"""Pluggable video generation providers.

Public surface:
    - VideoProvider             abstract base
    - get_provider(provider_id) factory by id
    - PROVIDER_CATALOG          list of (id, label, models) for UI dropdowns
"""

from services.video_providers.base import (
    VideoProvider,
    VideoSubmission,
    VideoStatusResult,
    VideoProviderError,
)
from services.video_providers.registry import (
    get_provider,
    PROVIDER_CATALOG,
    PROVIDER_KLING_DIRECT,
    PROVIDER_REPLICATE,
    PROVIDER_VEO,
    DEFAULT_PROVIDER_MODEL,
)

__all__ = [
    "VideoProvider",
    "VideoSubmission",
    "VideoStatusResult",
    "VideoProviderError",
    "get_provider",
    "PROVIDER_CATALOG",
    "PROVIDER_KLING_DIRECT",
    "PROVIDER_REPLICATE",
    "PROVIDER_VEO",
    "DEFAULT_PROVIDER_MODEL",
]
