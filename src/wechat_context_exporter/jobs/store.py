"""On-disk layout and lifecycle for export jobs.

```
<jobs_root>/
├── .staging/<jobId>/        # 写入中，任何结束方式都会离开这里
│   ├── manifest.json
│   ├── state.json
│   └── files/               # PDF / Markdown / JSON / *_assets/
├── Ready/<jobId>/           # 原子提交后的成品
├── Failed/<jobId>/          # 失败或中断，保留以便排查
└── Logs/<YYYY-MM-DD>.log
```

The split matters for durability: a job is written into ``.staging`` and only
becomes visible under ``Ready`` once its bytes are complete and hashed.  A
crash therefore leaves either nothing or a complete job -- never a half-written
PDF that looks deliverable.  ``Failed`` keeps the wreckage instead of deleting
it, because the interesting question after a failure is *what* was produced.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from .models import (
    JobArtifact,
    JobError,
    JobManifest,
    JobRecord,
    JobState,
    JobStatus,
    format_utc,
    sha256_file,
    utc_now,
)

MANIFEST_NAME = "manifest.json"
STATE_NAME = "state.json"
FILES_DIR = "files"
READY_DIR = "Ready"
FAILED_DIR = "Failed"
STAGING_DIR = ".staging"
LOG_DIR = "Logs"


def default_jobs_dir() -> Path:
    """Where jobs live when the caller does not say.

    Follows the app's existing cache convention (``%LOCALAPPDATA%\\WeChatAIMemory``,
    already used for the transcription model and voice cache).
    ``WECHAT_AI_MEMORY_JOBS_DIR`` overrides it -- used by the test suite so a GUI
    test never records into the user's real job history, and by portable installs.
    """
    override = os.environ.get("WECHAT_AI_MEMORY_JOBS_DIR")
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "WeChatAIMemory" / "jobs"
    return Path.home() / ".wechat-ai-memory" / "jobs"


def _atomic_write(path: Path, text: str) -> None:
    """Write via ``.tmp`` + replace so a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


class JobHandle:
    """An in-progress job; nothing is visible under ``Ready`` until commit."""

    def __init__(self, store: "JobStore", manifest: JobManifest, staging: Path) -> None:
        self._store = store
        self.manifest = manifest
        self.staging = staging
        self._settled = False

    @property
    def directory(self) -> Path:
        return self.staging

    @property
    def files_dir(self) -> Path:
        path = self.staging / FILES_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def commit(
        self,
        artifacts: Sequence[JobArtifact] | None = None,
        notes: Sequence[str] | None = None,
    ) -> JobRecord:
        """Finish the job and publish it under ``Ready`` in one rename."""
        if self._settled:
            raise JobError(f"job {self.manifest.job_id} is already committed or aborted")

        manifest = self.manifest.with_artifacts(artifacts or (), notes)
        state = JobState(
            job_id=manifest.job_id,
            status=JobStatus.READY,
            updated_at=utc_now(),
            attempts=0,
        )
        target = self._store.ready_dir / manifest.job_id
        if target.exists():
            raise JobError(f"job already exists: {manifest.job_id}")

        self._write(manifest, state)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.staging.rename(target)
        self.staging = target
        self._settled = True
        self._store.log(manifest.job_id, "committed")
        return JobRecord(manifest=manifest, state=state, directory=target)

    def abort(self, error: str) -> JobRecord:
        """Move the wreckage to ``Failed`` and record why it stopped."""
        if self._settled:
            raise JobError(f"job {self.manifest.job_id} is already committed or aborted")

        manifest = self.manifest
        state = JobState(
            job_id=manifest.job_id,
            status=JobStatus.FAILED,
            updated_at=utc_now(),
            attempts=0,
            error=error,
        )
        target = self._store.failed_dir / manifest.job_id
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{target.name}-{utc_now():%H%M%S%f}")
            target.parent.mkdir(parents=True, exist_ok=True)

        self._write(manifest, state)
        shutil.move(str(self.staging), str(target))
        self.staging = target
        self._settled = True
        self._store.log(manifest.job_id, f"failed: {error}")
        return JobRecord(manifest=manifest, state=state, directory=target)

    def _write(self, manifest: JobManifest, state: JobState) -> None:
        _atomic_write(self.staging / MANIFEST_NAME, manifest.to_json())
        _atomic_write(self.staging / STATE_NAME, state.to_json())

    def __enter__(self) -> "JobHandle":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if not self._settled:
            self.abort(f"{exc_type.__name__}: {exc}" if exc else "job was never committed")
        return False


