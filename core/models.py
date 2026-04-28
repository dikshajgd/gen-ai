"""Pydantic data models for Scene Studio."""

from __future__ import annotations

import base64
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SceneStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class VideoStatus(str, Enum):
    NOT_STARTED = "not_started"
    SUBMITTING = "submitting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class CharacterProfile(BaseModel):
    reference_image_path: str = ""
    reference_image_b64: str = ""  # first ref image (backward compat)
    art_style: str = ""
    color_palette: list[str] = Field(default_factory=list)
    character_description: str = ""
    style_prompt_prefix: str = ""
    raw_analysis: str = ""
    # New fields for creative brief
    creative_prompt: str = ""
    style_prompt: str = ""
    reference_images_b64: list[str] = Field(default_factory=list)
    reference_image_names: list[str] = Field(default_factory=list)


class Scene(BaseModel):
    index: int
    title: str = ""
    description: str = ""
    image_prompt: str = ""
    video_prompt: str = ""
    # Optional per-scene style override — takes precedence over the global
    # character.style_prompt_prefix for this scene only. Use for flashbacks,
    # dream sequences, or stylistic variations.
    style_override: str = ""


class SceneImage(BaseModel):
    scene_index: int
    status: SceneStatus = SceneStatus.PENDING
    image_b64: str = ""
    # Previous versions kept for undo. Newest at index 0; capped by UI logic.
    history_b64: list[str] = Field(default_factory=list)
    generation_attempts: int = 0
    max_attempts: int = 3
    error_message: str = ""
    generated_at: datetime | None = None

    def get_image_bytes(self) -> bytes | None:
        if self.image_b64:
            return base64.b64decode(self.image_b64)
        return None


class SceneVideo(BaseModel):
    scene_index: int
    status: VideoStatus = VideoStatus.NOT_STARTED
    # Generic task id from the chosen provider. Field name kept as
    # `kling_task_id` for backward compat with previously-saved projects.
    kling_task_id: str = ""
    video_url: str = ""
    video_b64: str = ""
    duration_sec: float = 5.0
    generation_attempts: int = 0
    max_attempts: int = 3
    error_message: str = ""
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    # Which provider+model was used to generate this video. Empty for
    # videos saved before multi-provider support — they're treated as
    # the project's currently selected provider on resume.
    provider: str = ""
    model_name: str = ""

    def get_video_bytes(self) -> bytes | None:
        if self.video_b64:
            return base64.b64decode(self.video_b64)
        return None


class ProjectMetadata(BaseModel):
    project_id: str
    name: str = "Untitled Project"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    thumbnail_b64: str = ""
    scene_count: int = 0
    approved_images: int = 0
    approved_videos: int = 0


class ProjectState(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = "Untitled Project"
    character: CharacterProfile | None = None
    scenes: list[Scene] = Field(default_factory=list)
    images: list[SceneImage] = Field(default_factory=list)
    videos: list[SceneVideo] = Field(default_factory=list)
    gemini_conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    current_step: int = 1
    # Default video backend selected for this project. Each video also
    # records its own provider/model in case the user changed mid-project.
    video_provider: str = ""
    video_model: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
