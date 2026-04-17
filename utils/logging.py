"""Centralized logging setup for Scene Studio.

Writes to console (INFO+) and a rotating file at ~/.scene_studio/logs/app.log.
Call `setup_logging()` once at app startup.

On read-only filesystems (e.g. some hosted environments) the file handler is
silently skipped — console logging still works.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
_BACKUP_COUNT = 5


def setup_logging(data_dir: str | None = None) -> None:
    """Configure root logger. Idempotent — safe to call on every Streamlit rerun."""
    root = logging.getLogger()
    if getattr(root, "_scene_studio_configured", False):
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Rotating file handler (best-effort)
    log_dir = _resolve_log_dir(data_dir)
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            # Read-only FS or permission denied — keep going with console only.
            pass

    # Quiet down chatty third-party libs
    for noisy in ("httpx", "urllib3", "google_genai", "google.auth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._scene_studio_configured = True  # type: ignore[attr-defined]


def _resolve_log_dir(data_dir: str | None) -> Path | None:
    candidate = data_dir or os.path.expanduser("~/.scene_studio")
    return Path(candidate) / "logs"
