"""Video generation pipeline — provider-agnostic.

Picks a `VideoProvider` for each scene (defaults to the project's selected
provider), submits in parallel, polls for completion, downloads the result.
"""

from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from core.constants import KLING_MAX_WORKERS
from core.models import SceneImage, SceneVideo, VideoStatus
from services.video_providers import (
    VideoProvider,
    VideoProviderError,
    get_provider,
    timeout_for_provider,
)

logger = logging.getLogger(__name__)


class VideoPipeline:
    """Orchestrates video generation across any provider in the registry."""

    def __init__(self, default_provider_id: str, default_model: str):
        """Construct with a default provider+model. Per-video overrides allowed."""
        self.default_provider_id = default_provider_id
        self.default_model = default_model

    # ── Submit ───────────────────────────────────────────────────────

    def submit_all(
        self,
        approved_indices: list[int],
        images: list[SceneImage],
        videos: list[SceneVideo],
        scenes_prompts: dict[int, str],
        duration: float = 5.0,
        aspect_ratio: str = "16:9",
    ) -> list[SceneVideo]:
        """Submit all approved scenes in parallel, recording provider+task_id per video."""

        provider_id = self.default_provider_id
        model_name = self.default_model

        # Build the provider on the main thread — get_provider() reads
        # st.session_state, which is not accessible from worker threads on
        # Streamlit Cloud. Reusing one provider across workers is safe;
        # providers carry only credentials and are stateless per request.
        try:
            provider = get_provider(provider_id)
        except VideoProviderError as e:
            for idx in approved_indices:
                video = videos[idx]
                video.status = VideoStatus.FAILED
                video.error_message = str(e)
                video.generation_attempts += 1
            return videos

        def _submit_one(idx: int) -> tuple[int, str | None, str | None]:
            img = images[idx]
            prompt = scenes_prompts.get(idx, "")
            try:
                if not img.image_b64:
                    return idx, None, "Source image missing — cannot generate video."
                image_bytes = base64.b64decode(img.image_b64)
                submission = provider.submit_image_to_video(
                    image_bytes=image_bytes,
                    prompt=prompt,
                    duration_sec=duration,
                    aspect_ratio=aspect_ratio,
                    model=model_name,
                )
                return idx, submission.task_id, None
            except VideoProviderError as e:
                logger.warning("Submit failed for scene %s: %s", idx, e)
                return idx, None, str(e)
            except Exception as e:
                logger.exception("Unexpected submit error for scene %s", idx)
                return idx, None, f"Unexpected error: {e}"

        with ThreadPoolExecutor(max_workers=KLING_MAX_WORKERS) as executor:
            futures = {executor.submit(_submit_one, idx): idx for idx in approved_indices}
            for future in as_completed(futures):
                idx, task_id, error = future.result()
                video = videos[idx]
                if task_id:
                    video.kling_task_id = task_id
                    video.provider = provider_id
                    video.model_name = model_name
                    video.status = VideoStatus.PROCESSING
                    video.submitted_at = datetime.now()
                    video.error_message = ""
                else:
                    video.status = VideoStatus.FAILED
                    video.error_message = error or "Submission failed"
                    video.generation_attempts += 1

        return videos

    # ── Poll ────────────────────────────────────────────────────────

    def poll_all(self, videos: list[SceneVideo]) -> list[SceneVideo]:
        """Poll status of every PROCESSING video, download succeeded ones."""
        for video in videos:
            if video.status != VideoStatus.PROCESSING:
                continue
            if not video.kling_task_id:
                continue

            provider_id = video.provider or self.default_provider_id

            # Timeout guard — provider-specific because Veo's queue can be much
            # slower than Kling/Replicate.
            if video.submitted_at:
                elapsed = (datetime.now() - video.submitted_at).total_seconds()
                timeout = timeout_for_provider(provider_id)
                if elapsed > timeout:
                    video.status = VideoStatus.FAILED
                    video.error_message = f"Timed out after {timeout}s"
                    continue
            try:
                provider = get_provider(provider_id)
                result = provider.get_task_status(video.kling_task_id)
            except VideoProviderError as e:
                video.error_message = f"Poll error: {e}"
                logger.warning("Poll error for task %s (provider=%s): %s", video.kling_task_id, provider_id, e)
                continue
            except Exception as e:
                video.error_message = f"Poll error: {e}"
                logger.exception("Unexpected poll error for task %s", video.kling_task_id)
                continue

            if result.state == "succeed":
                video.video_url = result.video_url
                try:
                    video_bytes = provider.download_video(result.video_url)
                    video.video_b64 = base64.b64encode(video_bytes).decode()
                    video.status = VideoStatus.COMPLETED
                    video.completed_at = datetime.now()
                except Exception as e:
                    video.status = VideoStatus.FAILED
                    video.error_message = f"Download failed: {e}"
                    logger.exception("Video download failed for task %s", video.kling_task_id)

            elif result.state == "failed":
                video.status = VideoStatus.FAILED
                video.error_message = result.error_message or "Generation failed"
            # else: still processing

        return videos

    # ── Retry single ─────────────────────────────────────────────────

    def retry_single(
        self,
        idx: int,
        images: list[SceneImage],
        videos: list[SceneVideo],
        prompt: str,
        duration: float = 5.0,
        aspect_ratio: str = "16:9",
    ) -> SceneVideo:
        """Retry video generation for a single scene with the project's default provider."""
        video = videos[idx]
        img = images[idx]
        video.generation_attempts += 1
        video.error_message = ""
        video.kling_task_id = ""
        video.video_url = ""
        video.video_b64 = ""
        video.status = VideoStatus.SUBMITTING

        try:
            provider = get_provider(self.default_provider_id)
            if not img.image_b64:
                raise VideoProviderError("Source image missing.")
            image_bytes = base64.b64decode(img.image_b64)
            submission = provider.submit_image_to_video(
                image_bytes=image_bytes,
                prompt=prompt,
                duration_sec=duration,
                aspect_ratio=aspect_ratio,
                model=self.default_model,
            )
            video.kling_task_id = submission.task_id
            video.provider = self.default_provider_id
            video.model_name = self.default_model
            video.status = VideoStatus.PROCESSING
            video.submitted_at = datetime.now()
        except VideoProviderError as e:
            video.status = VideoStatus.FAILED
            video.error_message = str(e)
            logger.warning("Retry failed for scene %s: %s", idx, e)
        except Exception as e:
            video.status = VideoStatus.FAILED
            video.error_message = f"Unexpected error: {e}"
            logger.exception("Unexpected retry error for scene %s", idx)

        return video
