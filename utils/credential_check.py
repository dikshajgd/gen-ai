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


def validate_kling_direct_keys(access_key: str, secret_key: str) -> Tuple[bool, str]:
    """Verify a Kling Direct (Open Platform) Access Key + Secret Key pair.

    We sign a JWT and call the user-info endpoint. A valid pair returns 200;
    invalid signing or wrong key returns 401/403.
    """
    if not access_key or not access_key.strip():
        return False, "Access Key is empty."
    if not secret_key or not secret_key.strip():
        return False, "Secret Key is empty."

    try:
        import jwt
        import requests
    except ImportError as exc:
        return False, f"Missing dependency: {exc}"

    import time

    now = int(time.time())
    try:
        token = jwt.encode(
            {"iss": access_key.strip(), "exp": now + 600, "nbf": now - 5},
            secret_key.strip(),
            algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT"},
        )
    except Exception as exc:
        return False, f"Failed to sign JWT: {exc}"

    # Hit the image2video listing endpoint (any authenticated GET works).
    try:
        resp = requests.get(
            "https://api-singapore.klingai.com/v1/videos/image2video",
            headers={"Authorization": f"Bearer {token}"},
            params={"pageNum": 1, "pageSize": 1},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach Kling: {exc}"

    if resp.status_code in (401, 403):
        return False, "Kling rejected these keys (unauthorized)."
    if resp.status_code == 200:
        try:
            data = resp.json()
            if data.get("code") == 0:
                return True, "Kling keys work."
            return False, f"Kling error: {data.get('message')}"
        except ValueError:
            return False, "Kling returned non-JSON."
    return False, f"Unexpected Kling response (HTTP {resp.status_code})."


def validate_replicate_token(api_token: str) -> Tuple[bool, str]:
    """Verify a Replicate API token by calling the account endpoint."""
    if not api_token or not api_token.strip():
        return False, "Token is empty."

    try:
        import requests
    except ImportError:
        return False, "requests package is not installed."

    try:
        resp = requests.get(
            "https://api.replicate.com/v1/account",
            headers={"Authorization": f"Token {api_token.strip()}"},
            timeout=8,
        )
    except requests.RequestException as exc:
        return False, f"Could not reach Replicate: {exc}"

    if resp.status_code in (401, 403):
        return False, "Replicate rejected this token."
    if resp.status_code == 200:
        return True, "Replicate token works."
    return False, f"Unexpected Replicate response (HTTP {resp.status_code})."
