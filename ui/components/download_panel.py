"""Bulk download component."""

from __future__ import annotations

import base64
import json
import re

import streamlit as st

from core.models import ProjectState, SceneImage, SceneVideo, SceneStatus, VideoStatus
from utils.file_utils import create_zip_from_files


def _safe_filename(s: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in " _-" else "_" for c in s).strip()
    return re.sub(r"\s+", "_", cleaned) or "untitled"


def render_image_download_panel(images: list[SceneImage], scenes_titles: list[str]) -> None:
    """Render bulk download panel for approved images."""
    approved = [
        (i, img) for i, img in enumerate(images)
        if img.status == SceneStatus.APPROVED and img.image_b64
    ]
    if not approved:
        return

    st.divider()
    st.subheader(f"Download Approved Images ({len(approved)})")

    files = {}
    for i, img in approved:
        title = scenes_titles[i] if i < len(scenes_titles) else f"Scene {i + 1}"
        files[f"{i + 1}_{_safe_filename(title)}.png"] = base64.b64decode(img.image_b64)

    zip_bytes = create_zip_from_files(files)
    st.download_button(
        "Download All as ZIP",
        data=zip_bytes,
        file_name="approved_scenes.zip",
        mime="application/zip",
        key="dl_all_images_zip",
    )


def render_video_download_panel(videos: list[SceneVideo], scenes_titles: list[str]) -> None:
    """Render bulk download panel for approved videos."""
    approved = [
        (i, vid) for i, vid in enumerate(videos)
        if vid.status == VideoStatus.APPROVED and vid.video_b64
    ]
    if not approved:
        return

    st.divider()
    st.subheader(f"Download Approved Videos ({len(approved)})")

    files = {}
    for i, vid in approved:
        title = scenes_titles[i] if i < len(scenes_titles) else f"Scene {i + 1}"
        files[f"{i + 1}_{_safe_filename(title)}.mp4"] = base64.b64decode(vid.video_b64)

    zip_bytes = create_zip_from_files(files)
    st.download_button(
        "Download All as ZIP",
        data=zip_bytes,
        file_name="approved_videos.zip",
        mime="application/zip",
        key="dl_all_videos_zip",
    )


def build_full_project_zip(project: ProjectState) -> bytes:
    """Bundle the entire project — script, profile, images, videos, refs — into a ZIP."""
    files: dict[str, bytes] = {}

    # Reconstructed script (from parsed scenes) so the recipient can edit & re-run.
    if project.scenes:
        script_lines = []
        for i, scene in enumerate(project.scenes, 1):
            title = scene.title or f"Scene {i}"
            script_lines.append(f"SCENE {i}: {title}")
            if scene.description:
                script_lines.append(scene.description)
            script_lines.append("")
        files["script.txt"] = "\n".join(script_lines).encode("utf-8")

    # Character profile (redacted — no base64 payloads).
    if project.character:
        profile = project.character.model_dump(
            exclude={"reference_image_b64", "reference_images_b64"}
        )
        files["character.json"] = json.dumps(profile, indent=2).encode("utf-8")

    # All scene metadata + prompts.
    if project.scenes:
        scenes_export = [s.model_dump() for s in project.scenes]
        files["scenes.json"] = json.dumps(scenes_export, indent=2).encode("utf-8")

    # Reference images.
    if project.character and project.character.reference_images_b64:
        for i, b64 in enumerate(project.character.reference_images_b64):
            if not b64:
                continue
            try:
                name = (
                    project.character.reference_image_names[i]
                    if i < len(project.character.reference_image_names)
                    else f"reference_{i + 1}"
                )
                safe = _safe_filename(name)
                ext = "png"  # stored as png-equivalent; MIME lost at b64 boundary
                files[f"reference_images/{i + 1}_{safe}.{ext}"] = base64.b64decode(b64)
            except Exception:
                continue

    # All generated images (any status that has bytes).
    for img in project.images:
        if not img.image_b64:
            continue
        idx = img.scene_index
        title = (
            project.scenes[idx].title
            if idx < len(project.scenes) and project.scenes[idx].title
            else f"Scene {idx + 1}"
        )
        status_tag = img.status.value if img.status != SceneStatus.APPROVED else "approved"
        files[f"images/{idx + 1}_{_safe_filename(title)}_{status_tag}.png"] = base64.b64decode(
            img.image_b64
        )

    # All generated videos.
    for vid in project.videos:
        if not vid.video_b64:
            continue
        idx = vid.scene_index
        title = (
            project.scenes[idx].title
            if idx < len(project.scenes) and project.scenes[idx].title
            else f"Scene {idx + 1}"
        )
        status_tag = vid.status.value if vid.status != VideoStatus.APPROVED else "approved"
        files[f"videos/{idx + 1}_{_safe_filename(title)}_{status_tag}.mp4"] = base64.b64decode(
            vid.video_b64
        )

    # Manifest / README for the recipient.
    manifest_lines = [
        f"# {project.name}",
        "",
        f"Exported from Scene Studio on {project.updated_at.isoformat(timespec='seconds')}.",
        f"Project ID: {project.project_id}",
        "",
        "## Contents",
        "- script.txt       Reconstructed script with scene headers",
        "- character.json   Character profile (style, description, palette)",
        "- scenes.json      All scene metadata and prompts",
        "- reference_images/   Reference images provided for the character",
        "- images/          Generated scene images (all statuses)",
        "- videos/          Generated scene videos (all statuses)",
    ]
    files["README.md"] = "\n".join(manifest_lines).encode("utf-8")

    return create_zip_from_files(files)


def render_full_project_download(project: ProjectState, key_suffix: str = "") -> None:
    """Render a 'Download full project' button.

    Call from anywhere (sidebar, finish screen, etc.). Disabled when there's
    nothing meaningful to export.
    """
    has_content = bool(
        project.character
        or project.scenes
        or any(img.image_b64 for img in project.images)
        or any(vid.video_b64 for vid in project.videos)
    )
    filename = f"{_safe_filename(project.name or 'scene_studio_project')}.zip"

    if not has_content:
        st.button(
            "📦 Export full project",
            disabled=True,
            use_container_width=True,
            key=f"full_export_btn_disabled{key_suffix}",
            help="Nothing to export yet — add a character, scenes, or generate images first.",
        )
        return

    zip_bytes = build_full_project_zip(project)
    st.download_button(
        "📦 Export full project",
        data=zip_bytes,
        file_name=filename,
        mime="application/zip",
        use_container_width=True,
        key=f"full_export_btn{key_suffix}",
        help="Bundle script, character profile, prompts, images, and videos into a single ZIP.",
    )
