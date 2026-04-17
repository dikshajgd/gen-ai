"""Video generation pipeline using Kling 3.0 API."""

from __future__ import annotations

import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from core.models import SceneImage, SceneVideo, SceneStatus, VideoStatus
from core.constants import KLING_MAX_WORKERS, KLING_TIMEOUT_SEC
from services.kling_client import KlingClient, KlingAPIError

logger = logging.getLogger(__name__)


class VideoPipeline:
    def __init__(self, kling_client: KlingClient):
        self.kling = kling_client

    def submit_all(
        self,
        approved_indices: list[int],
        images: list[SceneImage],
        videos: list[SceneVideo],
        scenes_prompts: dict[int, str],
        duration: float = 5.0,
        aspect_ratio: str = "16:9",
    ) -> list[SceneVideo]:
        """Submit video generation for all approved images in parallel."""

        def _submit_one(idx: int) -> tuple[int, str | None, str | None]:
            img = images[idx]
            prompt = scenes_prompts.get(idx, "")
            try:
                task_id = self.kling.submit_image_to_video(
                    image_b64=img.image_b64,
                    prompt=prompt,
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                )
                return idx, task_id, None
            except (KlingAPIError, Exception) as e:
                return idx, None, str(e)

        with ThreadPoolExecutor(max_workers=KLING_MAX_WORKERS) as executor:
            futures = {
                executor.submit(_submit_one, idx): idx
                for idx in approved_indices
            }
            for future in as_completed(futures):
                idx, task_id, error = future.result()
                video = videos[idx]
                if task_id:
                    video.kling_task_id = task_id
                    video.status = VideoStatus.PROCESSING
                    video.submitted_at = datetime.now()
                    video.error_message = ""
                else:
                    video.status = VideoStatus.FAILED
                    video.error_message = error or "Submission failed"
                    video.generation_attempts += 1

        return videos

    def poll_all(self, videos: list[SceneVideo]) -> list[SceneVideo]:
        """Check status of all processing videos. Download completed ones."""
        for video in videos:
            if video.status != VideoStatus.PROCESSING:
                continue
            if not video.kling_task_id:
                continue

            # Check timeout
            if video.submitted_at:
                elapsed = (datetime.now() - video.submitted_at).total_seconds()
                if elapsed > KLING_TIMEOUT_SEC:
                    video.status = VideoStatus.FAILED
                    video.error_message = f"Timed out after {KLING_TIMEOUT_SEC}s"
                    continue

            try:
                data = self.kling.get_task_status(video.kling_task_id)
                task_status = data.get("task_status", "")

                if task_status == "succeed":
                    # Get video URL from works array
                    works = data.get("task_result", {}).get("videos", [])
                    if not works:
                        works = data.get("works", [])
                    if works:
                        video.video_url = works[0].get("resource", {}).get("resource", "")
                        if not video.video_url:
                            video.video_url = works[0].get("url", "")

                    if video.video_url:
                        try:
                            video_bytes = self.kling.download_video(video.video_url)
                            video.video_b64 = base64.b64encode(video_bytes).decode()
                            video.status = VideoStatus.COMPLETED
                            video.completed_at = datetime.now()
                        except Exception as e:
                            video.status = VideoStatus.FAILED
                            video.error_message = f"Download failed: {e}"
                            logger.exception("Video download failed for task %s", video.task_id)
                    else:
                        video.status = VideoStatus.FAILED
                        video.error_message = "No video URL in response"

                elif task_status == "failed":
                    video.status = VideoStatus.FAILED
                    video.error_message = data.get("task_status_msg", "Generation failed")

                # else: still processing, leave status as-is

            except (KlingAPIError, Exception) as e:
                # Don't fail on poll errors, just log and try again next cycle
                video.error_message = f"Poll error: {e}"
                logger.warning("Poll error for task %s: %s", video.task_id, e)

        return videos

    def retry_single(
        self,
        idx: int,
        images: list[SceneImage],
        videos: list[SceneVideo],
        prompt: str,
        duration: float = 5.0,
        aspect_ratio: str = "16:9",
    ) -> SceneVideo:
        """Retry video generation for a single scene."""
        video = videos[idx]
        img = images[idx]
        video.generation_attempts += 1
        video.error_message = ""
        video.kling_task_id = ""
        video.video_url = ""
        video.video_b64 = ""
        video.status = VideoStatus.SUBMITTING

        try:
            task_id = self.kling.submit_image_to_video(
                image_b64=img.image_b64,
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
            )
            video.kling_task_id = task_id
            video.status = VideoStatus.PROCESSING
            video.submitted_at = datetime.now()
        except (KlingAPIError, Exception) as e:
            video.status = VideoStatus.FAILED
            video.error_message = str(e)

        return video
