"""Kling Open Platform direct API client.

Auth is JWT-based: each request must carry a fresh JWT signed with HS256 using
the user's Secret Key, with the Access Key as `iss`.

Docs: https://docs.qingque.cn/d/home/eZQDh53FXztmf3-2OYr3kjU0E

Endpoints used:
    POST {base}/v1/videos/image2video        — submit a job, get task_id
    GET  {base}/v1/videos/image2video/{id}   — poll status, get result
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import jwt
import requests

from services.video_providers.base import (
    VideoProvider,
    VideoProviderError,
    VideoStatusResult,
    VideoSubmission,
)
from utils.retry import kling_retry

logger = logging.getLogger(__name__)

# Singapore endpoint is preferred for global users; api.klingai.com is the China region.
DEFAULT_BASE = "https://api-singapore.klingai.com"
JWT_TTL_SEC = 1800
JWT_NBF_SKEW_SEC = 5

# Kling model identifiers as expected by the Open Platform API.
# The "pro" / "std" distinction is conveyed via the `mode` field in the body,
# not the model_name. Names below are the values Kling's API actually accepts.
MODEL_KLING_2_1_MASTER = "kling-v2-1-master"  # Kling 2.1 Master (latest)
MODEL_KLING_2_MASTER = "kling-v2-master"      # Kling 2.x Master
MODEL_KLING_1_6 = "kling-v1-6"                # Kling 1.6 fallback

# Back-compat aliases for code that still imports the old names.
MODEL_KLING_2_6_PRO = MODEL_KLING_2_1_MASTER
MODEL_KLING_1_6_PRO = MODEL_KLING_1_6


class KlingDirectProvider(VideoProvider):
    provider_id = "kling_direct"
    label = "Kling (direct)"
    default_model = MODEL_KLING_2_6_PRO

    def __init__(self, access_key: str, secret_key: str, base_url: str = DEFAULT_BASE):
        if not access_key or not secret_key:
            raise VideoProviderError("Kling Direct requires both Access Key and Secret Key.")
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.base_url = base_url.rstrip("/")

    # ── Auth ──────────────────────────────────────────────────────────

    def _sign_token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self.access_key,
            "exp": now + JWT_TTL_SEC,
            "nbf": now - JWT_NBF_SKEW_SEC,
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256", headers={"alg": "HS256", "typ": "JWT"})

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._sign_token()}",
            "Content-Type": "application/json",
        }

    # ── Public API ────────────────────────────────────────────────────

    @kling_retry
    def submit_image_to_video(
        self,
        image_bytes: bytes,
        prompt: str,
        duration_sec: float,
        aspect_ratio: str,
        model: str,
    ) -> VideoSubmission:
        body = {
            "model_name": model or self.default_model,
            "image": base64.b64encode(image_bytes).decode("utf-8"),
            "prompt": prompt[:2500],  # Kling caps prompts; truncate defensively
            "duration": str(int(duration_sec)),
            "aspect_ratio": aspect_ratio,
            "mode": "pro" if "pro" in (model or "").lower() else "std",
            "cfg_scale": 0.5,
        }

        resp = requests.post(
            f"{self.base_url}/v1/videos/image2video",
            json=body,
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code >= 400:
            raise VideoProviderError(f"Kling submit HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        if data.get("code") != 0:
            raise VideoProviderError(f"Kling submit error: {data.get('message')}")

        task_id = (data.get("data") or {}).get("task_id")
        if not task_id:
            raise VideoProviderError(f"Kling submit returned no task_id: {data}")

        return VideoSubmission(task_id=task_id, raw=data)

    @kling_retry
    def get_task_status(self, task_id: str) -> VideoStatusResult:
        resp = requests.get(
            f"{self.base_url}/v1/videos/image2video/{task_id}",
            headers=self._headers(),
            timeout=20,
        )
        if resp.status_code == 404:
            return VideoStatusResult(state="failed", error_message="Task not found.")
        if resp.status_code >= 400:
            raise VideoProviderError(f"Kling status HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        if data.get("code") != 0:
            return VideoStatusResult(state="failed", error_message=str(data.get("message")), raw=data)

        payload = data.get("data") or {}
        status_str = (payload.get("task_status") or "").lower()

        # Kling status values: "submitted", "processing", "succeed", "failed"
        if status_str == "succeed":
            videos = (payload.get("task_result") or {}).get("videos") or []
            video_url = videos[0]["url"] if videos and videos[0].get("url") else ""
            if not video_url:
                return VideoStatusResult(state="failed", error_message="No video URL in result.", raw=data)
            return VideoStatusResult(state="succeed", video_url=video_url, raw=data)

        if status_str == "failed":
            return VideoStatusResult(
                state="failed",
                error_message=payload.get("task_status_msg") or "Generation failed.",
                raw=data,
            )

        return VideoStatusResult(state="processing", raw=data)

    @kling_retry
    def download_video(self, url: str) -> bytes:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content
