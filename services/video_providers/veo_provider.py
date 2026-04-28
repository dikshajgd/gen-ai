"""Google Veo video provider via the Gemini API.

Veo is exposed through `google-genai`'s `client.models.generate_videos` and
runs as a long-running operation — submit, then poll, then fetch the file.
Reuses the same Gemini API key, so visitors who already provided one need no
extra credentials.
"""

from __future__ import annotations

import logging
from typing import Any

from services.video_providers.base import (
    VideoProvider,
    VideoProviderError,
    VideoStatusResult,
    VideoSubmission,
)

logger = logging.getLogger(__name__)


# Veo model identifiers as accepted by `google-genai`.
MODEL_VEO_3 = "veo-3.0-generate-001"
MODEL_VEO_3_FAST = "veo-3.0-fast-generate-001"
MODEL_VEO_2 = "veo-2.0-generate-001"


class VeoProvider(VideoProvider):
    provider_id = "veo"
    label = "Google Veo (uses Gemini key)"
    default_model = MODEL_VEO_3_FAST

    def __init__(self, api_key: str):
        if not api_key:
            raise VideoProviderError("Veo requires the Gemini API key.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise VideoProviderError(f"google-genai not installed: {exc}")

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=api_key.strip())

    # ── Provider API ─────────────────────────────────────────────────

    def submit_image_to_video(
        self,
        image_bytes: bytes,
        prompt: str,
        duration_sec: float,
        aspect_ratio: str,
        model: str,
    ) -> VideoSubmission:
        types = self._types
        model = model or self.default_model

        try:
            image = types.Image(image_bytes=image_bytes, mime_type="image/png")
            # Veo accepts 4-8s only; clamp so the shared duration radio (which
            # also offers 10s for Kling/Replicate) doesn't break Veo runs.
            clamped_duration = max(4, min(8, int(duration_sec)))
            config = types.GenerateVideosConfig(
                duration_seconds=clamped_duration,
                aspect_ratio=aspect_ratio if aspect_ratio in ("16:9", "9:16") else "16:9",
                number_of_videos=1,
            )
            operation = self._client.models.generate_videos(
                model=model,
                prompt=prompt,
                image=image,
                config=config,
            )
        except Exception as exc:
            raise VideoProviderError(f"Veo submit failed: {exc}") from exc

        # Operation object's `name` is the long-running id we'll poll on.
        op_name = getattr(operation, "name", "") or str(operation)
        return VideoSubmission(task_id=op_name, raw={"model": model, "name": op_name})

    def get_task_status(self, task_id: str) -> VideoStatusResult:
        try:
            operation = self._client.operations.get({"name": task_id})
        except Exception as exc:
            raise VideoProviderError(f"Veo status failed: {exc}") from exc

        if not getattr(operation, "done", False):
            return VideoStatusResult(state="processing", raw={"name": task_id})

        if getattr(operation, "error", None):
            err = operation.error
            return VideoStatusResult(
                state="failed",
                error_message=getattr(err, "message", "") or str(err),
                raw={"name": task_id},
            )

        # Veo response shape: operation.response.generated_videos[0].video
        response = getattr(operation, "response", None)
        videos = getattr(response, "generated_videos", None) if response else None
        if not videos:
            return VideoStatusResult(state="failed", error_message="No videos in Veo response.")

        first = videos[0]
        video = getattr(first, "video", None)
        # We use the `task_id` itself as the URL — download_video re-fetches the file.
        return VideoStatusResult(state="succeed", video_url=task_id, raw={"name": task_id, "video": video})

    def download_video(self, url: str) -> bytes:
        # `url` here is the operation name; pull the operation again, then download the file.
        try:
            operation = self._client.operations.get({"name": url})
            response = getattr(operation, "response", None)
            videos = getattr(response, "generated_videos", None) if response else None
            if not videos:
                raise VideoProviderError("Veo returned no videos at download time.")
            video = videos[0].video
            data = self._client.files.download(file=video)
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
            # Some genai versions return an object with `.data` or write to a path
            if hasattr(data, "data"):
                return bytes(data.data)
            raise VideoProviderError(f"Unexpected Veo download return type: {type(data)}")
        except VideoProviderError:
            raise
        except Exception as exc:
            raise VideoProviderError(f"Veo download failed: {exc}") from exc
