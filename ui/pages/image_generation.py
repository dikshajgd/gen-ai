"""Step 3: Image generation, review, and approval."""

from __future__ import annotations

import streamlit as st

from core.models import ProjectState, SceneStatus, SceneVideo, VideoStatus
from core.constants import SCENE_GRID_COLUMNS
from config import get_gemini_api_key
from services.gemini_client import GeminiClient
from engine.image_pipeline import ImagePipeline
from ui.components.scene_card import render_image_card
from ui.components.progress_tracker import render_image_progress
from ui.components.download_panel import render_image_download_panel


def render(project: ProjectState) -> None:
    st.header("Step 3: Image Generation")

    if not project.images:
        with st.container(border=True):
            st.markdown("#### No scenes yet")
            st.caption(
                "Parse a script in Step 2 and scenes will show up here, "
                "ready to generate images from."
            )
            if st.button("← Back to Script Input", type="primary", key="step3_jump_back"):
                project.current_step = 2
                st.rerun()
        return

    # Progress
    render_image_progress(project.images)

    # Controls
    col1, col2, col3 = st.columns([1, 1, 2])
    pending_count = sum(
        1 for img in project.images
        if img.status in (SceneStatus.PENDING, SceneStatus.REJECTED, SceneStatus.FAILED)
    )

    with col1:
        generate_all = st.button(
            f"Generate All ({pending_count})",
            disabled=pending_count == 0 or st.session_state.get("_generating", False),
            type="primary",
            key="gen_all_btn",
        )
    with col2:
        approve_all_generated = st.button(
            "Approve All Generated",
            key="approve_all_gen_btn",
        )

    # Approve all generated at once
    if approve_all_generated:
        for img in project.images:
            if img.status == SceneStatus.GENERATED:
                img.status = SceneStatus.APPROVED
        st.rerun()

    # Generate all
    if generate_all:
        api_key = get_gemini_api_key()
        if not api_key:
            st.error("GEMINI_API_KEY is missing from app secrets.")
            return

        st.session_state["_generating"] = True
        client = GeminiClient(api_key)
        pipeline = ImagePipeline(client)

        progress_placeholder = st.empty()

        def on_progress(idx, img, history):
            project.images[idx] = img
            project.gemini_conversation_history = history
            progress_placeholder.text(f"Processing scene {idx + 1}/{len(project.scenes)}...")

        with st.spinner("Generating images..."):
            project.images, project.gemini_conversation_history = pipeline.generate_all(
                scenes=project.scenes,
                images=project.images,
                character=project.character,
                history=project.gemini_conversation_history,
                on_progress=on_progress,
            )

        st.session_state["_generating"] = False
        st.rerun()

    # Scene grid
    st.divider()
    for row_start in range(0, len(project.scenes), SCENE_GRID_COLUMNS):
        cols = st.columns(SCENE_GRID_COLUMNS)
        for col_idx in range(SCENE_GRID_COLUMNS):
            scene_idx = row_start + col_idx
            if scene_idx >= len(project.scenes):
                break

            scene = project.scenes[scene_idx]
            img = project.images[scene_idx]

            with cols[col_idx]:
                actions = render_image_card(scene_idx, scene.title, img)

                if actions["approve"]:
                    img.status = SceneStatus.APPROVED
                    st.rerun()

                if actions["reject"]:
                    img.status = SceneStatus.REJECTED
                    st.rerun()

                if actions.get("undo") and img.history_b64:
                    # Swap current image with the newest history entry.
                    previous = img.history_b64.pop(0)
                    img.history_b64.insert(0, img.image_b64)  # current becomes redo
                    img.image_b64 = previous
                    img.status = SceneStatus.GENERATED
                    img.error_message = ""
                    st.rerun()

                if actions["regenerate"]:
                    api_key = get_gemini_api_key()
                    if api_key:
                        client = GeminiClient(api_key)
                        pipeline = ImagePipeline(client)
                        with st.spinner(f"Regenerating scene {scene_idx + 1}..."):
                            img, project.gemini_conversation_history = pipeline.regenerate_single(
                                scene_index=scene_idx,
                                scenes=project.scenes,
                                images=project.images,
                                character=project.character,
                                history=project.gemini_conversation_history,
                                extra_guidance=actions.get("guidance", ""),
                            )
                            project.images[scene_idx] = img
                        st.rerun()

    # Download panel
    render_image_download_panel(project.images, [s.title for s in project.scenes])

    # Navigation
    st.divider()
    approved_count = sum(1 for img in project.images if img.status == SceneStatus.APPROVED)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← Back to Script Input", key="step3_back"):
            project.current_step = 2
            st.rerun()
    with col_next:
        if st.button(
            f"Continue to Video Generation ({approved_count} approved) →",
            disabled=approved_count == 0,
            type="primary",
            key="step3_continue",
        ):
            # Initialize SceneVideo objects for all scenes
            project.videos = [
                SceneVideo(scene_index=i) for i in range(len(project.scenes))
            ]
            project.current_step = 4
            st.rerun()
