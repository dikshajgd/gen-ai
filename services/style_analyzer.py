"""Character style analysis using Gemini vision."""

from __future__ import annotations

import json

from core.models import CharacterProfile
from services.gemini_client import GeminiClient
from utils.image_utils import encode_image_to_b64


ANALYSIS_PROMPT = """Analyze this character image in detail. Return a JSON object with these fields:

{
  "art_style": "description of the art style (e.g., watercolor anime, pixel art, realistic 3D, comic book style)",
  "color_palette": ["list", "of", "dominant", "colors", "as", "descriptive", "names"],
  "character_description": "detailed physical description of the character including clothing, accessories, hair, build, distinguishing features",
  "style_prompt_prefix": "A 2-3 sentence prompt prefix that can be prepended to any scene description to maintain this character's visual consistency. It should describe the character and art style concisely."
}

Return ONLY the JSON object, no other text."""


BRIEF_ANALYSIS_PROMPT_TEMPLATE = """You are a visual style and character analyst. Analyze the provided inputs and return a JSON object.

{context_section}

Return a JSON object with these fields:
{{
  "art_style": "description of the art style",
  "color_palette": ["list", "of", "dominant", "colors", "as", "descriptive", "names"],
  "character_description": "detailed physical description of any characters, objects, or subjects including clothing, accessories, distinguishing features",
  "style_prompt_prefix": "A 2-3 sentence prompt prefix that can be prepended to any scene description to maintain visual consistency. It should describe the subject and art style concisely."
}}

Return ONLY the JSON object, no other text."""


def _build_context_section(
    creative_prompt: str = "",
    style_prompt: str = "",
    has_images: bool = False,
) -> str:
    """Build the context paragraph for the analysis prompt."""
    parts = []
    if creative_prompt:
        parts.append(f"The user wants to create: {creative_prompt}")
    if style_prompt:
        parts.append(f"The desired visual style is: {style_prompt}")
    if has_images:
        parts.append(
            "Analyze the provided reference image(s) for art style, color palette, "
            "and character/subject details. Incorporate what you see into the analysis."
        )
    if not parts:
        parts.append("Analyze the provided image(s) in detail.")
    return "\n".join(parts)


def _parse_analysis_json(raw: str) -> dict | None:
    """Try to parse JSON from a Gemini response, stripping markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return None


class StyleAnalyzer:
    def __init__(self, gemini_client: GeminiClient):
        self.gemini = gemini_client

    def analyze(self, image_bytes: bytes) -> CharacterProfile:
        """Analyze a single character reference image. Legacy entry point."""
        return self.analyze_brief(image_bytes_list=[image_bytes])

    def analyze_brief(
        self,
        creative_prompt: str = "",
        image_bytes_list: list[bytes] | None = None,
        style_prompt: str = "",
        image_names: list[str] | None = None,
    ) -> CharacterProfile:
        """Analyze a creative brief (text + images + style) and return a CharacterProfile."""
        images = image_bytes_list or []
        names = image_names or []

        context = _build_context_section(creative_prompt, style_prompt, bool(images))
        prompt = BRIEF_ANALYSIS_PROMPT_TEMPLATE.format(context_section=context)

        # Call Gemini with images or text-only
        if images:
            raw = self.gemini.analyze_images(images, prompt)
        else:
            raw = self.gemini.chat(prompt)

        # Parse JSON response
        data = _parse_analysis_json(raw)

        # Encode images
        ref_images_b64 = [encode_image_to_b64(img) for img in images]
        first_b64 = ref_images_b64[0] if ref_images_b64 else ""

        if data is None:
            # Fallback: use raw text
            return CharacterProfile(
                reference_image_b64=first_b64,
                reference_images_b64=ref_images_b64,
                reference_image_names=names,
                character_description=raw,
                style_prompt_prefix=raw[:300],
                raw_analysis=raw,
                creative_prompt=creative_prompt,
                style_prompt=style_prompt,
            )

        return CharacterProfile(
            reference_image_b64=first_b64,
            reference_images_b64=ref_images_b64,
            reference_image_names=names,
            art_style=data.get("art_style", ""),
            color_palette=data.get("color_palette", []),
            character_description=data.get("character_description", ""),
            style_prompt_prefix=data.get("style_prompt_prefix", ""),
            raw_analysis=raw,
            creative_prompt=creative_prompt,
            style_prompt=style_prompt,
        )
