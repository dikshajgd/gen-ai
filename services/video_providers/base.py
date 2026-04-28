"""Abstract base for video generation providers.

Every provider implements three operations:
    submit_image_to_video(...) -> VideoSubmission   # returns a task id
    get_task_status(task_id)   -> VideoStatusResult # polled by the pipeline
    download_video(url)        -> bytes             # final retrieval

The pipeline doesn't care which model is behind the curtain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class VideoProviderError(Exception):
    """Raised on any provider failure."""


@dataclass
class VideoSubmission:
    """Returned from submit_image_to_video. Contains the provider's task id."""

    task_id: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoStatusResult:
    """Returned from get_task_status. Normalized across providers.

    state ∈ {"processing", "succeed", "failed"}
    """

    state: str
    video_url: str = ""
    error_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class VideoProvider:
    """Provider contract. Concrete implementations live alongside in this package."""

    #: Stable id used in the model and on the wire (e.g. "kling_direct").
    provider_id: str = ""

    #: Human-readable label for UI dropdowns.
    label: str = ""

    #: Default model name when caller doesn't specify one.
    default_model: str = ""

    def submit_image_to_video(
        self,
        image_bytes: bytes,
        prompt: str,
        duration_sec: float,
        aspect_ratio: str,
        model: str,
    ) -> VideoSubmission:
        raise NotImplementedError

    def get_task_status(self, task_id: str) -> VideoStatusResult:
        raise NotImplementedError

    def download_video(self, url: str) -> bytes:
        raise NotImplementedError
