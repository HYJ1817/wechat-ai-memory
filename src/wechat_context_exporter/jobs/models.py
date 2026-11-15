"""Data contracts for a single export job.

One export run is recorded as one job: a manifest describing where the data came
from and what was produced, plus a state record describing where it was
delivered.  The shape mirrors the inbox contract used by WeChatBridge -- an
immutable manifest, a separate mutable state file, and content-addressed
artifacts -- so a job directory can be read by a tool that never saw the code
that wrote it.

The job id is the only identifier an agent or a rerun needs.  Everything else
(includes the message id range) can be reconstructed from the manifest.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

JOB_SCHEMA_VERSION = 1
PREVIEW_LIMIT = 80

_JOB_ID_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_HASH_CHUNK = 1024 * 1024


class JobError(ValueError):
    """Raised when a job manifest, state, or directory cannot be built or read."""


class JobStatus(str, Enum):
    """Lifecycle of one export job.

    ``READY`` means the artifacts are on disk but nothing has been delivered --
    it is deliberately *not* a finished state, so a later cleanup pass leaves it
    alone and the user can still retry the delivery.
    """

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    DELIVERED = "delivered"
    COPIED = "copied"
    FAILED = "failed"
    EXPIRED = "expired"


FINISHED_STATUSES = frozenset(
    {JobStatus.DELIVERED, JobStatus.COPIED, JobStatus.FAILED, JobStatus.EXPIRED}
)


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC.

    Chat sources hand out naive local timestamps.  Normalizing on construction
    keeps a freshly built manifest equal to the one read back from disk, which
    round-trip tests and duplicate detection both depend on.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    """Render a datetime as ``2026-11-15T23:07:55Z``.

    A naive value is assumed to already be UTC: every timestamp stored in a
    manifest comes from the chat source, which has no timezone information, and
    guessing a local offset would silently shift the recorded window.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime(_TIMESTAMP_FORMAT)


