"""Retry decorators using tenacity."""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from core.constants import (
    GEMINI_MAX_RETRIES,
    GEMINI_RETRY_MIN_WAIT,
    GEMINI_RETRY_MAX_WAIT,
    KLING_MAX_RETRIES,
    KLING_RETRY_MIN_WAIT,
    KLING_RETRY_MAX_WAIT,
)


gemini_retry = retry(
    stop=stop_after_attempt(GEMINI_MAX_RETRIES),
    wait=wait_exponential(min=GEMINI_RETRY_MIN_WAIT, max=GEMINI_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
)

kling_retry = retry(
    stop=stop_after_attempt(KLING_MAX_RETRIES),
    wait=wait_exponential(min=KLING_RETRY_MIN_WAIT, max=KLING_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
)
