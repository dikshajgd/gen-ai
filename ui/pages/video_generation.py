"""Step 4: Video generation, review, and approval."""

from __future__ import annotations

import streamlit as st

from core.models import ProjectState, SceneStatus, VideoStatus
from core.constants import (
    SCENE_GRID_COLUMNS,
    KLING_DURATIONS,
    KLING_ASPECT_RATIOS,
    KLING_POLL_INTERVAL_SEC,
)
from services.gemini_client import GeminiClient
from services.kling_client import KlingClient
from services.script_parser import ScriptParser
from engine.video_pipeline import VideoPipeline
from ui.components.scene_card import render_video_card
from ui.components.progress_tracker import render_video_progress
from ui.components.download_panel import render_video_download_panel


def _get_kling_client() -> KlingClient | None:
    access = st.session_state.get("kling_access_key", "")
    if access:
        return KlingClient(access)
    return None


def render(project: ProjectState) -> None:
    st.header("Step 4: Video Generation")

    # Get approved images
    approved_indices = [
        i for i, img in enumerate(project.images)
        if img.status == SceneStatus.APPROVED
    ]

    if not approved_indices:
        with st.container(border=True):
            st.markdown("#### Nothing to animate yet")
            st.caption(
                "Approve at least one image in Step 3 before generating videos. "
                "Only approved images can be turned into videos."
            )
            if st.button("← Back to Image Review", type="primary", key="step4_jump_back"):
                project.current_step = 3
                st.rerun()
        return

    # Auto-poll for processing videos (runs only when needed, as a fragment)
    if any(v.status == VideoStatus.PROCESSING for v in project.videos):
        _video_poll_fragment()

    # Video progress
    render_video_progress(project.videos)

    # Settings
    with st.expander("Video Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            duration = st.radio(
                "Duration (seconds):",
                options=KLING_DURATIONS,
                format_func=lambda x: f"{x:.0f}s",
                key="vid_duration",
            )
        with col2:
            aspect_ratio = st.selectbox(
                "Aspect Ratio:",
                options=KLING_ASPECT_RATIOS,
                key="vid_aspect_ratio",
            )

    # Generate video prompts if not done
    _ensure_video_prompts(project, approved_indices)

    # Editable video prompts
    st.subheader("Video Prompts")
    prompts = {}
    for idx in approved_indices:
        scene = project.scenes[idx]
        video = project.videos[idx]
        if video.status in (VideoStatus.APPROVED,):
            continue
        prompts[idx] = st.text_area(
            f"Scene {idx + 1}: {scene.title}",
            value=scene.video_prompt or scene.description,
            height=60,
            key=f"vid_prompt_{idx}",
        )
        # Save back
        scene.video_prompt = prompts[idx]

    # Generate button
    not_started = [
        idx for idx in approved_indices
        if project.videos[idx].status in (VideoStatus.NOT_STARTED, VideoStatus.FAILED, VideoStatus.REJECTED)
    ]
    col1, col2 = st.columns([1, 2])
    with col1:
        generate_all = st.button(
            f"Generate All Videos ({len(not_started)})",
            disabled=len(not_started) == 0,
            type="primary",
            key="gen_all_vids_btn",
        )

    if generate_all:
        kling = _get_kling_client()
        if not kling:
            st.error("Please set your fal.ai API key in Settings.")
            return

        pipeline = VideoPipeline(kling)

        # Collect prompts
        vid_prompts = {}
        for idx in not_started:
            scene = project.scenes[idx]
            vid_prompts[idx] = scene.video_prompt or scene.description

        with st.spinner("Submitting video generation requests..."):
            project.videos = pipeline.submit_all(
                approved_indices=not_started,
                images=project.images,
                videos=project.videos,
                scenes_prompts=vid_prompts,
                duration=duration,
                aspect_ratio=aspect_ratio,
            )
        st.session_state["_poll_timer"] = time.time()
        st.rerun()

    # Video grid
    st.divider()
    for row_start in range(0, len(approved_indices), SCENE_GRID_COLUMNS):
        cols = st.columns(SCENE_GRID_COLUMNS)
        for col_idx in range(SCENE_GRID_COLUMNS):
            list_idx = row_start + col_idx
            if list_idx >= len(approved_indices):
                break

            scene_idx = approved_indices[list_idx]
            scene = project.scenes[scene_idx]
            img = project.images[scene_idx]
            video = project.videos[scene_idx]

            with cols[col_idx]:
                actions = render_video_card(scene_idx, scene.title, img, video)

                if actions["approve"]:
                    video.status = VideoStatus.APPROVED
                    st.rerun()

                if actions["reject"]:
                    video.status = VideoStatus.REJECTED
                    st.rerun()

                if actions["retry"]:
                    kling = _get_kling_client()
                    if kling:
                        pipeline = VideoPipeline(kling)
                        with st.spinner(f"Retrying scene {scene_idx + 1}..."):
                            project.videos[scene_idx] = pipeline.retry_single(
                                idx=scene_idx,
                                images=project.images,
                                videos=project.videos,
                                prompt=scene.video_prompt or scene.description,
                                duration=duration,
                                aspect_ratio=aspect_ratio,
                            )
                        st.rerun()

    # Download panel
    render_video_download_panel(project.videos, [s.title for s in project.scenes])

    # Navigation
    st.divider()
    if st.button("← Back to Image Review", key="step4_back"):
        project.current_step = 3
        st.rerun()


@st.fragment(run_every=int(KLING_POLL_INTERVAL_SEC))
def _video_poll_fragment() -> None:
    """Poll Kling for processing videos on a fixed cadence.

    Uses Streamlit's fragment mechanism so the rest of the page isn't
    re-executed every tick — the fragment reruns every N seconds on its own.
    Only triggers a full-page rerun when a video actually changes state,
    which is when the outer metrics need refreshing.
    """
    project: ProjectState = st.session_state["project"]

    before = sum(1 for v in project.videos if v.status == VideoStatus.PROCESSING)
    if before == 0:
        return

    kling = _get_kling_client()
    if not kling:
        st.caption("⚠️ Add a fal.ai key in the sidebar to resume polling.")
        return

    pipeline = VideoPipeline(kling)
    project.videos = pipeline.poll_all(project.videos)

    after = sum(1 for v in project.videos if v.status == VideoStatus.PROCESSING)
    if after < before:
        st.rerun(scope="app")
    else:
        st.caption(
            f"⏳ {after} video(s) still processing — next check in "
            f"{int(KLING_POLL_INTERVAL_SEC)}s."
        )


def _ensure_video_prompts(project: ProjectState, approved_indices: list[int]) -> None:
    """Generate video prompts if not already done."""
    needs_prompts = [
        idx for idx in approved_indices
        if not project.scenes[idx].video_prompt
    ]
    if not needs_prompts:
        return

    api_key = st.session_state.get("gemini_api_key", "")
    if not api_key:
        return

    gemini = GeminiClient(api_key)
    parser = ScriptParser(gemini)
    scenes_to_update = [project.scenes[idx] for idx in needs_prompts]
    parser.generate_video_prompts(scenes_to_update)
