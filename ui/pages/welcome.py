"""Welcome / BYOK gate — shown when no Gemini key is present in session state.

Visitors to the public deployment land here first. They paste their own API
keys, which live only in `st.session_state` for the duration of the browser
session — nothing is persisted server-side or logged.
"""

from __future__ import annotations

import streamlit as st

from utils.credential_check import validate_gemini_key, validate_fal_key


def render() -> None:
    st.markdown(
        """
        <div style="text-align:center;padding:1rem 0 0.25rem 0;">
          <div style="font-size:3rem;">🎬</div>
          <h1 style="margin:0.25rem 0;">Scene Studio</h1>
          <p style="color:#888;margin:0;">
            Character-consistent scene generation and short-video production.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── What this app does ──
    with st.container(border=True):
        st.markdown("#### What you can do here")
        st.markdown(
            "1. **Describe your character** and upload a reference image.  \n"
            "2. **Paste a script** — Scene Studio breaks it into scenes.  \n"
            "3. **Generate on-model images** for every scene.  \n"
            "4. **Turn approved images into short videos.**"
        )

    # ── BYOK section ──
    st.markdown("### Bring your own API keys")
    st.caption(
        "This is a public demo. To keep it free and safe for everyone, you provide "
        "your own keys. **They live only in your browser session** — never stored, "
        "logged, or shared. Refresh the page and they're gone."
    )

    gem_key = st.session_state.get("gemini_api_key", "")
    fal_key = st.session_state.get("kling_access_key", "")

    # ── Gemini (required) ──
    with st.container(border=True):
        col_head, col_status = st.columns([5, 2])
        with col_head:
            st.markdown("**Google Gemini** — required for analysis + image generation")
            st.caption(
                "Free tier is enough to try it out. "
                "Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)."
            )
        with col_status:
            _render_key_badge("gemini")

        gem_input = st.text_input(
            "Gemini API key",
            value=gem_key,
            type="password",
            key="welcome_gemini_input",
            label_visibility="collapsed",
            placeholder="AIza...",
        )
        if gem_input != gem_key:
            st.session_state["gemini_api_key"] = gem_input
            st.session_state.pop("gemini_key_status", None)

        if st.button(
            "Test Gemini key",
            key="welcome_test_gemini",
            disabled=not gem_input.strip(),
            use_container_width=False,
        ):
            with st.spinner("Calling Gemini…"):
                ok, msg = validate_gemini_key(gem_input)
            st.session_state["gemini_key_status"] = {"ok": ok, "msg": msg}
            st.rerun()

    # ── fal.ai (optional, needed at step 4) ──
    with st.container(border=True):
        col_head, col_status = st.columns([5, 2])
        with col_head:
            st.markdown("**fal.ai** — optional, required for video generation (Step 4)")
            st.caption(
                "Pay-as-you-go (~$0.35 per 5-second Kling 2.6 clip at the time of writing). "
                "You can skip this now and add it before Step 4. "
                "Get one at [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys)."
            )
        with col_status:
            _render_key_badge("fal")

        fal_input = st.text_input(
            "fal.ai API key",
            value=fal_key,
            type="password",
            key="welcome_fal_input",
            label_visibility="collapsed",
            placeholder="<uuid>:<hex>",
        )
        if fal_input != fal_key:
            st.session_state["kling_access_key"] = fal_input
            st.session_state.pop("fal_key_status", None)

        if st.button(
            "Test fal.ai key",
            key="welcome_test_fal",
            disabled=not fal_input.strip(),
        ):
            with st.spinner("Calling fal.ai…"):
                ok, msg = validate_fal_key(fal_input)
            st.session_state["fal_key_status"] = {"ok": ok, "msg": msg}
            st.rerun()

    # ── Continue button ──
    st.divider()

    gem_validated = st.session_state.get("gemini_key_status", {}).get("ok") is True
    gem_present = bool(st.session_state.get("gemini_api_key", "").strip())

    col_left, col_right = st.columns([3, 2])
    with col_left:
        if not gem_present:
            st.info("Paste a Gemini key above to continue.")
        elif not gem_validated:
            st.warning(
                "Key not tested yet. You can continue without testing, but you'll "
                "get a clearer error here than mid-generation."
            )
        else:
            st.success("You're ready. Gemini key validated.")

    with col_right:
        if st.button(
            "Continue to Scene Studio →",
            type="primary",
            disabled=not gem_present,
            use_container_width=True,
            key="welcome_continue",
        ):
            st.session_state["show_welcome"] = False
            st.rerun()

    # ── Tiny footer ──
    st.caption(
        "Source: [github.com](https://github.com) · "
        "Built with Streamlit · "
        "Images by Gemini 2.5 Flash Image · Video by Kling 2.6 Pro via fal.ai"
    )


def _render_key_badge(which: str) -> None:
    """Show a small colored badge reflecting validation state."""
    status_key = "gemini_key_status" if which == "gemini" else "fal_key_status"
    status = st.session_state.get(status_key)
    if not status:
        st.markdown(
            "<div style='text-align:right;color:#888;'>Not tested</div>",
            unsafe_allow_html=True,
        )
        return
    if status["ok"]:
        st.markdown(
            f"<div style='text-align:right;color:#1a7f37;'>✓ {status['msg']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='text-align:right;color:#c92a2a;'>✗ {status['msg']}</div>",
            unsafe_allow_html=True,
        )
