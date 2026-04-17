"""Configuration and environment variable management.

Resolution order for credentials:
  1. Streamlit secrets (`.streamlit/secrets.toml` locally or the Secrets UI on
     Streamlit Community Cloud).
  2. Process environment variables (including values loaded from `.env`).

Streamlit secrets take precedence so deployments can override local `.env` files
without code changes.
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


def get_gemini_api_key() -> str:
    return _resolve("GEMINI_API_KEY")


def get_kling_access_key() -> str:
    return _resolve("KLING_ACCESS_KEY")


def get_kling_secret_key() -> str:
    return _resolve("KLING_SECRET_KEY")


def get_data_dir() -> str:
    return os.path.expanduser(_resolve("SCENE_STUDIO_DATA_DIR", DEFAULT_DATA_DIR))
