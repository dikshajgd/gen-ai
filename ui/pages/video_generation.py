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
from config import get_gemini_api_key
from services.gemini_client import GeminiClient
from services.script_parser import ScriptParser
from services.video_providers import (
    PROVIDER_CATALOG,
    DEFAULT_PROVIDER_MODEL,
    VideoProviderError,
)
from services.video_providers.registry import is_provider_available
from engine.video_pipeline import VideoPipeline
from ui.components.scene_card import render_video_card
from ui.components.progress_tracker import render_video_progress
from ui.components.download_panel import render_video_download_panel


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

    # ── Provider/model + duration/aspect ratio settings ──
    with st.expander("Video Settings", expanded=True):
        provider_id, model_name = _render_provider_picker(project)

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

    # Eligible scenes: approved images that don't already have a finished/in-progress video.
    not_started = [
        idx for idx in approved_indices
        if project.videos[idx].status in (VideoStatus.NOT_STARTED, VideoStatus.FAILED, VideoStatus.REJECTED)
    ]

    # Editable video prompts + per-scene "include in this batch" toggle
    st.subheader("Video Prompts")
    if not_started:
        sel_col_a, sel_col_b, _spacer = st.columns([1, 1, 6])
        with sel_col_a:
            if st.button("Select all", key="vid_select_all"):
                for idx in not_started:
                    st.session_state[f"vid_selected_{idx}"] = True
                st.rerun()
        with sel_col_b:
            if st.button("Clear all", key="vid_clear_all"):
                for idx in not_started:
                    st.session_state[f"vid_selected_{idx}"] = False
                st.rerun()

    for idx in approved_indices:
        scene = project.scenes[idx]
        video = project.videos[idx]
        if video.status in (VideoStatus.APPROVED,):
            continue

        is_eligible = idx in not_started
        check_col, prompt_col = st.columns([1, 11])
        with check_col:
            if is_eligible:
                st.checkbox(
                    "Include",
                    value=st.session_state.get(f"vid_selected_{idx}", True),
                    key=f"vid_selected_{idx}",
                    label_visibility="collapsed",
                )
            else:
                st.markdown("&nbsp;", unsafe_allow_html=True)
        with prompt_col:
            new_prompt = st.text_area(
                f"Scene {idx + 1}: {scene.title}",
                value=scene.video_prompt or scene.description,
                height=60,
                key=f"vid_prompt_{idx}",
                disabled=not is_eligible,
            )
            scene.video_prompt = new_prompt

    # Resolve selection — only checked, eligible scenes are submitted
    selected = [
        idx for idx in not_started
        if st.session_state.get(f"vid_selected_{idx}", True)
    ]

    # Generate button
    col1, col2 = st.columns([1, 2])
    with col1:
        provider_ready = is_provider_available(provider_id)
        if len(selected) == len(not_started):
            btn_label = f"Generate All Videos ({len(selected)})"
        else:
            btn_label = f"Generate Selected ({len(selected)} of {len(not_started)})"
        generate_all = st.button(
            btn_label,
            disabled=len(selected) == 0 or not provider_ready,
            type="primary",
            key="gen_all_vids_btn",
            help=None if provider_ready else "This provider's credentials are missing from app secrets.",
        )

    if generate_all:
        try:
            pipeline = VideoPipeline(provider_id, model_name)
        except VideoProviderError as e:
            st.error(str(e))
            return

        vid_prompts = {idx: project.scenes[idx].video_prompt or project.scenes[idx].description for idx in selected}

        with st.spinner("Submitting video generation requests..."):
            project.videos = pipeline.submit_all(
                approved_indices=selected,
                images=project.images,
                videos=project.videos,
                scenes_prompts=vid_prompts,
                duration=duration,
                aspect_ratio=aspect_ratio,
            )
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
                    try:
                        pipeline = VideoPipeline(provider_id, model_name)
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
                    except VideoProviderError as e:
                        st.error(str(e))

    # Download panel
    render_video_download_panel(project.videos, [s.title for s in project.scenes])

    # Navigation
    st.divider()
    if st.button("← Back to Image Review", key="step4_back"):
        project.current_step = 3
        st.rerun()


# ── Provider selection ───────────────────────────────────────────────


def _render_provider_picker(project: ProjectState) -> tuple[str, str]:
    """Render the provider/model dropdown and persist the choice on the project.

    Returns (provider_id, model_id) — guaranteed non-empty.
    """
    # Build label list, marking unavailable providers with a 🔒 prefix.
    options: list[tuple[str, str, str]] = []  # (provider_id, model_id, ui_label)
    for pid, mid, label, _notes in PROVIDER_CATALOG:
        prefix = "" if is_provider_available(pid) else "🔒 "
        options.append((pid, mid, f"{prefix}{label}"))

    # Default selection: project-saved choice → first available → catalog default.
    saved = (project.video_provider, project.video_model) if project.video_provider else None
    fallback = DEFAULT_PROVIDER_MODEL

    def _index_for(pid: str, mid: str) -> int:
        for i, (p, m, _l) in enumerate(options):
            if p == pid and m == mid:
                return i
        return 0

    initial_idx = (
        _index_for(*saved) if saved else
        next((i for i, (p, _m, _l) in enumerate(options) if is_provider_available(p)), _index_for(*fallback))
    )

    chosen = st.selectbox(
        "Video provider & model",
        options=options,
        index=initial_idx,
        format_func=lambda opt: opt[2],
        key="video_provider_model_select",
    )
    chosen_pid, chosen_mid, _label = chosen

    # Persist the choice on the project so it survives reload.
    if (project.video_provider, project.video_model) != (chosen_pid, chosen_mid):
        project.video_provider = chosen_pid
        project.video_model = chosen_mid

    if not is_provider_available(chosen_pid):
        st.warning(
            "🔒 This provider's credentials are missing from app secrets."
        )

    return chosen_pid, chosen_mid


# ── Polling fragment ─────────────────────────────────────────────────


@st.fragment(run_every=int(KLING_POLL_INTERVAL_SEC))
def _video_poll_fragment() -> None:
    """Poll the chosen provider for processing videos on a fixed cadence.

    Each video records which provider it was submitted to, so the pipeline
    can poll the right backend even if the project default has since changed.
    """
    project: ProjectState = st.session_state["project"]

    before = sum(1 for v in project.videos if v.status == VideoStatus.PROCESSING)
    if before == 0:
        return

    provider_id = project.video_provider or DEFAULT_PROVIDER_MODEL[0]
    model_name = project.video_model or DEFAULT_PROVIDER_MODEL[1]

    try:
        pipeline = VideoPipeline(provider_id, model_name)
        project.videos = pipeline.poll_all(project.videos)
    except VideoProviderError as e:
        st.caption(f"⚠️ Polling paused: {e}")
        return

    after = sum(1 for v in project.videos if v.status == VideoStatus.PROCESSING)
    if after < before:
        st.rerun(scope="app")
    else:
        st.caption(
            f"⏳ {after} video(s) still processing — next check in "
            f"{int(KLING_POLL_INTERVAL_SEC)}s."
        )


def _ensure_video_prompts(project: ProjectState, approved_indices: list[int]) -> None:
    """Generate video prompts for any scene that doesn't have one yet."""
    needs_prompts = [
        idx for idx in approved_indices
        if not project.scenes[idx].video_prompt
    ]
    if not needs_prompts:
        return

    api_key = get_gemini_api_key()
    if not api_key:
        return

    gemini = GeminiClient(api_key)
    parser = ScriptParser(gemini)
    scenes_to_update = [project.scenes[idx] for idx in needs_prompts]
    parser.generate_video_prompts(scenes_to_update)
