"""Hand the archive to a running agent: activate it, paste, get out of the way.

This is the piece an archive tool usually lacks.  Writing a PDF next to the chat
does not help anyone at 11pm; the useful action is "open Claude, put the paths
and the question in the box, leave the cursor there".

``path_only`` mirrors what WeChatBridge had to learn per app: some agents accept
dropped files, others only read a path from the text box.  Defaulting to paths in
the prompt is the version that works everywhere, and the files are still one
drag away.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from .base import DeliveryError, DeliveryRequest, DeliveryResult
from .clipboard import fallback_text


class AgentBackend(Protocol):
    def copy(self, *, text: str | None = None, files: Sequence[Path] = ()) -> bool: ...

    def activate(self, app: str) -> bool: ...

    def paste(self) -> bool: ...


class AgentDelivery:
    """Copy the prompt, focus the target app, paste."""

    name = "agent"

    def __init__(
        self,
        app: str,
        *,
        backend: AgentBackend | None = None,
        path_only: bool = True,
        dry_run: bool = False,
    ) -> None:
        if not app.strip():
            raise DeliveryError("agent target needs an application name")
        self.app = app.strip()
        self.backend = backend
        self.path_only = path_only
        self.dry_run = dry_run

    def deliver(self, request: DeliveryRequest) -> DeliveryResult:
        text = request.prompt or fallback_text(request)
        files = () if self.path_only else request.artifacts

        backend = self._resolve_backend()
        try:
            copied = backend.copy(text=text, files=files)
        except OSError as exc:
            raise DeliveryError(f"clipboard is unavailable: {exc}") from exc
        if not copied:
            raise DeliveryError("clipboard refused the payload, so pasting is impossible")

        if self.dry_run:
            return DeliveryResult(
                target=self.name,
                status="copied",
                detail=f"dry run：未唤起 {self.app}",
            )
        if not backend.activate(self.app):
            return DeliveryResult(
                target=self.name,
                status="copied",
                detail=f"未找到 {self.app} 的窗口，内容已在剪贴板，Ctrl+V 即可",
            )
        if not backend.paste():
            return DeliveryResult(
                target=self.name,
                status="copied",
                destination=self.app,
                detail="已激活窗口，自动粘贴失败，Ctrl+V 即可",
            )
        return DeliveryResult(
            target=self.name,
            status="delivered",
            destination=self.app,
            detail="已激活并粘贴提示词",
        )

    def _resolve_backend(self) -> AgentBackend:
        if self.backend is None:
            from .win32 import Win32Clipboard

            self.backend = Win32Clipboard()
        return self.backend
