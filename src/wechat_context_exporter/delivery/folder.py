"""Write the archive into a plain folder, one folder per conversation per day."""

from __future__ import annotations

from pathlib import Path

from .base import (
    DeliveryError,
    DeliveryRequest,
    DeliveryResult,
    copy_artifacts,
    safe_filename,
)

PROMPT_FILENAME = "给 Agent 的提示词.txt"


class FolderDelivery:
    """The simplest target: a directory the user already browses.

    Naming follows ``2026-11-15 生态项目组/`` so ten exports of the same group
    line up chronologically in Explorer instead of overwriting each other.
    """

    name = "folder"

    def __init__(self, root: Path | str, *, organize_by_date: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        self.organize_by_date = organize_by_date

    def destination_for(self, request: DeliveryRequest) -> Path:
        conversation = safe_filename(request.conversation)
        if not self.organize_by_date:
            return self.root / conversation
        stamp = request.job.manifest.created_at.strftime("%Y-%m-%d")
        return self.root / f"{stamp} {conversation}"

    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        destination = self.destination_for(request)
        try:
            copied = copy_artifacts(request.job, destination)
            if request.prompt:
                (destination / PROMPT_FILENAME).write_text(request.prompt, encoding="utf-8")
        except OSError as exc:
            raise DeliveryError(f"cannot write to {destination}: {exc}") from exc

        detail = f"{len(copied)} 个文件"
        if request.prompt:
            detail += f" + {PROMPT_FILENAME}"
        return DeliveryResult(
            target=self.name,
            status="delivered",
            destination=str(destination),
            detail=detail,
        )
