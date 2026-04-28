"""Scene Studio - Character-consistent scene generation and video production."""

import sys
import os

# Ensure the app directory is on sys.path so sibling package imports work when
# launched by `streamlit run app.py` from any working directory.
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

import streamlit as st

from core.models import ProjectState
from config import (
    get_gemini_api_key,
    get_kling_access_key,
    get_kling_secret_key,
    get_replicate_api_token,
    get_data_dir,
)
from utils.logging import setup_logging
from utils.project_store import ProjectStore

setup_logging(get_data_dir())


def main():
    st.set_page_config(
        page_title="Scene Studio",
        page_icon="🎬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _init_session_state()

    project: ProjectState = st.session_state["project"]
    store: ProjectStore = st.session_state["project_store"]

    # Welcome / BYOK gate — shown on first visit (no Gemini key) or when the
    # user explicitly clicks "Manage keys" from the sidebar.
    if st.session_state.get("show_welcome", False):
        from ui.pages.welcome import render as render_welcome
        render_welcome()
        return

    # Sidebar
    with st.sidebar:
        st.title("Scene Studio")
        st.caption("Character-consistent scene generation")

        # Project name
        new_name = st.text_input(
            "Project Name",
            value=project.name,
            key="project_name_input",
            label_visibility="collapsed",
            placeholder="Untitled Project",
        )
        if new_name != project.name:
            project.name = new_name

        st.divider()

        # Step indicators
        steps = [
            ("1. Visual Style", 1),
            ("2. Script Input", 2),
            ("3. Image Generation", 3),
            ("4. Video Generation", 4),
        ]
        for label, step_num in steps:
            if step_num < project.current_step:
                icon = "✅"
            elif step_num == project.current_step:
                icon = "▶️"
            else:
                icon = "⬜"

            if st.sidebar.button(
                f"{icon} {label}",
                key=f"nav_step_{step_num}",
                disabled=step_num > project.current_step,
                use_container_width=True,
            ):
                project.current_step = step_num
                st.rerun()

        st.divider()

        # Project History
        with st.expander("Project History"):
            history = store.list_projects()
            if history:
                for meta in history[:20]:
                    col_thumb, col_info, col_actions = st.columns([1, 3, 1])
                    with col_thumb:
                        if meta.thumbnail_b64:
                            try:
                                import base64 as _b64
                                st.image(_b64.b64decode(meta.thumbnail_b64), width=48)
                            except Exception:
                                st.markdown("🎬")
                        else:
                            st.markdown("🎬")
                    with col_info:
                        label = meta.name or "Untitled"
                        date_str = meta.updated_at.strftime("%b %d")
                        stats = []
                        if meta.scene_count:
                            stats.append(f"{meta.scene_count} scene{'s' if meta.scene_count != 1 else ''}")
                        if meta.approved_images:
                            stats.append(f"🖼 {meta.approved_images}")
                        if meta.approved_videos:
                            stats.append(f"🎞 {meta.approved_videos}")
                        stats_line = " · ".join(stats) if stats else "empty"
                        st.markdown(f"**{label}**")
                        st.caption(f"{date_str} · {stats_line}")
                    with col_actions:
                        if st.button("Load", key=f"load_{meta.project_id}", use_container_width=True):
                            loaded = store.load(meta.project_id)
                            st.session_state["project"] = loaded
                            st.rerun()
                        if st.button("🗑", key=f"del_{meta.project_id}", use_container_width=True):
                            store.delete(meta.project_id)
                            st.rerun()
            else:
                st.caption("No saved projects yet.")

        # Save / New buttons
        col_save, col_new = st.columns(2)
        with col_save:
            if st.button("💾 Save", key="save_btn", use_container_width=True):
                store.save(project)
                st.toast("Project saved!")
        with col_new:
            if st.button("🗑️ New", key="reset_btn", use_container_width=True):
                # Save current project if it has content
                if project.character or project.scenes:
                    store.save(project)
                st.session_state["project"] = ProjectState()
                st.rerun()

        from ui.components.download_panel import render_full_project_download
        render_full_project_download(project, key_suffix="_sidebar")

        st.divider()

        # API key status
        st.subheader("API Keys")
        gemini_key = st.session_state.get("gemini_api_key", "")
        kling_access = st.session_state.get("kling_access_key", "")

        st.markdown(f"Gemini: {'✅ Set' if gemini_key else '❌ Missing'}")
        st.markdown(f"Video (fal.ai): {'✅ Set' if kling_access else '⚪️ Optional'}")
        st.caption("Keys stay in your browser session only.")

        if st.button("🔑 Manage keys", key="sidebar_manage_keys", use_container_width=True):
            st.session_state["show_welcome"] = True
            st.rerun()

    # Main content - render current step
    if project.current_step == 1:
        from ui.pages.character_setup import render
        render(project)
    elif project.current_step == 2:
        from ui.pages.script_input import render
        render(project)
    elif project.current_step == 3:
        from ui.pages.image_generation import render
        render(project)
    elif project.current_step == 4:
        from ui.pages.video_generation import render
        render(project)


def _init_session_state():
    """Initialize session state with defaults."""
    if "project_store" not in st.session_state:
        st.session_state["project_store"] = ProjectStore(get_data_dir())

    if "project" not in st.session_state:
        st.session_state["project"] = ProjectState()

    if "gemini_api_key" not in st.session_state:
        st.session_state["gemini_api_key"] = get_gemini_api_key()

    if "kling_access_key" not in st.session_state:
        st.session_state["kling_access_key"] = get_kling_access_key()

    if "kling_secret_key" not in st.session_state:
        st.session_state["kling_secret_key"] = get_kling_secret_key()

    if "replicate_api_token" not in st.session_state:
        st.session_state["replicate_api_token"] = get_replicate_api_token()

    # Show the welcome/BYOK gate on first visit if no Gemini key was injected
    # via secrets/env. Once the user dismisses welcome, it stays dismissed
    # until they click "Manage keys" in the sidebar.
    if "show_welcome" not in st.session_state:
        st.session_state["show_welcome"] = not st.session_state["gemini_api_key"]


if __name__ == "__main__":
    main()