class JobStore:
    """Reads and writes the job directory tree."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.ready_dir = self.root / READY_DIR
        self.failed_dir = self.root / FAILED_DIR
        self.staging_dir = self.root / STAGING_DIR
        self.log_dir = self.root / LOG_DIR
        self.last_warnings: list[str] = []

    # -- writing ---------------------------------------------------------

    def begin(self, manifest: JobManifest) -> JobHandle:
        """Create a staging directory for ``manifest`` and mark it running."""
        staging = self.staging_dir / manifest.job_id
        for candidate in (staging, self.ready_dir / manifest.job_id, self.failed_dir / manifest.job_id):
            if candidate.exists():
                raise JobError(f"job already exists: {manifest.job_id}")

        (staging / FILES_DIR).mkdir(parents=True, exist_ok=True)
        state = JobState(
            job_id=manifest.job_id,
            status=JobStatus.RUNNING,
            updated_at=utc_now(),
            attempts=0,
        )
        _atomic_write(staging / MANIFEST_NAME, manifest.to_json())
        _atomic_write(staging / STATE_NAME, state.to_json())
        self.log(manifest.job_id, f"started ({manifest.conversation_name})")
        return JobHandle(self, manifest, staging)

    def set_state(
        self,
        record: JobRecord | str,
        status: JobStatus,
        *,
        target: str | None = None,
        destination: str | None = None,
        detail: str = "",
        error: str | None = None,
        count_attempt: bool = True,
    ) -> JobRecord:
        """Rewrite ``state.json`` for a job that already exists on disk."""
        job_record = self.load(record) if isinstance(record, str) else record
        attempts = job_record.state.attempts
        if count_attempt and status in {
            JobStatus.DELIVERED,
            JobStatus.COPIED,
            JobStatus.FAILED,
        }:
            attempts += 1

        state = JobState(
            job_id=job_record.job_id,
            status=status,
            updated_at=utc_now(),
            attempts=attempts,
            target=target if target is not None else job_record.state.target,
            destination=(
                destination if destination is not None else job_record.state.destination
            ),
            detail=detail,
            error=error,
        )
        _atomic_write(job_record.directory / STATE_NAME, state.to_json())
        self.log(job_record.job_id, f"state={status.value} {destination or ''}".strip())
        return replace(job_record, state=state)

    def log(self, job_id: str, message: str) -> None:
        """Append a line to the daily log; never let logging break an export."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            line = f"{format_utc(utc_now())}\t{job_id}\t{message}\n"
            with (self.log_dir / f"{utc_now():%Y-%m-%d}.log").open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass

    # -- reading ---------------------------------------------------------

    def load(self, job_id: str) -> JobRecord:
        for base in (self.ready_dir, self.failed_dir, self.staging_dir):
            candidate = base / job_id
            if candidate.is_dir():
                return self._load_dir(candidate)
        raise JobError(f"job not found: {job_id}")

    def list_jobs(
        self,
        *,
        limit: int | None = None,
        include_staging: bool = False,
    ) -> list[JobRecord]:
        """All readable jobs, newest first.

        A directory that cannot be parsed is skipped and reported in
        ``last_warnings`` instead of aborting the listing: one truncated
        manifest must not hide the other twenty jobs.
        """
        self.last_warnings = []
        bases: list[Path] = [self.ready_dir, self.failed_dir]
        if include_staging:
            bases.append(self.staging_dir)

        records: list[JobRecord] = []
        for base in bases:
            for entry in self._iter_dirs(base):
                try:
                    records.append(self._load_dir(entry))
                except (JobError, OSError) as exc:
                    self.last_warnings.append(f"{entry.name}: {exc}")
        records.sort(key=lambda record: record.manifest.created_at, reverse=True)
        return records[:limit] if limit is not None else records

    def recover_stale(self) -> list[str]:
        """Move abandoned staging directories to ``Failed``.

        Called before a new run so an interrupted export cannot masquerade as
        an in-progress one, and so its artifacts stay inspectable.
        """
        recovered: list[str] = []
        for entry in self._iter_dirs(self.staging_dir):
            try:
                record = self._load_dir(entry)
                error = "interrupted before commit"
            except (JobError, OSError) as exc:
                record = None
                error = f"interrupted with an unreadable manifest: {exc}"

            target = self.failed_dir / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target = target.with_name(f"{target.name}-{utc_now():%Y%m%d%H%M%S}")
            try:
                if record is not None:
                    state = JobState(
                        job_id=record.job_id,
                        status=JobStatus.FAILED,
                        updated_at=utc_now(),
                        attempts=max(1, record.state.attempts),
                        error=error,
                    )
                    _atomic_write(entry / STATE_NAME, state.to_json())
                shutil.move(str(entry), str(target))
            except OSError as exc:
                self.last_warnings.append(f"{entry.name}: could not be recovered ({exc})")
                continue
            self.log(entry.name, error)
            recovered.append(entry.name)
        return recovered

    def prune(
        self,
        older_than_days: int = 30,
        *,
        keep_unfinished: bool = True,
        now: datetime | None = None,
    ) -> list[str]:
        """Delete old finished jobs.

        ``keep_unfinished`` defaults to True: a job that was never delivered is
        the user's only copy of that export, so age alone must not remove it.
        """
        if older_than_days < 0:
            raise ValueError("older_than_days cannot be negative")
        cutoff = (now or utc_now()) - timedelta(days=older_than_days)
        removed: list[str] = []
        for record in self.list_jobs():
            if keep_unfinished and not record.is_finished:
                continue
            if record.state.updated_at > cutoff:
                continue
            if not self._owns(record.directory):
                self.last_warnings.append(f"{record.job_id}: outside the job root, skipped")
                continue
            shutil.rmtree(record.directory, ignore_errors=True)
            removed.append(record.job_id)
        for job_id in removed:
            self.log(job_id, "pruned")
        return removed

    # -- internals -------------------------------------------------------

    def _owns(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.root)
        except (OSError, ValueError):
            return False

    @staticmethod
    def _iter_dirs(base: Path) -> list[Path]:
        try:
            if not base.is_dir():
                return []
            return sorted(
                (entry for entry in base.iterdir() if entry.is_dir()),
                key=lambda entry: entry.name,
                reverse=True,
            )
        except OSError:
            return []

    @staticmethod
    def _load_dir(directory: Path) -> JobRecord:
        manifest_path = directory / MANIFEST_NAME
        state_path = directory / STATE_NAME
        try:
            manifest = JobManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise JobError(f"cannot read manifest: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise JobError(f"manifest is not UTF-8: {exc}") from exc

        try:
            state = JobState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
        except OSError:
            state = JobState(
                job_id=manifest.job_id,
                status=JobStatus.PENDING,
                updated_at=manifest.created_at,
            )
        except (json.JSONDecodeError, JobError):
            state = JobState(
                job_id=manifest.job_id,
                status=JobStatus.PENDING,
                updated_at=manifest.created_at,
            )
        return JobRecord(manifest=manifest, state=state, directory=directory)


def collect_artifacts(files_dir: Path) -> list[JobArtifact]:
    """Describe every produced file in ``files_dir``.

    Attachments live in a sibling ``*_assets`` directory, whose individual files
    are not enumerated: a chat with 300 images would otherwise dominate the
    manifest, and the directory is copied as a unit by every delivery target.
    """
    artifacts: list[JobArtifact] = []
    if not files_dir.is_dir():
        return artifacts
    for path in sorted(files_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".pdf", ".md", ".json"}:
            continue
        artifacts.append(
            JobArtifact(
                name=path.name,
                kind={".pdf": "pdf", ".md": "markdown", ".json": "json"}.get(
                    path.suffix.lower(), "file"
                ),
                size=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return artifacts
