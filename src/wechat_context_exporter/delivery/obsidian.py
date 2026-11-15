"""Write into an Obsidian vault: one note per export, attachments alongside.

Obsidian is a folder of Markdown, so "integration" is just writing files in the
right place.  Two details decide whether the result is usable:

* the note must carry frontmatter, otherwise every export looks the same in
  search and in Dataview queries;
* attachments must be copied next to the note and linked *relatively*, because
  the transcript's own image links are relative to the folder it sits in.

The note therefore points at a copied ``_附件/<job_id>/`` folder rather than at
the job directory, which lives outside the vault and may be pruned later.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .base import (
    DeliveryError,
    DeliveryRequest,
    DeliveryResult,
    copy_artifacts,
    ordered_artifacts,
    safe_filename,
)
from ..jobs.models import format_utc, window_text

DEFAULT_FOLDER = "微信记忆"
DEFAULT_ATTACHMENTS = "_附件"


class ObsidianDelivery:
    name = "obsidian"

    def __init__(
        self,
        vault: Path | str,
        *,
        folder: str = DEFAULT_FOLDER,
        attachments: str = DEFAULT_ATTACHMENTS,
    ) -> None:
        self.vault = Path(vault).expanduser().resolve()
        self.folder = folder
        self.attachments = attachments

    def destination_for(self, request: DeliveryRequest) -> Path:
        month = request.job.manifest.created_at.strftime("%Y-%m")
        stamp = request.job.manifest.created_at.strftime("%Y-%m-%d")
        name = f"{stamp} {safe_filename(request.conversation)}.md"
        return self.vault / self.folder / month / name

    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        if not self.vault.is_dir():
            raise DeliveryError(f"Obsidian vault not found: {self.vault}")

        note_path = self.destination_for(request)
        attachment_dir = self.vault / self.folder / self.attachments / request.job.job_id
        try:
            note_path.parent.mkdir(parents=True, exist_ok=True)
            copy_artifacts(request.job, attachment_dir)
            note_path.write_text(self._render(request, note_path, attachment_dir), encoding="utf-8")
        except OSError as exc:
            raise DeliveryError(f"cannot write note to {note_path}: {exc}") from exc

        return DeliveryResult(
            target=self.name,
            status="delivered",
            destination=str(note_path),
            detail=f"附件在 {attachment_dir.name}/",
        )

    # -- rendering -------------------------------------------------------

    def _render(self, request: DeliveryRequest, note_path: Path, attachment_dir: Path) -> str:
        manifest = request.job.manifest
        links = []
        for path in ordered_artifacts(request.job):
            copied = attachment_dir / path.name
            links.append(f"[{path.name}](<{_relative(copied, note_path.parent)}>)")

        heading_date = manifest.end or manifest.start or manifest.created_at

        lines = [
            "---",
            "source: wechat",
            f"conversation: {json.dumps(manifest.conversation_name, ensure_ascii=False)}",
            f"conversation_id: {json.dumps(manifest.conversation_id, ensure_ascii=False)}",
            f"job_id: {manifest.job_id}",
            f"exported_at: {format_utc(manifest.created_at)}",
            f"window_start: {manifest.start:%Y-%m-%d}" if manifest.start else "window_start:",
            f"window_end: {manifest.end:%Y-%m-%d}" if manifest.end else "window_end:",
            f"message_count: {manifest.message_count}",
            f"scene: {json.dumps(request.scene.name, ensure_ascii=False)}" if request.scene else "scene:",
            "tags:",
            "  - 微信记忆",
            f"  - {json.dumps(safe_filename(manifest.conversation_name), ensure_ascii=False)}",
            "---",
            "",
            f"# {manifest.conversation_name} · {heading_date:%Y-%m-%d}",
            "",
            f"- 归档：{' · '.join(links)}",
        ]

        window = window_text(manifest)
        lines.append(f"- 范围：{window}｜{manifest.message_count} 条消息")
        if manifest.query:
            lines.append(f"- 关键词：{manifest.query}")
        lines.append(f"- 任务号：`{manifest.job_id}`")

        if request.prompt:
            lines.extend(["", "## 交给 Agent 的任务", "", request.prompt])

        if manifest.notes:
            lines.extend(["", "## 备注", ""])
            lines.extend(f"- {note}" for note in manifest.notes)

        lines.append("")
        return "\n".join(lines)


def _relative(target: Path, start: Path) -> str:
    try:
        return Path(os.path.relpath(target, start)).as_posix()
    except ValueError:
        return target.as_posix()