def parse_utc(text: str) -> datetime:
    """Inverse of :func:`format_utc`, tolerating a plain ISO 8601 offset."""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise JobError(f"invalid timestamp: {text!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def new_job_id(now: datetime | None = None) -> str:
    """Sortable, collision-resistant id such as ``20261115T230755-a1b2c3``."""
    stamp = (now or utc_now()).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of a file, so a large PDF never lands in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def message_preview(text: str, limit: int = PREVIEW_LIMIT) -> str:
    """Single-line, length-limited excerpt used for the range reference."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not _JOB_ID_PATTERN.match(job_id):
        raise JobError(f"invalid job id: {job_id!r}")
    return job_id


@dataclass(frozen=True, slots=True)
class MessageRef:
    """First/last message of the exported range.

    Borrowed from the batch-collection panel in WeChatBridge: showing the head
    and tail of a range is what lets a user confirm "I picked the right window"
    without opening the export.
    """

    id: str
    timestamp: datetime
    sender: str
    preview: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise JobError("message reference id cannot be empty")
        object.__setattr__(self, "timestamp", as_utc(self.timestamp))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": format_utc(self.timestamp),
            "sender": self.sender,
            "preview": self.preview,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MessageRef":
        try:
            return cls(
                id=str(payload["id"]),
                timestamp=parse_utc(str(payload["timestamp"])),
                sender=str(payload.get("sender", "")),
                preview=str(payload.get("preview", "")),
            )
        except KeyError as exc:
            raise JobError(f"message reference is missing {exc.args[0]!r}") from exc


@dataclass(frozen=True, slots=True)
class JobArtifact:
    """One produced file, addressed by relative name inside ``files/``.

    ``name`` is validated to be a bare filename: a manifest is data that may
    have been edited by hand, and a value like ``../../secrets`` must never be
    able to point an artifact path outside the job directory.
    """

    name: str
    kind: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not self.name or self.name != Path(self.name).name:
            raise JobError(f"artifact name must be a bare filename: {self.name!r}")
        if self.name in {".", ".."}:
            raise JobError(f"artifact name must be a bare filename: {self.name!r}")
        if self.size < 0:
            raise JobError(f"artifact size cannot be negative: {self.name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobArtifact":
        try:
            return cls(
                name=str(payload["name"]),
                kind=str(payload.get("kind", "file")),
                size=int(payload["size"]),
                sha256=str(payload["sha256"]),
            )
        except KeyError as exc:
            raise JobError(f"artifact is missing {exc.args[0]!r}") from exc
        except (TypeError, ValueError) as exc:
            raise JobError(f"artifact is malformed: {payload!r}") from exc


@dataclass(frozen=True, slots=True)
class JobManifest:
    """Immutable description of one export: provenance, range, and artifacts."""

    job_id: str
    conversation_id: str
    conversation_name: str
    created_at: datetime
    source_kind: str
    message_count: int
    source_label: str = ""
    wechat_version: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    query: str | None = None
    scene_id: str | None = None
    scene_name: str | None = None
    first_message: MessageRef | None = None
    last_message: MessageRef | None = None
    artifacts: tuple[JobArtifact, ...] = ()
    notes: tuple[str, ...] = ()
    schema_version: int = JOB_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", as_utc(self.created_at))
        if self.start is not None:
            object.__setattr__(self, "start", as_utc(self.start))
        if self.end is not None:
            object.__setattr__(self, "end", as_utc(self.end))
        _validate_job_id(self.job_id)
        if not self.conversation_id.strip():
            raise JobError("conversation_id cannot be empty")
        if not self.conversation_name.strip():
            raise JobError("conversation_name cannot be empty")
        if not self.source_kind.strip():
            raise JobError("source_kind cannot be empty")
        if self.message_count < 0:
            raise JobError("message_count cannot be negative")
        if self.schema_version < 1:
            raise JobError(f"unsupported schema version: {self.schema_version}")
        if self.start and self.end and self.start > self.end:
            raise JobError("start cannot be after end")

    def with_artifacts(
        self,
        artifacts: tuple[JobArtifact, ...] | list[JobArtifact],
        notes: tuple[str, ...] | list[str] | None = None,
    ) -> "JobManifest":
        return replace(
            self,
            artifacts=tuple(artifacts),
            notes=self.notes if notes is None else tuple(notes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "created_at": format_utc(self.created_at),
            "source": {
                "kind": self.source_kind,
                "label": self.source_label,
                "wechat_version": self.wechat_version,
            },
            "conversation": {"id": self.conversation_id, "name": self.conversation_name},
            "window": {
                "start": format_utc(self.start) if self.start else None,
                "end": format_utc(self.end) if self.end else None,
                "query": self.query,
            },
            "scene": {"id": self.scene_id, "name": self.scene_name},
            "message_count": self.message_count,
            "reference": {
                "first": self.first_message.to_dict() if self.first_message else None,
                "last": self.last_message.to_dict() if self.last_message else None,
            },
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobManifest":
        try:
            source = payload.get("source") or {}
            conversation = payload.get("conversation") or {}
            window = payload.get("window") or {}
            scene = payload.get("scene") or {}
            reference = payload.get("reference") or {}
            first = reference.get("first")
            last = reference.get("last")
            return cls(
                job_id=str(payload["job_id"]),
                conversation_id=str(conversation["id"]),
                conversation_name=str(conversation["name"]),
                created_at=parse_utc(str(payload["created_at"])),
                source_kind=str(source.get("kind", "unknown")),
                source_label=str(source.get("label", "")),
                wechat_version=source.get("wechat_version"),
                message_count=int(payload.get("message_count", 0)),
                start=parse_utc(str(window["start"])) if window.get("start") else None,
                end=parse_utc(str(window["end"])) if window.get("end") else None,
                query=window.get("query"),
                scene_id=scene.get("id"),
                scene_name=scene.get("name"),
                first_message=MessageRef.from_dict(first) if first else None,
                last_message=MessageRef.from_dict(last) if last else None,
                artifacts=tuple(
                    JobArtifact.from_dict(item) for item in payload.get("artifacts") or ()
                ),
                notes=tuple(str(note) for note in payload.get("notes") or ()),
                schema_version=int(payload.get("schema_version", JOB_SCHEMA_VERSION)),
            )
        except KeyError as exc:
            raise JobError(f"manifest is missing {exc.args[0]!r}") from exc
        except (TypeError, ValueError) as exc:
            raise JobError(f"manifest is malformed: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "JobManifest":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise JobError(f"manifest is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise JobError("manifest must be a JSON object")
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class JobState:
    """Mutable half of a job: where it is in the delivery lifecycle."""

    job_id: str
    status: JobStatus
    updated_at: datetime
    attempts: int = 0
    target: str | None = None
    destination: str | None = None
    detail: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        _validate_job_id(self.job_id)
        object.__setattr__(self, "updated_at", as_utc(self.updated_at))
        if self.attempts < 0:
            raise JobError("attempts cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "updated_at": format_utc(self.updated_at),
            "attempts": self.attempts,
            "target": self.target,
            "destination": self.destination,
            "detail": self.detail,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobState":
        try:
            status = JobStatus(str(payload["status"]))
        except (KeyError, ValueError) as exc:
            raise JobError(f"unknown job status: {payload.get('status')!r}") from exc
        try:
            return cls(
                job_id=str(payload["job_id"]),
                status=status,
                updated_at=parse_utc(str(payload.get("updated_at") or format_utc(utc_now()))),
                attempts=int(payload.get("attempts", 0)),
                target=payload.get("target"),
                destination=payload.get("destination"),
                detail=str(payload.get("detail", "")),
                error=payload.get("error"),
            )
        except KeyError as exc:
            raise JobError(f"state is missing {exc.args[0]!r}") from exc
        except (TypeError, ValueError) as exc:
            raise JobError(f"state is malformed: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A manifest, its current state, and the directory holding both."""

    manifest: JobManifest
    state: JobState
    directory: Path

    @property
    def job_id(self) -> str:
        return self.manifest.job_id

    @property
    def files_dir(self) -> Path:
        return self.directory / "files"

    @property
    def is_finished(self) -> bool:
        return self.state.status in FINISHED_STATUSES

    def artifact_path(self, artifact: JobArtifact) -> Path:
        return self.files_dir / artifact.name

    def artifact_by_kind(self, kind: str) -> JobArtifact | None:
        for artifact in self.manifest.artifacts:
            if artifact.kind == kind:
                return artifact
        return None

    def summary(self) -> str:
        """One line for a history list: id, status, conversation, volume."""
        window = ""
        if self.manifest.start or self.manifest.end:
            start = f"{self.manifest.start:%Y-%m-%d}" if self.manifest.start else "…"
            end = f"{self.manifest.end:%Y-%m-%d}" if self.manifest.end else "…"
            window = f" {start}~{end}"
        delivered = f" -> {self.state.destination}" if self.state.destination else ""
        return (
            f"{self.job_id}  {self.state.status.value:<9} "
            f"{self.manifest.conversation_name}{window} "
            f"{self.manifest.message_count} 条{delivered}"
        )


def window_text(manifest: JobManifest) -> str:
    """Human-readable range, e.g. ``2026-08-21 ~ 2026-08-22``.

    Shared by the prompt header, the Obsidian note, and the clipboard fallback so
    a range never reads three different ways in three places.
    """
    start, end = manifest.start, manifest.end
    if start and end:
        return f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"
    if start:
        return f"{start:%Y-%m-%d} 起"
    if end:
        return f"截至 {end:%Y-%m-%d}"
    return "全部"
