"""Step 1: Creative Brief — prompt, reference images, and style definition."""

from __future__ import annotations

import streamlit as st

from core.constants import MAX_REFERENCE_IMAGES, STYLE_PRESETS, SUPPORTED_IMAGE_TYPES
from core.models import ProjectState
from services.gemini_client import GeminiClient
from services.style_analyzer import StyleAnalyzer
from utils.image_utils import resize_image_if_needed


def render(project: ProjectState) -> None:
    st.header("Step 1: Creative Brief")
    st.markdown(
        "Describe what you want to create, upload reference images, and define your visual style."
    )

    # ── Section A: Creative Prompt ──────────────────────────────────────
    st.subheader("What do you want to create?")
    creative_prompt = st.text_area(
        "Describe your story, character, or concept",
        value=st.session_state.get("_creative_prompt", ""),
        height=120,
        key="creative_prompt_input",
        placeholder="e.g. A brave young girl with red hair exploring an enchanted forest...",
    )
    st.session_state["_creative_prompt"] = creative_prompt

    # ── Section B: Reference Images ─────────────────────────────────────
    st.subheader("Reference Images")
    st.caption(f"Upload up to {MAX_REFERENCE_IMAGES} images for reference or editing.")

    uploaded_files = st.file_uploader(
        "Upload reference images",
        type=SUPPORTED_IMAGE_TYPES,
        accept_multiple_files=True,
        key="ref_images_upload",
    )

    # Process uploaded files
    image_bytes_list: list[bytes] = []
    image_names: list[str] = []
    if uploaded_files:
        for f in uploaded_files[:MAX_REFERENCE_IMAGES]:
            raw = f.read()
            resized = resize_image_if_needed(raw)
            image_bytes_list.append(resized)
            image_names.append(f.name)

        # Display uploaded images in a row
        cols = st.columns(min(len(image_bytes_list), 4))
        for idx, img_bytes in enumerate(image_bytes_list):
            with cols[idx % len(cols)]:
                st.image(img_bytes, caption=image_names[idx], use_container_width=True)

        if len(uploaded_files) > MAX_REFERENCE_IMAGES:
            st.warning(f"Only the first {MAX_REFERENCE_IMAGES} images will be used.")

    # ── Section C: Style Definition ─────────────────────────────────────
    st.subheader("Visual Style")

    # Style presets
    selected_preset = st.pills(
        "Quick presets",
        options=STYLE_PRESETS,
        key="style_preset_pills",
    )

    # Initialize style text from preset or previous value
    default_style = st.session_state.get("_style_prompt", "")
    if selected_preset and selected_preset != st.session_state.get("_last_preset"):
        default_style = f"{selected_preset} style"
        st.session_state["_last_preset"] = selected_preset

    style_prompt = st.text_area(
        "Describe your desired visual style (or pick a preset above)",
        value=default_style,
        height=80,
        key="style_prompt_input",
        placeholder="e.g. Watercolor illustration with soft pastels, Studio Ghibli-inspired",
    )
    st.session_state["_style_prompt"] = style_prompt

    # ── Section D: Analyze Button ───────────────────────────────────────
    st.divider()

    has_input = bool(creative_prompt.strip() or image_bytes_list or style_prompt.strip())

    if st.button(
        "Analyze & Build Profile",
        type="primary",
        disabled=not has_input,
        key="analyze_brief_btn",
    ):
        api_key = st.session_state.get("gemini_api_key", "")
        if not api_key:
            st.error("Please set your Gemini API key in Settings.")
            return

        with st.spinner("Analyzing your creative brief..."):
            try:
                client = GeminiClient(api_key)
                analyzer = StyleAnalyzer(client)
                profile = analyzer.analyze_brief(
                    creative_prompt=creative_prompt.strip(),
                    image_bytes_list=image_bytes_list or None,
                    style_prompt=style_prompt.strip(),
                    image_names=image_names,
                )
                project.character = profile

                # Auto-save
                store = st.session_state.get("project_store")
                if store:
                    store.save(project)

                st.rerun()
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Creative-brief analysis failed")
                st.error(f"Analysis failed: {e}")

    # ── Section E: Results ──────────────────────────────────────────────
    char = project.character
    if char and char.style_prompt_prefix:
        st.divider()
        st.subheader("Analysis Results")

        col_info, col_edit = st.columns([1, 1])

        with col_info:
            if char.art_style:
                st.markdown(f"**Art Style:** {char.art_style}")

            if char.color_palette:
                st.markdown("**Color Palette:**")
                palette_html = " ".join(
                    f'<span style="background-color:{c};padding:4px 12px;'
                    f'border-radius:4px;margin:2px;color:white;font-size:12px;">{c}</span>'
                    for c in char.color_palette
                )
                st.markdown(palette_html, unsafe_allow_html=True)

            if char.character_description:
                st.markdown("**Description:**")
                st.markdown(char.character_description)

            # Reference images gallery
            if char.reference_images_b64:
                st.markdown("**Reference Images:**")
                gallery_cols = st.columns(min(len(char.reference_images_b64), 4))
                for idx, img_b64 in enumerate(char.reference_images_b64):
                    import base64
                    with gallery_cols[idx % len(gallery_cols)]:
                        img_bytes = base64.b64decode(img_b64)
                        name = char.reference_image_names[idx] if idx < len(char.reference_image_names) else f"Image {idx + 1}"
                        st.image(img_bytes, caption=name, use_container_width=True)

        with col_edit:
            st.markdown("**Style Prompt Prefix** (editable):")
            new_prefix = st.text_area(
                "This prefix is prepended to every scene prompt for consistency:",
                value=char.style_prompt_prefix,
                height=120,
                key="style_prefix_edit",
            )
            if new_prefix != char.style_prompt_prefix:
                char.style_prompt_prefix = new_prefix

    # ── Continue Button ─────────────────────────────────────────────────
    st.divider()
    has_character = project.character is not None and bool(
        project.character.style_prompt_prefix or project.character.character_description
    )
    if st.button(
        "Continue to Script Input \u2192",
        disabled=not has_character,
        type="primary",
        key="step1_continue",
    ):
        project.current_step = 2
        st.rerun()
