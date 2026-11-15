"""Delivery is a separate layer from export.

Export answers "what was in the chat"; delivery answers "where does it need to
be for anyone to use it".  Keeping them apart means a new target -- an Obsidian
vault, a shared folder, another agent -- is a small class, not a change to the
rendering pipeline.

The rule every target follows comes from WeChatBridge: a failed delivery must
still leave the user one Ctrl+V away from the content.  Targets therefore return
``status="copied"`` rather than raising when the destination is missing but the
clipboard still holds the payload; only a total failure raises.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from ..jobs import JobRecord
from ..scenes import Scene

_KIND_ORDER = {"pdf": 0, "markdown": 1, "json": 2}
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class DeliveryError(RuntimeError):
    """Raised when a target cannot deliver and cannot fall back either."""


def safe_filename(text: str, fallback: str = "chat", limit: int = 80) -> str:
    """Turn a conversation name into something Windows will accept.

    Windows rejects ``<>:"/\\|?*`` and control characters in names, strips
    trailing dots and spaces, and still has path-length limits worth respecting.
    """
    cleaned = _UNSAFE.sub("_", (text or "").strip())
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.rstrip(" .")
    if not cleaned:
        cleaned = fallback
    return cleaned[:limit].rstrip(" .") or fallback


def ordered_artifacts(job: JobRecord) -> tuple[Path, ...]:
    """Artifacts on disk, PDF first, in the order a human would open them."""
    ordered = sorted(
        job.manifest.artifacts,
        key=lambda artifact: (_KIND_ORDER.get(artifact.kind, 9), artifact.name),
    )
    return tuple(
        path
        for path in (job.artifact_path(artifact) for artifact in ordered)
        if path.is_file()
    )


def copy_artifacts(job: JobRecord, destination: Path) -> list[Path]:
    """Copy the produced files, including their ``*_assets`` sibling folders."""
    paths = ordered_artifacts(job)
    if not paths:
        raise DeliveryError(f"job {job.job_id} has no artifacts to deliver")

    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for path in paths:
        target = destination / path.name
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        copied.append(target)

    seen_assets: set[Path] = set()
    for path in paths:
        assets = path.with_name(f"{path.stem}_assets")
        if not assets.is_dir() or assets in seen_assets:
            continue
        target_assets = destination / assets.name
        if assets.resolve() == target_assets.resolve():
            continue
        seen_assets.add(assets)
        if target_assets.exists():
            shutil.rmtree(target_assets, ignore_errors=True)
        shutil.copytree(assets, target_assets)
    return copied


@dataclass(frozen=True, slots=True)
class DeliveryRequest:
    """Everything a target needs: the job on disk plus the words to send."""

    job: JobRecord
    scene: Scene | None = None
    prompt: str | None = None

    @property
    def artifacts(self) -> tuple[Path, ...]:
        return ordered_artifacts(self.job)

    @property
    def conversation(self) -> str:
        return self.job.manifest.conversation_name


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    target: str
    status: str
    destination: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"delivered", "copied"}

    def describe(self) -> str:
        label = {
            "delivered": "已投递",
            "copied": "已复制，等待手动粘贴",
            "failed": "投递失败",
        }.get(self.status, self.status)
        where = f" -> {self.destination}" if self.destination else ""
        note = f"（{self.detail}）" if self.detail else ""
        return f"{label}{where}{note}"


class DeliveryTarget(Protocol):
    name: str

    def deliver(self, request: DeliveryRequest) -> DeliveryResult: ...


def paths_as_text(paths: Sequence[Path]) -> str:
    """Newline list of absolute paths, used by prompt-only targets."""
    return "\n".join(str(Path(path).expanduser().resolve()) for path in paths)
