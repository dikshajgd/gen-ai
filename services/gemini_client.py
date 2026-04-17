"""Gemini API client for vision analysis and image generation."""

from __future__ import annotations

import base64
from typing import Any

from google import genai
from google.genai import types

from core.constants import GEMINI_MODEL, GEMINI_IMAGE_MODEL, GEMINI_MAX_HISTORY_TURNS
from utils.retry import gemini_retry


class ImageGenerationError(Exception):
    """Raised when Gemini fails to generate an image."""
    pass


class GeminiClient:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = GEMINI_MODEL
        self.image_model = GEMINI_IMAGE_MODEL

    @gemini_retry
    def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        """Send an image + text prompt for vision analysis. Returns text response."""
        mime = _detect_mime(image_bytes)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
        )
        return response.text or ""

    @gemini_retry
    def analyze_images(self, image_bytes_list: list[bytes], prompt: str) -> str:
        """Send multiple images + text prompt for vision analysis. Returns text response."""
        parts: list[types.Part] = []
        for img_bytes in image_bytes_list:
            mime = _detect_mime(img_bytes)
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        response = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
        )
        return response.text or ""

    @gemini_retry
    def generate_image(
        self,
        prompt: str,
        reference_image_bytes: bytes | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[bytes, list[dict[str, Any]]]:
        """Generate an image using Gemini with optional reference and conversation history.

        Returns (image_bytes, updated_history).
        Raises ImageGenerationError if no image is produced.
        """
        history = list(history) if history else []

        # Build the user message parts
        parts = []
        if reference_image_bytes:
            mime = _detect_mime(reference_image_bytes)
            parts.append(types.Part.from_bytes(data=reference_image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        # Truncate what we SEND to the model to the last N turns (N user +
        # N model entries). The full history is still returned for persistence
        # so a re-opened project keeps the complete chain.
        max_entries = 2 * GEMINI_MAX_HISTORY_TURNS
        sendable_history = history[-max_entries:] if len(history) > max_entries else history

        sdk_contents = _history_to_contents(sendable_history)
        sdk_contents.append(types.Content(role="user", parts=parts))

        response = self.client.models.generate_content(
            model=self.image_model,
            contents=sdk_contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract image from response
        image_bytes = None
        response_text = ""
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = part.inline_data.data
                elif part.text:
                    response_text = part.text

        if image_bytes is None:
            raise ImageGenerationError(
                f"No image generated. Model response: {response_text[:200] if response_text else 'empty'}"
            )

        # Update history with user message and model response
        user_entry = {"role": "user", "parts": [{"text": prompt}]}
        if reference_image_bytes:
            user_entry["parts"].insert(0, {
                "inline_data": {
                    "mime_type": _detect_mime(reference_image_bytes),
                    "data_b64": base64.b64encode(reference_image_bytes).decode(),
                }
            })

        model_entry = {"role": "model", "parts": []}
        if image_bytes:
            model_entry["parts"].append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data_b64": base64.b64encode(image_bytes).decode(),
                }
            })
        if response_text:
            model_entry["parts"].append({"text": response_text})

        history.append(user_entry)
        history.append(model_entry)

        return image_bytes, history

    @gemini_retry
    def chat(self, prompt: str, system_prompt: str = "") -> str:
        """Simple text chat with Gemini. Returns text response."""
        contents = []
        if system_prompt:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=system_prompt)]))
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        return response.text or ""


def _detect_mime(data: bytes) -> str:
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and len(data) > 11 and data[8:12] == b'WEBP':
        return "image/webp"
    return "image/png"


def _history_to_contents(history: list[dict[str, Any]]) -> list[types.Content]:
    """Convert serialized history dicts back to SDK Content objects."""
    contents = []
    for entry in history:
        parts = []
        for p in entry.get("parts", []):
            if "text" in p:
                parts.append(types.Part.from_text(text=p["text"]))
            elif "inline_data" in p:
                data = base64.b64decode(p["inline_data"]["data_b64"])
                mime = p["inline_data"]["mime_type"]
                parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        if parts:
            contents.append(types.Content(role=entry["role"], parts=parts))
    return contents
