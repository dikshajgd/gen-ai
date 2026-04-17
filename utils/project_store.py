"""JSON-based project persistence for Scene Studio.

Storage layout (per project):
    <data_dir>/<project_id>/project.json         # slim metadata + prompts
    <data_dir>/<project_id>/images/<i>.png        # generated scene images
    <data_dir>/<project_id>/videos/<i>.mp4        # generated scene videos
    <data_dir>/<project_id>/ref/<i>.bin           # reference images (first one also as ref/main.bin)

Images, videos, and reference images live as sidecar files to keep the JSON
file compact and fast to parse. The in-memory `ProjectState` still holds the
binaries as base64 strings (loaded lazily when the project is opened).

Backward compatibility: older projects that were saved as `<data_dir>/<id>.json`
with inline base64 payloads are still readable.
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from core.constants import GEMINI_MAX_HISTORY_TURNS
from core.models import ProjectMetadata, ProjectState, SceneStatus, VideoStatus
from utils.image_utils import make_thumbnail_b64

logger = logging.getLogger(__name__)


class ProjectStore:
    """Saves and loads projects as per-folder JSON + binary sidecars on disk."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.data_dir / "_index.json"

    # ── Public API ────────────────────────────────────────────────────

    def save(self, project: ProjectState) -> None:
        """Persist a project to disk and update the index."""
        project.updated_at = datetime.now()

        project_dir = self.data_dir / project.project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        slim = self._write_sidecars(project, project_dir)

        project_path = project_dir / "project.json"
        project_path.write_text(slim.model_dump_json(indent=2), encoding="utf-8")

        # Clean up any legacy flat JSON from a previous save layout.
        legacy = self.data_dir / f"{project.project_id}.json"
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass

        self._update_index(project)

    def load(self, project_id: str) -> ProjectState:
        """Load a project from disk by ID (supports both new and legacy layouts)."""
        new_path = self.data_dir / project_id / "project.json"
        legacy_path = self.data_dir / f"{project_id}.json"

        if new_path.exists():
            state = ProjectState.model_validate_json(new_path.read_text(encoding="utf-8"))
            self._read_sidecars(state, self.data_dir / project_id)
            return state

        if legacy_path.exists():
            # Old flat layout with inline base64 — still works.
            return ProjectState.model_validate_json(legacy_path.read_text(encoding="utf-8"))

        raise FileNotFoundError(f"No project found for id {project_id}")

    def list_projects(self) -> list[ProjectMetadata]:
        index = self._read_index()
        index.sort(key=lambda m: m.updated_at, reverse=True)
        return index

    def delete(self, project_id: str) -> None:
        """Remove a project's files and its index entry."""
        project_dir = self.data_dir / project_id
        if project_dir.exists() and project_dir.is_dir():
            shutil.rmtree(project_dir, ignore_errors=True)

        legacy = self.data_dir / f"{project_id}.json"
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass

        index = self._read_index()
        index = [m for m in index if m.project_id != project_id]
        self._write_index(index)

    # ── Save-time binary stripping ────────────────────────────────────

    def _write_sidecars(self, project: ProjectState, project_dir: Path) -> ProjectState:
        """Write every binary payload to a sidecar file and return a slim copy
        of the ProjectState with binaries cleared from the JSON-bound fields."""
        slim = deepcopy(project)

        # Scene images (current + undo history)
        (project_dir / "images").mkdir(exist_ok=True)
        for img in slim.images:
            if img.image_b64:
                try:
                    (project_dir / "images" / f"{img.scene_index}.png").write_bytes(
                        base64.b64decode(img.image_b64)
                    )
                    img.image_b64 = ""
                except Exception:
                    logger.exception("Failed to write image sidecar for scene %s", img.scene_index)

            # History entries: images/<i>_prev_<n>.png (n=0 is most recent prior)
            for n, b64 in enumerate(img.history_b64):
                if not b64:
                    continue
                try:
                    (project_dir / "images" / f"{img.scene_index}_prev_{n}.png").write_bytes(
                        base64.b64decode(b64)
                    )
                except Exception:
                    logger.exception("Failed to write history sidecar for scene %s/%s", img.scene_index, n)
            img.history_b64 = [""] * len(img.history_b64)

        # Scene videos
        (project_dir / "videos").mkdir(exist_ok=True)
        for vid in slim.videos:
            if not vid.video_b64:
                continue
            try:
                data = base64.b64decode(vid.video_b64)
                (project_dir / "videos" / f"{vid.scene_index}.mp4").write_bytes(data)
                vid.video_b64 = ""
            except Exception:
                logger.exception("Failed to write video sidecar for scene %s", vid.scene_index)

        # Reference images (character profile)
        if slim.character:
            (project_dir / "ref").mkdir(exist_ok=True)
            if slim.character.reference_image_b64:
                try:
                    data = base64.b64decode(slim.character.reference_image_b64)
                    (project_dir / "ref" / "main.bin").write_bytes(data)
                    slim.character.reference_image_b64 = ""
                except Exception:
                    logger.exception("Failed to write main ref image sidecar")

            for i, b64 in enumerate(slim.character.reference_images_b64):
                if not b64:
                    continue
                try:
                    data = base64.b64decode(b64)
                    (project_dir / "ref" / f"{i}.bin").write_bytes(data)
                except Exception:
                    logger.exception("Failed to write ref image %s sidecar", i)
            slim.character.reference_images_b64 = [""] * len(slim.character.reference_images_b64)

        # Gemini conversation history — strip inline image bytes from all but
        # the last N turns (N user + N model entries). Older turns keep text
        # only so resume still has context without the size blow-up.
        keep_n = 2 * GEMINI_MAX_HISTORY_TURNS
        if len(slim.gemini_conversation_history) > keep_n:
            old = slim.gemini_conversation_history[:-keep_n]
            for entry in old:
                entry["parts"] = [p for p in entry.get("parts", []) if "text" in p]
            slim.gemini_conversation_history = old + slim.gemini_conversation_history[-keep_n:]

        return slim

    # ── Load-time binary re-hydration ─────────────────────────────────

    def _read_sidecars(self, project: ProjectState, project_dir: Path) -> None:
        """Re-populate base64 fields from sidecar files, in place."""
        images_dir = project_dir / "images"
        videos_dir = project_dir / "videos"
        ref_dir = project_dir / "ref"

        for img in project.images:
            path = images_dir / f"{img.scene_index}.png"
            if path.exists():
                try:
                    img.image_b64 = base64.b64encode(path.read_bytes()).decode()
                except Exception:
                    logger.exception("Failed to read image sidecar for scene %s", img.scene_index)

            # History entries
            for n in range(len(img.history_b64)):
                hpath = images_dir / f"{img.scene_index}_prev_{n}.png"
                if hpath.exists():
                    try:
                        img.history_b64[n] = base64.b64encode(hpath.read_bytes()).decode()
                    except Exception:
                        logger.exception("Failed to read history sidecar for scene %s/%s", img.scene_index, n)

        for vid in project.videos:
            path = videos_dir / f"{vid.scene_index}.mp4"
            if path.exists():
                try:
                    vid.video_b64 = base64.b64encode(path.read_bytes()).decode()
                except Exception:
                    logger.exception("Failed to read video sidecar for scene %s", vid.scene_index)

        if project.character:
            main = ref_dir / "main.bin"
            if main.exists():
                try:
                    project.character.reference_image_b64 = base64.b64encode(main.read_bytes()).decode()
                except Exception:
                    logger.exception("Failed to read main ref image sidecar")

            for i in range(len(project.character.reference_images_b64)):
                path = ref_dir / f"{i}.bin"
                if path.exists():
                    try:
                        project.character.reference_images_b64[i] = base64.b64encode(path.read_bytes()).decode()
                    except Exception:
                        logger.exception("Failed to read ref image %s sidecar", i)

    # ── Index management ──────────────────────────────────────────────

    def _update_index(self, project: ProjectState) -> None:
        index = self._read_index()

        meta = ProjectMetadata(
            project_id=project.project_id,
            name=project.name,
            created_at=project.created_at,
            updated_at=project.updated_at,
            thumbnail_b64=self._build_thumbnail(project),
            scene_count=len(project.scenes),
            approved_images=sum(1 for i in project.images if i.status == SceneStatus.APPROVED),
            approved_videos=sum(1 for v in project.videos if v.status == VideoStatus.APPROVED),
        )

        index = [m for m in index if m.project_id != project.project_id]
        index.append(meta)
        self._write_index(index)

    def _build_thumbnail(self, project: ProjectState) -> str:
        """Pick the best-available image and return a 96px JPEG thumbnail b64."""
        # Prefer an approved image, then any generated image, then the
        # character reference image.
        for img in project.images:
            if img.status == SceneStatus.APPROVED and img.image_b64:
                return make_thumbnail_b64(base64.b64decode(img.image_b64))
        for img in project.images:
            if img.image_b64:
                return make_thumbnail_b64(base64.b64decode(img.image_b64))
        if project.character and project.character.reference_image_b64:
            return make_thumbnail_b64(base64.b64decode(project.character.reference_image_b64))
        if project.character and project.character.reference_images_b64:
            for b64 in project.character.reference_images_b64:
                if b64:
                    return make_thumbnail_b64(base64.b64decode(b64))
        return ""

    def _read_index(self) -> list[ProjectMetadata]:
        if not self._index_path.exists():
            return []
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            return [ProjectMetadata.model_validate(entry) for entry in raw]
        except (json.JSONDecodeError, ValueError):
            return []

    def _write_index(self, index: list[ProjectMetadata]) -> None:
        data = [m.model_dump(mode="json") for m in index]
        self._index_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
