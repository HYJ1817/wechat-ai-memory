"""Put the archive (and the prompt) on the clipboard, files included."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from ..jobs.models import window_text
from .base import DeliveryError, DeliveryRequest, DeliveryResult


class ClipboardBackend(Protocol):
    def copy(self, *, text: str | None = None, files: Sequence[Path] = ()) -> bool: ...


def fallback_text(request: DeliveryRequest) -> str:
    """Plain-text description used when the caller supplied no prompt."""
    manifest = request.job.manifest
    lines = [
        f"微信聊天归档：{manifest.conversation_name}"
        f"（{window_text(manifest)}，{manifest.message_count} 条）"
    ]
    lines.extend(f"- {path}" for path in request.artifacts)
    return "\n".join(lines)


class ClipboardDelivery:
    """The universal fallback: nothing to install, nothing to configure.

    ``CF_HDROP`` and ``CF_UNICODETEXT`` are set in the same clipboard session, so
    a single Ctrl+V into an agent gives it both the instruction text and the
    files as attachments.
    """

    name = "clipboard"

    def __init__(self, backend: ClipboardBackend | None = None) -> None:
        self.backend = backend

    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        files = request.artifacts
        text = request.prompt or fallback_text(request)
        if not text and not files:
            raise DeliveryError("nothing to copy: the job has no artifacts and no prompt")

        backend = self._resolve_backend()
        try:
            copied = backend.copy(text=text, files=files)
        except OSError as exc:
            raise DeliveryError(f"clipboard is unavailable: {exc}") from exc
        if not copied:
            raise DeliveryError("clipboard refused the payload")

        detail = f"{len(files)} 个文件 + {len(text)} 字"
        return DeliveryResult(target=self.name, status="copied", detail=detail)

    def _resolve_backend(self) -> ClipboardBackend:
        if self.backend is None:
            from .win32 import Win32Clipboard

            self.backend = Win32Clipboard()
        return self.backend
