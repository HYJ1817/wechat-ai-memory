"""Where user-visible artifacts go.

Exports used to land wherever the caller happened to be: `Documents`, the
current working directory, or a `--output` the user typed by hand.  One root keeps
the archive findable, and one environment variable keeps it relocatable without
touching code.

What does *not* live here: the job store (`%LOCALAPPDATA%\\WeChatAIMemory\\jobs`).
That directory holds staging files, manifests, and per-job hashes -- internal
state that the user should not have to curate, and that must survive a cleanup of
the archive folder.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR_ENV = "WECHAT_AI_MEMORY_OUTPUT_DIR"

_WINDOWS_ROOT = Path("C:/微信记忆")
_POSIX_ROOT_NAME = "微信记忆"


def default_output_root() -> Path:
    """The archive root: ``C:\\微信记忆`` on Windows, ``~/微信记忆`` elsewhere."""
    override = os.environ.get(OUTPUT_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return _WINDOWS_ROOT
    return Path.home() / _POSIX_ROOT_NAME


def output_root(*, create: bool = False) -> Path:
    """The archive root, optionally created.

    Creation is best effort: if the path is on a disconnected drive the export
    should still fail with the real error from the write, not from here.
    """
    root = default_output_root()
    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return root


def default_export_path(stem: str, suffix: str = ".pdf") -> Path:
    """``C:\\微信记忆\\<stem>.pdf`` with the folder created on demand."""
    root = output_root(create=True)
    return root / f"{stem}{suffix}"
