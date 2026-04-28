"""Welcome / onboarding screen.

Two paths:
  1. **Use admin keys** — a one-click button that loads the deployer's keys
     from Streamlit secrets (only shown when those secrets are configured).
     Anyone who clicks this is using the deployer's API quota.
  2. **Bring your own keys** — multi-provider form below. Each provider is
     optional; a visitor can pick whichever video backend they have access to.
"""

from __future__ import annotations

import streamlit as st

from config import get_admin_keys, has_admin_mode
from utils.credential_check import (
    validate_gemini_key,
    validate_kling_direct_keys,
    validate_replicate_token,
)


def render() -> None:
    st.markdown(
        """
        <div style="text-align:center;padding:1rem 0 0.25rem 0;">
          <div style="font-size:3rem;">🎬</div>
          <h1 style="margin:0.25rem 0;">Scene Studio</h1>
          <p style="color:#888;margin:0;">
            Style-consistent scene generation and short-video production.
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
            "1. **Pick a visual style** — text description, presets, or a style reference image.  \n"
            "2. **Paste a script** — Scene Studio breaks it into scenes.  \n"
            "3. **Generate on-style images** for every scene.  \n"
            "4. **Turn approved images into short videos** with Kling, Veo, Wan, or Seedance."
        )

    # ── Admin shortcut ──
    if has_admin_mode():
        with st.container(border=True):
            col_a, col_b = st.columns([3, 2])
            with col_a:
                st.markdown("**🔑 Use admin keys**")
                st.caption(
                    "One click and you're using the deployer's API keys. "
                    "Skip the BYOK form below."
                )
            with col_b:
                if st.button(
                    "Use admin keys",
                    type="primary",
                    use_container_width=True,
                    key="welcome_use_admin",
                ):
                    _apply_admin_keys()
                    st.rerun()

    # ── BYOK section ──
    st.markdown("### Bring your own API keys")
    st.caption(
        "Keys live only in your browser session — never stored, logged, or shared. "
        "Refresh the page and they're gone."
    )

    _render_gemini_card()
    _render_video_provider_cards()

    # ── Continue button ──
    st.divider()

    gem_present = bool(st.session_state.get("gemini_api_key", "").strip())
    gem_validated = st.session_state.get("gemini_key_status", {}).get("ok") is True

    col_left, col_right = st.columns([3, 2])
    with col_left:
        if not gem_present:
            st.info("Paste a Gemini key above (or click 'Use admin keys') to continue.")
        elif not gem_validated:
            st.warning(
                "Gemini key not tested yet. You can continue without testing, but you'll "
                "get a clearer error here than mid-generation."
            )
        else:
            video_ready = _any_video_provider_available()
            if video_ready:
                st.success("You're ready. Gemini key validated. A video provider is configured.")
            else:
                st.success(
                    "You're ready for Steps 1–3. Add a video provider below before Step 4 "
                    "(Veo works with just your Gemini key)."
                )

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

    # ── Footer ──
    st.caption(
        "Source: [github.com/dikshajgd/gen-ai](https://github.com/dikshajgd/gen-ai) · "
        "Built with Streamlit · "
        "Images by Gemini 2.5 Flash Image"
    )


# ── Cards ────────────────────────────────────────────────────────────


def _render_gemini_card() -> None:
    with st.container(border=True):
        col_head, col_status = st.columns([5, 2])
        with col_head:
            st.markdown("**Google Gemini** — required (analysis + image generation + Veo videos)")
            st.caption(
                "Free tier is enough to try it out. "
                "Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)."
            )
        with col_status:
            _render_badge(st.session_state.get("gemini_key_status"))

        current = st.session_state.get("gemini_api_key", "")
        new_val = st.text_input(
            "Gemini API key",
            value=current,
            type="password",
            key="welcome_gemini_input",
            label_visibility="collapsed",
            placeholder="AIza...",
        )
        if new_val != current:
            st.session_state["gemini_api_key"] = new_val
            st.session_state.pop("gemini_key_status", None)

        if st.button("Test Gemini key", key="welcome_test_gemini", disabled=not new_val.strip()):
            with st.spinner("Calling Gemini…"):
                ok, msg = validate_gemini_key(new_val)
            st.session_state["gemini_key_status"] = {"ok": ok, "msg": msg}
            st.rerun()


def _render_video_provider_cards() -> None:
    st.markdown("#### Video providers (optional — pick one or more)")
    st.caption(
        "You only need a video provider for Step 4. **Google Veo** uses your Gemini key — "
        "no extra setup needed."
    )

    # Kling Direct
    with st.container(border=True):
        col_head, col_status = st.columns([5, 2])
        with col_head:
            st.markdown("**Kling (direct API)** — Kling 2.6 Pro / 2 Master / 1.6 Pro")
            st.caption(
                "Latest Kling models. Apply for API access at "
                "[klingai.com/global](https://app.klingai.com/global) → API. "
                "You'll get an Access Key + Secret Key."
            )
        with col_status:
            _render_badge(st.session_state.get("kling_key_status"))

        access = st.session_state.get("kling_access_key", "")
        secret = st.session_state.get("kling_secret_key", "")
        new_access = st.text_input(
            "Kling Access Key",
            value=access,
            type="password",
            key="welcome_kling_access",
            placeholder="AccessKeyId",
        )
        new_secret = st.text_input(
            "Kling Secret Key",
            value=secret,
            type="password",
            key="welcome_kling_secret",
            placeholder="SecretKey",
        )
        if new_access != access or new_secret != secret:
            st.session_state["kling_access_key"] = new_access
            st.session_state["kling_secret_key"] = new_secret
            st.session_state.pop("kling_key_status", None)

        if st.button(
            "Test Kling keys",
            key="welcome_test_kling",
            disabled=not (new_access.strip() and new_secret.strip()),
        ):
            with st.spinner("Calling Kling…"):
                ok, msg = validate_kling_direct_keys(new_access, new_secret)
            st.session_state["kling_key_status"] = {"ok": ok, "msg": msg}
            st.rerun()

    # Replicate
    with st.container(border=True):
        col_head, col_status = st.columns([5, 2])
        with col_head:
            st.markdown("**Replicate** — Wan 2.1 / Seedance 1 Pro / Kling 2.1 Master")
            st.caption(
                "Single API token, instant signup. "
                "Get one at [replicate.com/account/api-tokens](https://replicate.com/account/api-tokens)."
            )
        with col_status:
            _render_badge(st.session_state.get("replicate_key_status"))

        token = st.session_state.get("replicate_api_token", "")
        new_token = st.text_input(
            "Replicate API token",
            value=token,
            type="password",
            key="welcome_replicate_token",
            label_visibility="collapsed",
            placeholder="r8_...",
        )
        if new_token != token:
            st.session_state["replicate_api_token"] = new_token
            st.session_state.pop("replicate_key_status", None)

        if st.button(
            "Test Replicate token",
            key="welcome_test_replicate",
            disabled=not new_token.strip(),
        ):
            with st.spinner("Calling Replicate…"):
                ok, msg = validate_replicate_token(new_token)
            st.session_state["replicate_key_status"] = {"ok": ok, "msg": msg}
            st.rerun()


# ── Helpers ──────────────────────────────────────────────────────────


def _render_badge(status: dict | None) -> None:
    if not status:
        st.markdown(
            "<div style='text-align:right;color:#888;'>Not tested</div>",
            unsafe_allow_html=True,
        )
        return
    if status.get("ok"):
        st.markdown(
            f"<div style='text-align:right;color:#1a7f37;'>✓ {status['msg']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='text-align:right;color:#c92a2a;'>✗ {status['msg']}</div>",
            unsafe_allow_html=True,
        )


def _apply_admin_keys() -> None:
    """Load admin keys into session state and dismiss the welcome screen."""
    admin = get_admin_keys()
    for k, v in admin.items():
        st.session_state[k] = v
    # Mark Gemini as validated so the continue button activates.
    if admin.get("gemini_api_key"):
        st.session_state["gemini_key_status"] = {"ok": True, "msg": "Admin key in use."}
    st.session_state["show_welcome"] = False


def _any_video_provider_available() -> bool:
    """True if at least one video provider has its credentials in session."""
    if st.session_state.get("gemini_api_key", "").strip():
        return True  # Veo works
    if st.session_state.get("replicate_api_token", "").strip():
        return True
    if (
        st.session_state.get("kling_access_key", "").strip()
        and st.session_state.get("kling_secret_key", "").strip()
    ):
        return True
    return False
