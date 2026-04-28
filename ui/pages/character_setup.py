"""Step 1: Visual Style — define the look that every scene will share.

Simplified from the original "creative brief" — no more character-identity
references. Just a style description plus an optional style reference image.
This sidesteps Gemini's safety blocks on real-person photos and matches how
most production AI art tools work (style transfer, not identity transfer).
"""

from __future__ import annotations

import base64

import streamlit as st

from core.constants import STYLE_PRESETS, SUPPORTED_IMAGE_TYPES
from core.models import CharacterProfile, ProjectState
from services.gemini_client import GeminiClient
from services.style_analyzer import StyleAnalyzer
from utils.image_utils import resize_image_if_needed


def render(project: ProjectState) -> None:
    st.header("Step 1: Visual Style")
    st.markdown(
        "Define the look that every scene will share. The character itself "
        "and what's happening in each scene comes from your script in Step 2."
    )

    # ── Section A: Style description ─────────────────────────────────
    st.subheader("Visual Style")

    selected_preset = st.pills(
        "Quick presets",
        options=STYLE_PRESETS,
        key="style_preset_pills",
    )

    default_style = st.session_state.get("_style_prompt", "")
    if selected_preset and selected_preset != st.session_state.get("_last_preset"):
        default_style = f"{selected_preset} style"
        st.session_state["_last_preset"] = selected_preset

    style_prompt = st.text_area(
        "Describe your desired visual style (or pick a preset above)",
        value=default_style,
        height=100,
        key="style_prompt_input",
        placeholder="e.g. Watercolor illustration with soft pastels, Studio Ghibli-inspired, warm amber light",
    )
    st.session_state["_style_prompt"] = style_prompt

    # ── Section B: Optional style reference ──────────────────────────
    st.subheader("Visual Style Reference (optional)")
    st.caption(
        "Upload an art piece, illustration, or screenshot whose style you want to match. "
        "Used as a visual anchor — Gemini will pick up the color palette, technique, and mood. "
        "Tip: avoid photos of real people; use illustrations or AI-generated art."
    )

    uploaded = st.file_uploader(
        "Style reference image",
        type=SUPPORTED_IMAGE_TYPES,
        accept_multiple_files=False,
        key="style_ref_upload",
        label_visibility="collapsed",
    )

    style_ref_bytes: bytes | None = None
    style_ref_name: str = ""
    if uploaded is not None:
        raw = uploaded.read()
        style_ref_bytes = resize_image_if_needed(raw)
        style_ref_name = uploaded.name
        col_preview, _spacer = st.columns([1, 2])
        with col_preview:
            st.image(style_ref_bytes, caption=style_ref_name, width=240)

    # ── Section C: Analyze ───────────────────────────────────────────
    st.divider()

    has_input = bool(style_prompt.strip() or style_ref_bytes)

    if st.button(
        "Analyze & Build Style Profile",
        type="primary",
        disabled=not has_input,
        key="analyze_brief_btn",
    ):
        api_key = st.session_state.get("gemini_api_key", "")
        if not api_key:
            st.error("Please set your Gemini API key first (sidebar → 🔑 Manage keys).")
            return

        with st.spinner("Analyzing your visual style..."):
            try:
                client = GeminiClient(api_key)
                analyzer = StyleAnalyzer(client)
                profile = analyzer.analyze_style(
                    style_prompt=style_prompt.strip(),
                    style_ref_bytes=style_ref_bytes,
                    style_ref_name=style_ref_name,
                )
                project.character = profile

                store = st.session_state.get("project_store")
                if store:
                    store.save(project)

                st.rerun()
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Style analysis failed")
                st.error(f"Analysis failed: {e}")

    # ── Section D: Results ───────────────────────────────────────────
    char = project.character
    if char and char.style_prompt_prefix:
        st.divider()
        st.subheader("Style Profile")

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

            if char.reference_image_b64:
                st.markdown("**Style Reference:**")
                st.image(base64.b64decode(char.reference_image_b64), width=240)

        with col_edit:
            st.markdown("**Style Prompt** (editable):")
            new_prefix = st.text_area(
                "Prepended to every scene prompt for visual consistency:",
                value=char.style_prompt_prefix,
                height=140,
                key="style_prefix_edit",
            )
            if new_prefix != char.style_prompt_prefix:
                char.style_prompt_prefix = new_prefix

    # ── Continue ─────────────────────────────────────────────────────
    st.divider()
    has_style = project.character is not None and bool(project.character.style_prompt_prefix)
    if st.button(
        "Continue to Script Input →",
        disabled=not has_style,
        type="primary",
        key="step1_continue",
    ):
        project.current_step = 2
        st.rerun()
