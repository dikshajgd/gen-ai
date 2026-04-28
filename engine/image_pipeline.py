"""Image generation pipeline with character consistency."""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any, Callable

from core.models import (
    Scene,
    SceneImage,
    SceneStatus,
    CharacterProfile,
)
from services.gemini_client import GeminiClient, ImageGenerationError

logger = logging.getLogger(__name__)

# Max prior versions kept per scene for the undo stack. Older versions are
# discarded. Keeps project size bounded.
UNDO_HISTORY_CAP = 3


def _push_to_history(img: SceneImage) -> None:
    """Move the current image_b64 onto the history stack (newest first)."""
    if not img.image_b64:
        return
    img.history_b64.insert(0, img.image_b64)
    del img.history_b64[UNDO_HISTORY_CAP:]


class ImagePipeline:
    def __init__(self, gemini_client: GeminiClient):
        self.gemini = gemini_client

    def generate_all(
        self,
        scenes: list[Scene],
        images: list[SceneImage],
        character: CharacterProfile,
        history: list[dict[str, Any]],
        on_progress: Callable[[int, SceneImage, list[dict[str, Any]]], None] | None = None,
    ) -> tuple[list[SceneImage], list[dict[str, Any]]]:
        """Generate images for all pending/rejected/failed scenes sequentially.

        Sequential is required to maintain conversation history for character consistency.
        Returns (updated images, updated history).
        """
        ref_bytes = base64.b64decode(character.reference_image_b64) if character.reference_image_b64 else None

        for i, scene in enumerate(scenes):
            img = images[i]
            if img.status not in (SceneStatus.PENDING, SceneStatus.REJECTED, SceneStatus.FAILED):
                continue

            # Preserve any prior image on the undo stack (e.g. a rejected one).
            _push_to_history(img)

            img.status = SceneStatus.GENERATING
            img.error_message = ""
            if on_progress:
                on_progress(i, img, history)

            prompt = _build_prompt(character, scene)

            success = False
            while img.generation_attempts < img.max_attempts and not success:
                img.generation_attempts += 1
                try:
                    image_bytes, history = self.gemini.generate_image(
                        prompt=prompt,
                        reference_image_bytes=ref_bytes,
                        history=history,
                    )
                    img.image_b64 = base64.b64encode(image_bytes).decode()
                    img.status = SceneStatus.GENERATED
                    img.generated_at = datetime.now()
                    img.error_message = ""
                    success = True
                except ImageGenerationError as e:
                    img.error_message = str(e)
                    logger.warning("Image gen failed (scene %s, attempt %s): %s", i, img.generation_attempts, e)
                    if img.generation_attempts >= img.max_attempts:
                        img.status = SceneStatus.FAILED
                except Exception as e:
                    img.error_message = f"Unexpected error: {str(e)}"
                    logger.exception("Unexpected image gen error (scene %s)", i)
                    if img.generation_attempts >= img.max_attempts:
                        img.status = SceneStatus.FAILED

            if on_progress:
                on_progress(i, img, history)

        return images, history

    def regenerate_single(
        self,
        scene_index: int,
        scenes: list[Scene],
        images: list[SceneImage],
        character: CharacterProfile,
        history: list[dict[str, Any]],
        extra_guidance: str = "",
    ) -> tuple[SceneImage, list[dict[str, Any]]]:
        """Regenerate a single scene image."""
        scene = scenes[scene_index]
        img = images[scene_index]

        # Push the current image onto the undo stack before overwriting.
        _push_to_history(img)

        img.status = SceneStatus.GENERATING
        img.generation_attempts = 0
        img.error_message = ""

        ref_bytes = base64.b64decode(character.reference_image_b64) if character.reference_image_b64 else None
        prompt = _build_prompt(character, scene, extra_guidance=extra_guidance)

        while img.generation_attempts < img.max_attempts:
            img.generation_attempts += 1
            try:
                image_bytes, history = self.gemini.generate_image(
                    prompt=prompt,
                    reference_image_bytes=ref_bytes,
                    history=history,
                )
                img.image_b64 = base64.b64encode(image_bytes).decode()
                img.status = SceneStatus.GENERATED
                img.generated_at = datetime.now()
                img.error_message = ""
                return img, history
            except ImageGenerationError as e:
                img.error_message = str(e)
                logger.warning("Regenerate failed (scene %s, attempt %s): %s", scene_index, img.generation_attempts, e)
            except Exception as e:
                img.error_message = f"Unexpected error: {str(e)}"
                logger.exception("Unexpected regenerate error (scene %s)", scene_index)

        img.status = SceneStatus.FAILED
        return img, history


def _build_prompt(
    character: CharacterProfile,
    scene: Scene,
    extra_guidance: str = "",
) -> str:
    """Compose the full image-gen prompt.

    Style-only model: the reference image (if any) is a STYLE anchor — color
    palette, technique, mood. Subject and action come entirely from the
    scene description. This avoids Gemini's "I can't put this person in a
    new pose" refusal pattern that bites when the reference is interpreted
    as a character identity to be preserved.

    Scene-level `style_override` takes precedence over the project-level
    style prefix.
    """
    style = scene.style_override.strip() or character.style_prompt_prefix.strip()
    scene_body = scene.image_prompt.strip() or scene.description.strip()

    parts: list[str] = []

    parts.append(
        "Generate a fresh illustration of the scene described below. "
        "If a reference image is attached, treat it ONLY as a visual style "
        "guide — match its color palette, technique, lighting, and mood. "
        "Do not copy its subject, composition, or pose. Invent the scene "
        "entirely from the description that follows."
    )

    if style:
        parts.append(f"Visual style to match: {style}")

    parts.append(f"Scene to depict: {scene_body}")

    if extra_guidance.strip():
        parts.append(f"Additional guidance: {extra_guidance.strip()}")

    return "\n\n".join(parts)
