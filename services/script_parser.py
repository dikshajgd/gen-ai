"""Script parsing and prompt generation."""

from __future__ import annotations

import re

from core.models import Scene, CharacterProfile
from services.gemini_client import GeminiClient


class ScriptParser:
    def __init__(self, gemini_client: GeminiClient | None = None):
        self.gemini = gemini_client

    def parse(self, raw_text: str) -> list[Scene]:
        """Parse raw script text into a list of Scene objects."""
        raw_text = raw_text.strip()
        if not raw_text:
            return []

        # Try pattern-based splitting in priority order
        for pattern, extractor in _SPLIT_STRATEGIES:
            segments = _split_by_pattern(raw_text, pattern, extractor)
            if segments and len(segments) > 1:
                return _segments_to_scenes(segments)

        # Fallback: split on double newlines
        segments = _split_on_blank_lines(raw_text)
        return _segments_to_scenes(segments)

    def generate_image_prompts(
        self, scenes: list[Scene], character: CharacterProfile
    ) -> list[Scene]:
        """Generate scene-content image prompts for each scene using Gemini.

        These prompts describe ONLY the scene (subject-action-setting-lighting-
        framing) — the character identity and art-style anchor are layered on
        by the image pipeline at generation time, so editing one scene's style
        doesn't require regenerating every prompt.
        """
        if not self.gemini:
            for s in scenes:
                s.image_prompt = s.description
            return scenes

        for scene in scenes:
            prompt = _IMAGE_PROMPT_META.format(
                scene_title=scene.title or f"Scene {scene.index + 1}",
                scene_description=scene.description,
            )
            try:
                scene.image_prompt = self.gemini.chat(prompt).strip()
            except Exception:
                scene.image_prompt = scene.description

        return scenes

    def generate_video_prompts(self, scenes: list[Scene]) -> list[Scene]:
        """Generate motion-focused video prompts for Kling."""
        if not self.gemini:
            for s in scenes:
                s.video_prompt = s.description
            return scenes

        for scene in scenes:
            prompt = _VIDEO_PROMPT_META.format(
                image_description=scene.image_prompt or scene.description,
            )
            try:
                scene.video_prompt = self.gemini.chat(prompt).strip()
            except Exception:
                scene.video_prompt = scene.description

        return scenes


# ── Prompt engineering templates ──────────────────────────────────────

_IMAGE_PROMPT_META = """You are a visual prompt engineer for an AI image model.

Write a single image prompt for the scene below. Describe ONLY the scene content — do not include character appearance anchors or art-style notes; those are layered in separately.

Required structure, packed into 2-4 sentences:
1. Subject + action (what the character is doing)
2. Setting (where, time of day)
3. Lighting / atmosphere (quality of light, mood)
4. Camera framing (shot type: wide, medium, close-up; angle: low/high/eye-level)

Rules:
- No narrative fluff, no "in this scene", no dialogue quotes.
- Present tense, concrete nouns and verbs, no adverbs of degree ("very", "really").
- Do not mention art style, medium, or character features.

Example input:
  Title: "Arrival at the cottage"
  Description: "She reaches the cottage at dusk, exhausted from the journey, and pushes the door open."

Example output:
  A weary young woman pushes open a wooden cottage door. Overgrown garden, fading daylight behind distant hills. Warm amber light spills from inside, casting long shadows across her face. Medium shot, low eye-level angle from inside the doorway.

---

Title: "{scene_title}"
Description: {scene_description}

Write ONLY the image prompt, nothing else."""


_VIDEO_PROMPT_META = """You are a video prompt engineer for an image-to-video AI model (Kling).

Given a still image description, write a motion prompt (1-3 sentences) describing what moves in the shot. Be specific about motion — vague prompts give dead results.

Required elements:
- An explicit camera movement verb: dolly in, dolly out, pan left/right, tilt up/down, push-in, pull-out, tracking shot, static.
- A subject motion beat: "subject starts X, ends Y" — what the character/subject does across the clip.
- Optional environmental motion (leaves, water, smoke, cloth).

Rules:
- Present tense. No art-style notes, no cuts, no multiple shots — this is one continuous motion.
- Keep duration implicit (the clip is 5-10 seconds).

Example input:
  Image: A weary young woman pushes open a wooden cottage door at dusk, warm amber light spilling out.

Example output:
  Slow push-in on the woman as she steps across the threshold, her expression shifting from exhaustion to relief. Interior firelight flickers on her face; a curtain of ivy sways gently in the breeze behind her.

---

Image description: {image_description}

Write ONLY the video motion prompt, nothing else."""


# --- Internal helpers ---

_SPLIT_STRATEGIES = [
    # (regex pattern, title extractor function)
    (r"^SCENE\s*\d*\s*[:.]\s*", lambda m, line: line[m.end():].strip() or f"Scene"),
    (r"^(?:INT|EXT)\.\s+", lambda m, line: line[m.start():].strip()),
    (r"^\d+\.\s+", lambda m, line: line[m.end():].strip()),
    (r"^#{1,3}\s+", lambda m, line: line[m.end():].strip()),
    (r"^\[(.+?)\]\s*$", lambda m, line: m.group(1).strip()),
]


def _split_by_pattern(
    text: str, pattern: str, title_extractor
) -> list[tuple[str, str]] | None:
    """Split text by a regex pattern. Returns list of (title, body) or None."""
    lines = text.split("\n")
    segments = []
    current_title = ""
    current_body_lines = []

    for line in lines:
        match = re.match(pattern, line, re.MULTILINE)
        if match:
            if current_title or current_body_lines:
                segments.append((current_title, "\n".join(current_body_lines).strip()))
            current_title = title_extractor(match, line)
            current_body_lines = []
        else:
            current_body_lines.append(line)

    if current_title or current_body_lines:
        segments.append((current_title, "\n".join(current_body_lines).strip()))

    # Only return if pattern matched at least twice
    titled = [s for s in segments if s[0]]
    if len(titled) >= 2:
        return segments
    return None


def _split_on_blank_lines(text: str) -> list[tuple[str, str]]:
    """Split on double newlines as fallback."""
    blocks = re.split(r"\n\s*\n", text)
    return [("", block.strip()) for block in blocks if block.strip()]


def _segments_to_scenes(segments: list[tuple[str, str]]) -> list[Scene]:
    """Convert (title, body) tuples to Scene objects."""
    scenes = []
    for i, (title, body) in enumerate(segments):
        if not body and not title:
            continue
        scenes.append(
            Scene(
                index=i,
                title=title or f"Scene {i + 1}",
                description=body or title,
            )
        )
    return scenes
