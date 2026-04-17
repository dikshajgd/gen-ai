"""Progress tracking component."""

from __future__ import annotations

import streamlit as st

from core.models import SceneImage, SceneVideo, SceneStatus, VideoStatus


def render_image_progress(images: list[SceneImage]) -> None:
    """Show progress bar and counts for image generation."""
    if not images:
        return

    total = len(images)
    done = sum(1 for i in images if i.status in (SceneStatus.GENERATED, SceneStatus.APPROVED, SceneStatus.REJECTED))
    failed = sum(1 for i in images if i.status == SceneStatus.FAILED)
    approved = sum(1 for i in images if i.status == SceneStatus.APPROVED)

    progress = (done + failed) / total if total > 0 else 0
    st.progress(progress)

    cols = st.columns(4)
    cols[0].metric("Total", total)
    cols[1].metric("Generated", done)
    cols[2].metric("Approved", approved)
    cols[3].metric("Failed", failed)


def render_video_progress(videos: list[SceneVideo]) -> None:
    """Show progress bar and counts for video generation."""
    if not videos:
        return

    total = len([v for v in videos if v.status != VideoStatus.NOT_STARTED])
    if total == 0:
        return

    done = sum(1 for v in videos if v.status in (VideoStatus.COMPLETED, VideoStatus.APPROVED, VideoStatus.REJECTED))
    failed = sum(1 for v in videos if v.status == VideoStatus.FAILED)
    processing = sum(1 for v in videos if v.status == VideoStatus.PROCESSING)
    approved = sum(1 for v in videos if v.status == VideoStatus.APPROVED)

    progress = (done + failed) / total if total > 0 else 0
    st.progress(progress)

    cols = st.columns(4)
    cols[0].metric("Submitted", total)
    cols[1].metric("Processing", processing)
    cols[2].metric("Approved", approved)
    cols[3].metric("Failed", failed)
