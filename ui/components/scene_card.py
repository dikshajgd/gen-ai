"""Reusable scene card component for displaying images and videos."""

from __future__ import annotations

import base64
import streamlit as st

from core.models import SceneImage, SceneVideo, SceneStatus, VideoStatus


def render_image_card(
    scene_index: int,
    title: str,
    image: SceneImage,
    key_prefix: str = "img",
) -> dict[str, bool | str]:
    """Render a scene image card with status-dependent controls.

    Returns dict of actions: {"approve": bool, "reject": bool, "regenerate": bool, "guidance": str, "undo": bool}
    """
    actions = {"approve": False, "reject": False, "regenerate": False, "guidance": "", "undo": False}

    with st.container(border=True):
        st.markdown(f"**{title}**")

        if image.status == SceneStatus.PENDING:
            st.markdown(
                "<div style='background:#f0f0f0;border-radius:6px;height:160px;"
                "display:flex;align-items:center;justify-content:center;color:#999;"
                "font-size:14px;'>⏳ Awaiting generation</div>",
                unsafe_allow_html=True,
            )

        elif image.status == SceneStatus.GENERATING:
            st.markdown(
                "<div style='background:#e8f0fe;border-radius:6px;height:160px;"
                "display:flex;align-items:center;justify-content:center;color:#4169e1;"
                "font-size:14px;'>🎨 Generating…</div>",
                unsafe_allow_html=True,
            )

        elif image.status in (SceneStatus.GENERATED, SceneStatus.APPROVED, SceneStatus.REJECTED):
            if image.image_b64:
                st.image(base64.b64decode(image.image_b64), width="stretch")

            # Undo — swap back to the previous version if one exists.
            if image.history_b64:
                depth = len(image.history_b64)
                if st.button(
                    f"↶ Previous version ({depth})",
                    key=f"{key_prefix}_undo_{scene_index}",
                    help="Swap back to the image from before the last regenerate.",
                ):
                    actions["undo"] = True

            if image.status == SceneStatus.APPROVED:
                st.success("Approved")
                # Download button
                if image.image_b64:
                    st.download_button(
                        "Download",
                        data=base64.b64decode(image.image_b64),
                        file_name=f"scene_{scene_index + 1}.png",
                        mime="image/png",
                        key=f"{key_prefix}_dl_{scene_index}",
                    )

            elif image.status == SceneStatus.GENERATED:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve", key=f"{key_prefix}_approve_{scene_index}", type="primary"):
                        actions["approve"] = True
                with col2:
                    if st.button("Reject", key=f"{key_prefix}_reject_{scene_index}"):
                        actions["reject"] = True

            elif image.status == SceneStatus.REJECTED:
                st.warning("Rejected")
                guidance = st.text_input(
                    "Guidance for regeneration:",
                    key=f"{key_prefix}_guidance_{scene_index}",
                    placeholder="e.g., Make the character face the camera",
                )
                if st.button("Regenerate", key=f"{key_prefix}_regen_{scene_index}"):
                    actions["regenerate"] = True
                    actions["guidance"] = guidance

        elif image.status == SceneStatus.FAILED:
            st.error(f"Failed: {image.error_message}")
            st.caption(f"Attempts: {image.generation_attempts}/{image.max_attempts}")
            if st.button("Retry", key=f"{key_prefix}_retry_{scene_index}"):
                actions["regenerate"] = True

    return actions


def render_video_card(
    scene_index: int,
    title: str,
    image: SceneImage,
    video: SceneVideo,
    key_prefix: str = "vid",
) -> dict[str, bool]:
    """Render a scene video card with status-dependent controls.

    Returns dict of actions: {"approve": bool, "reject": bool, "retry": bool}
    """
    actions = {"approve": False, "reject": False, "retry": False}

    with st.container(border=True):
        st.markdown(f"**{title}**")

        # Show source image thumbnail
        if image.image_b64:
            st.image(base64.b64decode(image.image_b64), width=150, caption="Source")

        if video.status == VideoStatus.NOT_STARTED:
            st.markdown(":gray[Ready for video generation]")

        elif video.status in (VideoStatus.SUBMITTING, VideoStatus.PROCESSING):
            st.info(f"Status: {video.status.value}")
            if video.submitted_at:
                elapsed = (
                    __import__("datetime").datetime.now() - video.submitted_at
                ).total_seconds()
                st.caption(f"Elapsed: {int(elapsed)}s")

        elif video.status in (VideoStatus.COMPLETED, VideoStatus.APPROVED, VideoStatus.REJECTED):
            if video.video_b64:
                st.video(base64.b64decode(video.video_b64))

            if video.status == VideoStatus.APPROVED:
                st.success("Approved")
                if video.video_b64:
                    st.download_button(
                        "Download Video",
                        data=base64.b64decode(video.video_b64),
                        file_name=f"scene_{scene_index + 1}.mp4",
                        mime="video/mp4",
                        key=f"{key_prefix}_dl_{scene_index}",
                    )

            elif video.status == VideoStatus.COMPLETED:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve", key=f"{key_prefix}_approve_{scene_index}", type="primary"):
                        actions["approve"] = True
                with col2:
                    if st.button("Reject", key=f"{key_prefix}_reject_{scene_index}"):
                        actions["reject"] = True

            elif video.status == VideoStatus.REJECTED:
                st.warning("Rejected")
                if st.button("Retry", key=f"{key_prefix}_retry_{scene_index}"):
                    actions["retry"] = True

        elif video.status == VideoStatus.FAILED:
            st.error(f"Failed: {video.error_message}")
            st.caption(f"Attempts: {video.generation_attempts}/{video.max_attempts}")
            if st.button("Retry", key=f"{key_prefix}_retry_{scene_index}"):
                actions["retry"] = True

    return actions
