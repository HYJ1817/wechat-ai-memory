from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..models import Conversation, Message


class SourceError(RuntimeError):
    """Raised when a chat source cannot be read or validated."""


# Probing a path that lives on a malfunctioning or disconnected device raises
# OSError on Windows instead of returning False -- a cloud-drive mount (115,
# Aliyun Drive, ...) or a dropped network share produces "[WinError 31] A
# device attached to the system is not functioning".  Directory walks fail the
# same way.  Every filesystem probe in this package goes through the helpers
# below so one bad path can never abort a whole scan.


def safe_is_dir(path: Path) -> bool:
    """`Path.is_dir()`, treating an inaccessible path as 'not a directory'."""
    try:
        return path.is_dir()
    except OSError:
        return False


def safe_is_file(path: Path) -> bool:
    """`Path.is_file()`, treating an inaccessible path as 'not a file'."""
    try:
        return path.is_file()
    except OSError:
        return False


def safe_size(path: Path) -> int | None:
    """Size in bytes, or None when the path cannot be stat'ed."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def safe_mtime_ns(path: Path) -> int:
    """Modification time in nanoseconds, or 0 when the path cannot be stat'ed.

    Suitable as a sort key: paths that cannot be inspected sort last.
    """
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def newest_files(root: Path, pattern: str) -> list[Path]:
    """Files under `root` matching `pattern`, newest first.

    Tolerates a directory that cannot be walked and a file that cannot be
    stat'ed; either would otherwise abort the entire scan.
    """
    try:
        candidates = list(root.rglob(pattern))
    except OSError:
        return []
    return sorted(candidates, key=safe_mtime_ns, reverse=True)


class ChatSource(Protocol):
    def list_conversations(self) -> list[Conversation]: ...

    def get_messages(
        self,
        conversation_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Message]: ...

