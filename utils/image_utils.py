"""Image utility functions."""

import base64
import io
from PIL import Image

from core.constants import GEMINI_IMAGE_MAX_SIZE_BYTES


def encode_image_to_b64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def decode_b64_to_bytes(b64_string: str) -> bytes:
    return base64.b64decode(b64_string)


def resize_image_if_needed(image_bytes: bytes, max_size: int = GEMINI_IMAGE_MAX_SIZE_BYTES) -> bytes:
    """Resize image if it exceeds max_size bytes."""
    if len(image_bytes) <= max_size:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes))
    quality = 85
    while quality >= 20:
        buf = io.BytesIO()
        img.save(buf, format="PNG" if img.mode == "RGBA" else "JPEG", quality=quality)
        result = buf.getvalue()
        if len(result) <= max_size:
            return result
        quality -= 10

    # Last resort: reduce dimensions
    while True:
        w, h = img.size
        img = img.resize((w // 2, h // 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG" if img.mode == "RGBA" else "JPEG", quality=60)
        result = buf.getvalue()
        if len(result) <= max_size or w < 100:
            return result


def make_thumbnail_b64(image_bytes: bytes, max_side: int = 96) -> str:
    """Create a small JPEG thumbnail and return it base64-encoded. Empty string on error."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""


def get_image_mime_type(image_bytes: bytes) -> str:
    """Detect MIME type from image header bytes."""
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    return "image/png"
