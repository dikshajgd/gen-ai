"""Lightweight API-key validation helpers for the BYOK welcome flow.

Each function returns (ok: bool, message: str). Messages are user-facing.
"""

from __future__ import annotations

from typing import Tuple


def validate_gemini_key(api_key: str) -> Tuple[bool, str]:
    """Verify a Gemini key by listing models — a cheap authenticated call."""
    if not api_key or not api_key.strip():
        return False, "Key is empty."

    try:
        from google import genai
    except ImportError:
        return False, "google-genai package is not installed."

    try:
        client = genai.Client(api_key=api_key.strip())
        # Pulling a single model via pager is enough to validate auth without
        # burning tokens on generation.
        models_iter = client.models.list()
        next(iter(models_iter), None)
        return True, "Gemini key works."
    except Exception as exc:
        detail = str(exc)
        if "API_KEY_INVALID" in detail or "401" in detail or "UNAUTHENTICATED" in detail:
            return False, "Gemini rejected this key (invalid or expired)."
        if "PERMISSION_DENIED" in detail or "403" in detail:
            return False, "Gemini key lacks permission — check API access on the key."
        return False, f"Gemini validation failed: {detail[:180]}"


def validate_fal_key(api_key: str) -> Tuple[bool, str]:
    """Verify a fal.ai key.

    fal.ai does not expose a cheap whoami endpoint, so we hit the status
    endpoint with a dummy request id. A valid key returns 404 (not found);
    an invalid key returns 401/403.
    """
    if not api_key or not api_key.strip():
        return False, "Key is empty."

    try:
        import requests
    except ImportError:
        return False, "requests package is not installed."

    key = api_key.strip()
    # fal.ai keys are typically "<uuid>:<hex>" — reject obvious junk early.
    if len(key) < 20:
        return False, "Key looks too short to be a fal.ai key."

    try:
        resp = requests.get(
            "https://queue.fal.run/fal-ai/kling-video/requests/00000000-0000-0000-0000-000000000000/status",
            headers={"Authorization": f"Key {key}"},
            timeout=8,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach fal.ai: {exc}"

    if resp.status_code in (401, 403):
        return False, "fal.ai rejected this key (unauthorized)."
    if resp.status_code in (200, 202, 404, 422):
        # 404 = request-id doesn't exist but auth was accepted.
        # 422 = malformed request-id but auth was accepted.
        return True, "fal.ai key works."
    return False, f"Unexpected fal.ai response (HTTP {resp.status_code})."
