"""Visual-style analysis using Gemini.

Given a text style description and an optional style reference image, produce
a `CharacterProfile` (kept under the legacy name for save-file compatibility)
that holds the refined style prompt prefix used for every scene generation.

Note: there's no character identity in this analysis anymore — character and
scene content come from the script in Step 2.
"""

from __future__ import annotations

import json

from core.models import CharacterProfile
from services.gemini_client import GeminiClient
from utils.image_utils import encode_image_to_b64


_STYLE_ANALYSIS_PROMPT_TEMPLATE = """You are a visual style analyst.

Inputs you may receive:
- A user-written style description.
- An optional style reference image (an artwork, illustration, or screenshot whose look should be matched).

Produce a single JSON object describing the visual style. The JSON will be used as a style anchor prepended to every scene-generation prompt downstream.

Return JSON with these fields:
{{
  "art_style": "concise descriptor — medium + technique + influence (e.g. 'watercolor illustration, soft pastels, Studio Ghibli-influenced')",
  "color_palette": ["a", "few", "dominant", "color", "names", "or", "hex"],
  "style_prompt_prefix": "1-3 sentences. The exact style guidance to prepend to scene prompts. Cover medium, technique, color/light mood, and any defining characteristics. Do NOT mention any specific character, subject, or person — this is style-only."
}}

Rules:
- The style_prompt_prefix must be SCENE-AGNOSTIC and CHARACTER-AGNOSTIC.
- Avoid words that lock specific subjects ("the woman", "the cat"). Talk only about the look.

Inputs:
{context_section}

Return ONLY the JSON object, no other text."""


def _build_context_section(style_prompt: str = "", has_image: bool = False) -> str:
    parts = []
    if style_prompt:
        parts.append(f"User style description: {style_prompt}")
    if has_image:
        parts.append(
            "A style reference image is attached. Analyze its art style, "
            "color palette, lighting, and technique. Match these in the output."
        )
    if not parts:
        parts.append("(No specific input provided — return a sensible default style.)")
    return "\n".join(parts)


def _parse_analysis_json(raw: str) -> dict | None:
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

    def analyze_style(
        self,
        style_prompt: str = "",
        style_ref_bytes: bytes | None = None,
        style_ref_name: str = "",
    ) -> CharacterProfile:
        """Build a style-only `CharacterProfile` from text + optional reference image."""
        context = _build_context_section(style_prompt, has_image=bool(style_ref_bytes))
        prompt = _STYLE_ANALYSIS_PROMPT_TEMPLATE.format(context_section=context)

        if style_ref_bytes:
            raw = self.gemini.analyze_image(style_ref_bytes, prompt)
        else:
            raw = self.gemini.chat(prompt)

        data = _parse_analysis_json(raw)

        ref_b64 = encode_image_to_b64(style_ref_bytes) if style_ref_bytes else ""
        ref_name = style_ref_name if style_ref_bytes else ""

        if data is None:
            # Fallback: just use the user's text directly.
            return CharacterProfile(
                reference_image_b64=ref_b64,
                reference_image_names=[ref_name] if ref_name else [],
                style_prompt_prefix=style_prompt or raw[:300],
                raw_analysis=raw,
                style_prompt=style_prompt,
            )

        return CharacterProfile(
            reference_image_b64=ref_b64,
            reference_image_names=[ref_name] if ref_name else [],
            art_style=data.get("art_style", ""),
            color_palette=data.get("color_palette", []),
            style_prompt_prefix=data.get("style_prompt_prefix", "") or style_prompt,
            raw_analysis=raw,
            style_prompt=style_prompt,
        )

    # ── Legacy entry points kept for backward-compat with anything importing them ──

    def analyze(self, image_bytes: bytes) -> CharacterProfile:
        """Legacy: analyze a single image as the style reference."""
        return self.analyze_style(style_ref_bytes=image_bytes)

    def analyze_brief(
        self,
        creative_prompt: str = "",
        image_bytes_list: list[bytes] | None = None,
        style_prompt: str = "",
        image_names: list[str] | None = None,
    ) -> CharacterProfile:
        """Legacy: forwards to analyze_style using the first image, if any."""
        first = image_bytes_list[0] if image_bytes_list else None
        first_name = (image_names or [""])[0] if image_bytes_list else ""
        return self.analyze_style(
            style_prompt=style_prompt or creative_prompt,
            style_ref_bytes=first,
            style_ref_name=first_name,
        )
