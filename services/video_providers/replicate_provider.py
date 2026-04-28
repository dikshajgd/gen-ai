"""Replicate-based video provider — covers Wan 2.1, Seedance Pro, and others.

The model id (e.g. "wan-ai/wan-2.1-i2v-720p" or "bytedance/seedance-1-pro") is
passed at submit time and routes to the right Replicate model. Replicate
returns prediction ids which we treat as task ids.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from services.video_providers.base import (
    VideoProvider,
    VideoProviderError,
    VideoStatusResult,
    VideoSubmission,
)

logger = logging.getLogger(__name__)


# Replicate model slugs we support. Keep them in one place so the UI
# dropdown and the input formatters agree.
MODEL_WAN_2_1 = "wan-ai/wan-2.1-i2v-720p"
MODEL_SEEDANCE_1_PRO = "bytedance/seedance-1-pro"
MODEL_KLING_2_1_MASTER = "kwaivgi/kling-v2.1-master"


class ReplicateProvider(VideoProvider):
    provider_id = "replicate"
    label = "Replicate"
    default_model = MODEL_WAN_2_1

    def __init__(self, api_token: str):
        if not api_token:
            raise VideoProviderError("Replicate requires an API token.")
        try:
            import replicate
        except ImportError as exc:
            raise VideoProviderError(f"replicate package not installed: {exc}")

        self._replicate = replicate
        self._client = replicate.Client(api_token=api_token.strip())

    # ── Provider API ─────────────────────────────────────────────────

    def submit_image_to_video(
        self,
        image_bytes: bytes,
        prompt: str,
        duration_sec: float,
        aspect_ratio: str,
        model: str,
    ) -> VideoSubmission:
        model = model or self.default_model
        image_data_uri = self._to_data_uri(image_bytes)
        inputs = self._build_inputs(model, image_data_uri, prompt, duration_sec, aspect_ratio)

        try:
            prediction = self._client.predictions.create(model=model, input=inputs)
        except Exception as exc:
            raise VideoProviderError(f"Replicate submit failed: {exc}") from exc

        return VideoSubmission(
            task_id=prediction.id,
            raw={"model": model, "id": prediction.id, "status": prediction.status},
        )

    def get_task_status(self, task_id: str) -> VideoStatusResult:
        try:
            prediction = self._client.predictions.get(task_id)
        except Exception as exc:
            raise VideoProviderError(f"Replicate status failed: {exc}") from exc

        status = (prediction.status or "").lower()
        if status in ("succeeded",):
            url = self._extract_url(prediction.output)
            if not url:
                return VideoStatusResult(state="failed", error_message="Prediction had no output URL.")
            return VideoStatusResult(state="succeed", video_url=url, raw={"id": prediction.id})

        if status in ("failed", "canceled"):
            return VideoStatusResult(
                state="failed",
                error_message=str(prediction.error or "Replicate prediction failed."),
                raw={"id": prediction.id},
            )

        # "starting", "processing", "queued"
        return VideoStatusResult(state="processing", raw={"id": prediction.id, "status": status})

    def download_video(self, url: str) -> bytes:
        import requests

        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _to_data_uri(image_bytes: bytes) -> str:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def _build_inputs(
        model: str,
        image_data_uri: str,
        prompt: str,
        duration_sec: float,
        aspect_ratio: str,
    ) -> dict[str, Any]:
        """Per-model input shapes — Replicate isn't uniform across models."""
        duration_int = max(1, int(duration_sec))

        if model.startswith("wan-ai/"):
            return {
                "image": image_data_uri,
                "prompt": prompt,
                "num_frames": 81 if duration_int <= 5 else 161,  # Wan: ~16fps
            }
        if model.startswith("bytedance/seedance"):
            return {
                "image": image_data_uri,
                "prompt": prompt,
                "duration": duration_int,
                "aspect_ratio": aspect_ratio,
                "resolution": "720p",
            }
        if model.startswith("kwaivgi/kling"):
            return {
                "start_image": image_data_uri,
                "prompt": prompt,
                "duration": duration_int,
                "aspect_ratio": aspect_ratio,
                "negative_prompt": "",
            }

        # Generic fallback — most i2v models accept these names
        return {"image": image_data_uri, "prompt": prompt}

    @staticmethod
    def _extract_url(output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, list) and output:
            first = output[0]
            return first if isinstance(first, str) else getattr(first, "url", "")
        if hasattr(output, "url"):
            return getattr(output, "url")
        return ""
