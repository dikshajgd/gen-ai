"""Registry of video providers + their offered models.

The catalog is the single source of truth for the Step 4 UI dropdown.
Each entry: (provider_id, model_id, label_for_UI).
"""

from __future__ import annotations

from typing import Iterable

from config import (
    get_gemini_api_key,
    get_kling_access_key,
    get_kling_secret_key,
    get_replicate_api_token,
)
from services.video_providers.base import VideoProvider, VideoProviderError
from services.video_providers.kling_direct import (
    KlingDirectProvider,
    MODEL_KLING_2_6_PRO,
    MODEL_KLING_2_MASTER,
    MODEL_KLING_1_6_PRO,
)
from services.video_providers.replicate_provider import (
    ReplicateProvider,
    MODEL_WAN_2_1,
    MODEL_SEEDANCE_1_PRO,
    MODEL_KLING_2_1_MASTER,
)
from services.video_providers.veo_provider import (
    VeoProvider,
    MODEL_VEO_3,
    MODEL_VEO_3_FAST,
    MODEL_VEO_2,
)


PROVIDER_KLING_DIRECT = "kling_direct"
PROVIDER_REPLICATE = "replicate"
PROVIDER_VEO = "veo"


# (provider_id, model_id, ui_label, notes_for_user)
PROVIDER_CATALOG: list[tuple[str, str, str, str]] = [
    # Kling Direct — needs Access Key + Secret Key
    (PROVIDER_KLING_DIRECT, MODEL_KLING_2_6_PRO, "Kling 2.6 Pro (direct)", "Latest Kling, JWT auth"),
    (PROVIDER_KLING_DIRECT, MODEL_KLING_2_MASTER, "Kling 2 Master (direct)", "JWT auth"),
    (PROVIDER_KLING_DIRECT, MODEL_KLING_1_6_PRO, "Kling 1.6 Pro (direct)", "JWT auth"),

    # Google Veo — uses the existing Gemini key
    (PROVIDER_VEO, MODEL_VEO_3_FAST, "Veo 3 Fast (Gemini key)", "Cheaper, 8s clips"),
    (PROVIDER_VEO, MODEL_VEO_3, "Veo 3 (Gemini key)", "Highest quality"),
    (PROVIDER_VEO, MODEL_VEO_2, "Veo 2 (Gemini key)", "Stable fallback"),

    # Replicate — single API token
    (PROVIDER_REPLICATE, MODEL_WAN_2_1, "Wan 2.1 I2V (Replicate)", "Open-weight"),
    (PROVIDER_REPLICATE, MODEL_SEEDANCE_1_PRO, "Seedance 1 Pro (Replicate)", "ByteDance"),
    (PROVIDER_REPLICATE, MODEL_KLING_2_1_MASTER, "Kling 2.1 Master (Replicate)", "Easier signup"),
]


# Default selection when no project preference exists yet.
DEFAULT_PROVIDER_MODEL: tuple[str, str] = (PROVIDER_VEO, MODEL_VEO_3_FAST)


def models_for_provider(provider_id: str) -> Iterable[tuple[str, str]]:
    """Yield (model_id, label) pairs for the given provider."""
    for pid, mid, label, _notes in PROVIDER_CATALOG:
        if pid == provider_id:
            yield (mid, label)


def get_provider(provider_id: str) -> VideoProvider:
    """Construct a provider, sourcing credentials from Streamlit secrets / env."""
    if provider_id == PROVIDER_KLING_DIRECT:
        access = get_kling_access_key().strip()
        secret = get_kling_secret_key().strip()
        if not access or not secret:
            raise VideoProviderError(
                "Kling Direct needs KLING_ACCESS_KEY and KLING_SECRET_KEY in app secrets."
            )
        return KlingDirectProvider(access_key=access, secret_key=secret)

    if provider_id == PROVIDER_REPLICATE:
        token = get_replicate_api_token().strip()
        if not token:
            raise VideoProviderError(
                "Replicate needs REPLICATE_API_TOKEN in app secrets."
            )
        return ReplicateProvider(api_token=token)

    if provider_id == PROVIDER_VEO:
        key = get_gemini_api_key().strip()
        if not key:
            raise VideoProviderError("Veo needs GEMINI_API_KEY in app secrets.")
        return VeoProvider(api_key=key)

    raise VideoProviderError(f"Unknown provider id: {provider_id!r}")


def is_provider_available(provider_id: str) -> bool:
    """True if app secrets / env contain the credentials this provider needs."""
    if provider_id == PROVIDER_KLING_DIRECT:
        return bool(get_kling_access_key().strip() and get_kling_secret_key().strip())
    if provider_id == PROVIDER_REPLICATE:
        return bool(get_replicate_api_token().strip())
    if provider_id == PROVIDER_VEO:
        return bool(get_gemini_api_key().strip())
    return False
