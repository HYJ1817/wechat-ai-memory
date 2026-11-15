"""Persistence for user-defined scenes.

Built-in scenes live in code; user scenes live in one small JSON file next to the
app's other state.  Listing merges the two, and a user scene with the same id as a
built-in one overrides it -- that is how a user retunes "群聊总结" without losing
the ability to get the original back by deleting their override.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .catalog import BUILTIN_SCENES, BUILTIN_BY_ID
from .models import Scene, SceneError

SCENES_SCHEMA_VERSION = 1


def default_scene_path() -> Path:
    """Scenes live beside the app's other state; env override for tests/portable."""
    override = os.environ.get("WECHAT_AI_MEMORY_SCENES_FILE")
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "WeChatAIMemory" / "scenes.json"
    return Path.home() / ".wechat-ai-memory" / "scenes.json"


class SceneStore:
    """Reads and writes the user's scene overrides."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path).expanduser() if path else default_scene_path()
        self.last_warnings: list[str] = []

    def list(self) -> list[Scene]:
        """Built-in scenes first (in catalog order), then the user's own."""
        self.last_warnings = []
        user_scenes = self._load()
        merged: dict[str, Scene] = {scene.id: scene for scene in BUILTIN_SCENES}
        order = [scene.id for scene in BUILTIN_SCENES]
        for scene in user_scenes:
            if scene.id not in merged:
                order.append(scene.id)
            merged[scene.id] = scene
        return [merged[scene_id] for scene_id in order]

    def get(self, scene_id: str) -> Scene:
        for scene in self.list():
            if scene.id == scene_id:
                return scene
        known = ", ".join(scene.id for scene in self.list())
        raise SceneError(f"unknown scene: {scene_id!r} (available: {known})")

    def save(self, scene: Scene) -> Scene:
        """Insert or replace a scene in the user file."""
        scenes = {item.id: item for item in self._load()}
        scenes[scene.id] = scene
        self._write(list(scenes.values()))
        return scene

    def delete(self, scene_id: str) -> bool:
        """Drop a user scene; deleting a built-in override restores the built-in."""
        scenes = self._load()
        kept = [scene for scene in scenes if scene.id != scene_id]
        if len(kept) == len(scenes):
            return False
        self._write(kept)
        return True

    # -- internals -------------------------------------------------------

    def _load(self) -> list[Scene]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.last_warnings.append(f"{self.path.name}: unreadable scene file ({exc})")
            return []

        items = payload.get("scenes") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            self.last_warnings.append(f"{self.path.name}: 'scenes' is not a list")
            return []

        scenes: list[Scene] = []
        for index, item in enumerate(items):
            try:
                scenes.append(Scene.from_dict(item))
            except SceneError as exc:
                self.last_warnings.append(f"{self.path.name}[{index}]: {exc}")
        return scenes

    def _write(self, scenes: list[Scene]) -> None:
        payload = {
            "schema_version": SCENES_SCHEMA_VERSION,
            "scenes": [scene.to_dict() for scene in scenes],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, self.path)


__all__ = ["BUILTIN_BY_ID", "BUILTIN_SCENES", "SceneStore", "default_scene_path"]
