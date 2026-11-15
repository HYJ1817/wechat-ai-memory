"""A scene is a saved recipe: what to select, how to export, who receives it.

WeChatBridge lets a user pin one prompt per group and pick it at forward time.
The same idea applied to an archive tool turns a five-step dialog into one
click: the conversation, the time window, the keyword filter, the output
formats, the prompt, and the delivery target all become a single named object.

Windows are wall-clock values, matching the chat data: message timestamps carry
no timezone, so a scene window is interpreted in the same frame as the messages
it selects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

SCENE_TARGETS = ("none", "folder", "obsidian", "clipboard", "agent")

_SCENE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")


class SceneError(ValueError):
    """Raised when a scene definition is invalid or cannot be read."""


def _source_time(value: datetime | None) -> datetime | None:
    """Normalize to the naive wall clock used by the chat sources."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class Scene:
    id: str
    name: str
    description: str = ""
    conversation_id: str | None = None
    days: int | None = None
    start: datetime | None = None
    end: datetime | None = None
    query: str | None = None
    include_image_pages: bool = True
    markdown: bool = True
    json_output: bool = True
    target: str = "folder"
    prompt: str = ""
    shortcut: int | None = None
    builtin: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _SCENE_ID_PATTERN.match(self.id):
            raise SceneError(
                f"invalid scene id: {self.id!r} (lowercase letters, digits, . _ - only)"
            )
        if not self.name.strip():
            raise SceneError("scene name cannot be empty")
        if self.days is not None and self.days < 1:
            raise SceneError(f"scene {self.id}: days must be at least 1")
        if self.target not in SCENE_TARGETS:
            raise SceneError(
                f"scene {self.id}: target must be one of {', '.join(SCENE_TARGETS)}"
            )
        if self.shortcut is not None and not 1 <= self.shortcut <= 9:
            raise SceneError(f"scene {self.id}: shortcut must be between 1 and 9")

        object.__setattr__(self, "start", _source_time(self.start))
        object.__setattr__(self, "end", _source_time(self.end))
        if self.start and self.end and self.start > self.end:
            raise SceneError(f"scene {self.id}: start cannot be after end")

    def window(self, now: datetime | None = None) -> tuple[datetime | None, datetime | None]:
        """Resolve the scene into a concrete ``[start, end]`` pair.

        An explicit range wins; otherwise the trailing ``days`` window ends at
        ``now``.  A scene with neither selects the whole conversation.
        """
        if self.start is not None or self.end is not None:
            return self.start, self.end
        if self.days is None:
            return None, None
        anchor = now or datetime.now()
        if anchor.tzinfo is not None:
            anchor = anchor.astimezone().replace(tzinfo=None)
        return anchor - timedelta(days=self.days, microseconds=anchor.microsecond), anchor

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "conversation_id": self.conversation_id,
            "days": self.days,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "query": self.query,
            "include_image_pages": self.include_image_pages,
            "markdown": self.markdown,
            "json_output": self.json_output,
            "target": self.target,
            "prompt": self.prompt,
            "shortcut": self.shortcut,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Scene":
        if not isinstance(payload, dict):
            raise SceneError("scene must be a JSON object")
        try:
            return cls(
                id=str(payload["id"]),
                name=str(payload["name"]),
                description=str(payload.get("description") or ""),
                conversation_id=payload.get("conversation_id"),
                days=payload.get("days"),
                start=_parse_time(payload.get("start")),
                end=_parse_time(payload.get("end")),
                query=payload.get("query"),
                include_image_pages=bool(payload.get("include_image_pages", True)),
                markdown=bool(payload.get("markdown", True)),
                json_output=bool(payload.get("json_output", True)),
                target=str(payload.get("target", "folder")),
                prompt=str(payload.get("prompt") or ""),
                shortcut=payload.get("shortcut"),
            )
        except KeyError as exc:
            raise SceneError(f"scene is missing {exc.args[0]!r}") from exc
        except (TypeError, ValueError) as exc:
            raise SceneError(f"scene is malformed: {exc}") from exc


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SceneError(f"invalid scene timestamp: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed
