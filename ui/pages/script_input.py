"""Step 2: Script input, parsing, and prompt generation."""

from __future__ import annotations

import streamlit as st

from core.models import ProjectState, Scene, SceneImage
from core.constants import MAX_SCRIPT_LENGTH, MAX_SCENES
from services.gemini_client import GeminiClient
from services.script_parser import ScriptParser


def render(project: ProjectState) -> None:
    st.header("Step 2: Script Input")
    st.markdown("Paste your script below and parse it into scenes.")

    # Script text area
    script_text = st.text_area(
        "Paste your script:",
        height=250,
        max_chars=MAX_SCRIPT_LENGTH,
        key="script_text",
        placeholder=(
            "SCENE 1: The forest clearing\n"
            "Our hero stands at the edge of a mystical forest...\n\n"
            "SCENE 2: The ancient temple\n"
            "Deep within the forest, an ancient temple reveals itself..."
        ),
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Parse Script", type="primary", key="parse_btn"):
            if not script_text.strip():
                st.error("Please enter a script first.")
                return

            api_key = st.session_state.get("gemini_api_key", "")
            gemini = GeminiClient(api_key) if api_key else None
            parser = ScriptParser(gemini)

            with st.spinner("Parsing script..."):
                scenes = parser.parse(script_text)
                if not scenes:
                    st.error("Could not parse any scenes. Try using scene headers (e.g., 'SCENE 1:').")
                    return
                if len(scenes) > MAX_SCENES:
                    scenes = scenes[:MAX_SCENES]
                    st.warning(f"Trimmed to {MAX_SCENES} scenes (maximum).")

            with st.spinner("Generating image prompts..."):
                if project.character:
                    scenes = parser.generate_image_prompts(scenes, project.character)

            project.scenes = scenes

            # Auto-save
            store = st.session_state.get("project_store")
            if store:
                store.save(project)

            st.rerun()

    # Display and edit parsed scenes
    if project.scenes:
        st.divider()
        st.subheader(f"Scenes ({len(project.scenes)})")

        scenes_to_remove = []
        for i, scene in enumerate(project.scenes):
            with st.expander(f"Scene {i + 1}: {scene.title}", expanded=(i < 3)):
                new_title = st.text_input(
                    "Title:",
                    value=scene.title,
                    key=f"scene_title_{i}",
                )
                new_desc = st.text_area(
                    "Description:",
                    value=scene.description,
                    height=80,
                    key=f"scene_desc_{i}",
                )
                new_prompt = st.text_area(
                    "Image Prompt:",
                    value=scene.image_prompt,
                    height=80,
                    key=f"scene_prompt_{i}",
                )
                new_style_override = st.text_input(
                    "Style override (optional):",
                    value=scene.style_override,
                    key=f"scene_style_override_{i}",
                    placeholder="Leave blank to use the project's style. Example: 'sepia flashback, film grain'.",
                    help="Overrides the global character style for this scene only. Useful for flashbacks or dream sequences.",
                )

                # Update in-place
                scene.title = new_title
                scene.description = new_desc
                scene.image_prompt = new_prompt
                scene.style_override = new_style_override

                if st.button("Remove Scene", key=f"remove_scene_{i}"):
                    scenes_to_remove.append(i)

        # Remove scenes marked for deletion
        if scenes_to_remove:
            project.scenes = [s for i, s in enumerate(project.scenes) if i not in scenes_to_remove]
            # Re-index
            for i, s in enumerate(project.scenes):
                s.index = i
            st.rerun()

        # Add scene manually
        st.divider()
        if st.button("+ Add Scene Manually", key="add_scene_btn"):
            new_idx = len(project.scenes)
            project.scenes.append(
                Scene(index=new_idx, title=f"Scene {new_idx + 1}", description="", image_prompt="")
            )
            st.rerun()

    # Continue button
    st.divider()
    has_scenes = len(project.scenes) > 0
    if st.button(
        "Continue to Image Generation →",
        disabled=not has_scenes,
        type="primary",
        key="step2_continue",
    ):
        # Initialize SceneImage objects
        project.images = [SceneImage(scene_index=i) for i in range(len(project.scenes))]
        project.current_step = 3
        st.rerun()

    # Back button
    if st.button("← Back to Character Setup", key="step2_back"):
        project.current_step = 1
        st.rerun()
