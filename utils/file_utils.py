"""File utility functions."""

import io
import zipfile


def create_zip_from_files(files: dict[str, bytes]) -> bytes:
    """Create a zip archive in memory from a dict of {filename: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()
