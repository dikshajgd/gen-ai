"""Configuration and environment variable management.

Resolution order for credentials:
  1. Streamlit secrets (`.streamlit/secrets.toml` locally or the Secrets UI on
     Streamlit Community Cloud).
  2. Process environment variables (including values loaded from `.env`).

Streamlit secrets take precedence so deployments can override local `.env` files
without code changes.

Admin keys (ADMIN_*) are a separate set, used by the "Use admin keys" button
on the welcome screen. They let the deployer offer free trials on their own
quota. Only `ADMIN_GEMINI_API_KEY` is required to enable the button — the rest
are provider-specific and optional.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

from core.constants import DEFAULT_DATA_DIR

load_dotenv()


def _from_streamlit_secrets(key: str) -> Optional[str]:
    try:
        import streamlit as st
    except ImportError:
        return None
    try:
        value = st.secrets.get(key)
    except Exception:
        return None
    return str(value) if value else None


def _resolve(key: str, default: str = "") -> str:
    return _from_streamlit_secrets(key) or os.getenv(key, default)


# ── User keys (BYOK form) ────────────────────────────────────────────


def get_gemini_api_key() -> str:
    return _resolve("GEMINI_API_KEY")


def get_kling_access_key() -> str:
    return _resolve("KLING_ACCESS_KEY")


def get_kling_secret_key() -> str:
    return _resolve("KLING_SECRET_KEY")


def get_replicate_api_token() -> str:
    return _resolve("REPLICATE_API_TOKEN")


def get_data_dir() -> str:
    return os.path.expanduser(_resolve("SCENE_STUDIO_DATA_DIR", DEFAULT_DATA_DIR))


# ── Admin keys ───────────────────────────────────────────────────────


def get_admin_keys() -> dict[str, str]:
    """Return a dict of admin keys present in secrets/env.

    The welcome screen shows the 'Use admin keys' button only when at least
    `gemini_api_key` is present. To disable admin mode in production, simply
    delete the `ADMIN_GEMINI_API_KEY` secret from Streamlit Cloud — the
    button disappears on the next page load. No redeploy needed.
    """
    keys = {
        "gemini_api_key": _resolve("ADMIN_GEMINI_API_KEY"),
        "kling_access_key": _resolve("ADMIN_KLING_ACCESS_KEY"),
        "kling_secret_key": _resolve("ADMIN_KLING_SECRET_KEY"),
        "replicate_api_token": _resolve("ADMIN_REPLICATE_API_TOKEN"),
    }
    return {k: v for k, v in keys.items() if v}


def has_admin_mode() -> bool:
    """True if the deployer has configured admin keys (at least Gemini)."""
    return bool(_resolve("ADMIN_GEMINI_API_KEY"))
