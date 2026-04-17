"""Video generation client using fal.ai (Kling models)."""

from __future__ import annotations

import base64
import os
import time

import fal_client
import requests

from utils.retry import kling_retry


FAL_KLING_MODEL = "fal-ai/kling-video/v2.6/pro/image-to-video"


class KlingAPIError(Exception):
    """Raised on video generation API errors."""
    pass


class KlingClient:
    """Video generation client using fal.ai's Kling endpoint.

    Uses simple API key auth instead of JWT.
    """

    def __init__(self, access_key: str, secret_key: str = ""):
        # For fal.ai, access_key is the FAL_KEY
        self.api_key = access_key
        os.environ["FAL_KEY"] = access_key

    @kling_retry
    def submit_image_to_video(
        self,
        image_b64: str,
        prompt: str,
        duration: float = 5.0,
        aspect_ratio: str = "16:9",
    ) -> str:
        """Submit an image-to-video generation request via fal.ai.

        Returns a request_id for polling.
        """
        # Convert base64 to a data URI for fal.ai
        if not image_b64.startswith("data:"):
            image_uri = f"data:image/png;base64,{image_b64}"
        else:
            image_uri = image_b64

        try:
            handler = fal_client.submit(
                FAL_KLING_MODEL,
                arguments={
                    "prompt": prompt,
                    "start_image_url": image_uri,
                    "duration": str(int(duration)),
                    "aspect_ratio": aspect_ratio,
                },
            )
            return handler.request_id
        except Exception as e:
            raise KlingAPIError(f"fal.ai submission error: {e}")

    @kling_retry
    def get_task_status(self, task_id: str) -> dict:
        """Check the status of a video generation task."""
        try:
            status = fal_client.status(FAL_KLING_MODEL, task_id, with_logs=False)

            if isinstance(status, fal_client.Completed):
                # Fetch the result
                result = fal_client.result(FAL_KLING_MODEL, task_id)
                return {
                    "task_status": "succeed",
                    "task_result": {
                        "videos": [{"resource": {"resource": result.get("video", {}).get("url", "")}}]
                    },
                }
            elif isinstance(status, fal_client.InProgress):
                return {"task_status": "processing"}
            elif isinstance(status, fal_client.Queued):
                return {"task_status": "processing"}
            else:
                return {"task_status": "processing"}

        except Exception as e:
            error_msg = str(e)
            if "not found" in error_msg.lower() or "404" in error_msg:
                return {"task_status": "failed", "task_status_msg": error_msg}
            raise KlingAPIError(f"fal.ai status error: {e}")

    @kling_retry
    def download_video(self, url: str) -> bytes:
        """Download video bytes from a URL."""
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content
