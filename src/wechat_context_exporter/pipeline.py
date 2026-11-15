"""One export, end to end: record it as a job, then deliver it.

The point of this module is that an export has a *lifecycle*, not just an output
path.  Calling :func:`run_export` with a :class:`JobStore` produces:

1. a staging directory that receives every artifact,
2. one atomic rename that publishes it under ``Ready/<job_id>/``,
3. a manifest with provenance, range, head/tail reference, and per-file hashes,
4. a rendered prompt when a scene was given,
5. a delivery result written back into ``state.json``.

Every step after (2) can fail without losing the archive: the job stays on disk
with a state that says what happened, which is what makes "retry the delivery"
possible at all.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from .delivery import (
    ClipboardDelivery,
    DeliveryError,
    DeliveryRequest,
    DeliveryResult,
    DeliveryTarget,
    ordered_artifacts,
    safe_filename,
)
from .jobs import (
    JobManifest,
    JobRecord,
    JobStatus,
    JobStore,
    MessageRef,
    collect_artifacts,
    message_preview,
    new_job_id,
    utc_now,
)
from .models import Conversation, Message, MessageType
from .scenes import Scene, render_prompt
from .service import (
    ExportOptions,
    ExportResult,
    ExportService,
    ProgressCallback,
    find_conversation,
    select_messages,
)
from .sources import ChatSource


@dataclass(frozen=True, slots=True)
class RunResult:
    export: ExportResult
    job: JobRecord | None = None
    delivery: DeliveryResult | None = None
    prompt: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def job_id(self) -> str | None:
        return self.job.job_id if self.job else None

    @property
    def ok(self) -> bool:
        return self.delivery is None or self.delivery.ok


def run_export(
    source: ChatSource,
    options: ExportOptions,
    *,
    store: JobStore | None = None,
    scene: Scene | None = None,
    target: DeliveryTarget | None = None,
    progress: ProgressCallback | None = None,
    clipboard_fallback: DeliveryTarget | None = None,
) -> RunResult:
    """Export ``options`` from ``source``, optionally recording and delivering it.

    Without ``store`` this is the old one-shot export: no job directory, no
    delivery, no prompt.
    """
    if store is None:
        return RunResult(export=ExportService().export(source, options, progress))

    conversation = find_conversation(source, options.conversation_id)
    messages = select_messages(source, options)
    manifest = _build_manifest(source, options, conversation, messages, scene)

    handle = store.begin(manifest)
    try:
        export_options = _redirect_to_job(options, handle.files_dir, conversation, scene)
        export = ExportService().export(source, export_options, progress)
    except BaseException as exc:
        handle.abort(f"{type(exc).__name__}: {exc}")
        raise

    record = handle.commit(collect_artifacts(handle.files_dir), _notes(messages))
    export = _final_paths(export, record)

    prompt = (
        render_prompt(scene, record.manifest, ordered_artifacts(record))
        if scene is not None
        else None
    )

    delivery: DeliveryResult | None = None
    if target is not None:
        request = DeliveryRequest(job=record, scene=scene, prompt=prompt)
        delivery, record = _deliver(
            store, record, request, target, clipboard_fallback or ClipboardDelivery()
        )

    return RunResult(export=export, job=record, delivery=delivery, prompt=prompt)


# -- delivery -------------------------------------------------------------


def _deliver(
    store: JobStore,
    record: JobRecord,
    request: DeliveryRequest,
    target: DeliveryTarget,
    fallback: DeliveryTarget,
) -> tuple[DeliveryResult, JobRecord]:
    try:
        result = target.deliver(request)
    except DeliveryError as exc:
        return _fall_back(store, record, request, target, exc, fallback)

    status = JobStatus.DELIVERED if result.status == "delivered" else JobStatus.COPIED
    record = store.set_state(
        record,
        status,
        target=result.target,
        destination=result.destination,
        detail=result.detail,
    )
    return result, record


def _fall_back(
    store: JobStore,
    record: JobRecord,
    request: DeliveryRequest,
    target: DeliveryTarget,
    error: DeliveryError,
    fallback: DeliveryTarget,
) -> tuple[DeliveryResult, JobRecord]:
    """A failed target must still leave the content one Ctrl+V away."""
    try:
        result = fallback.deliver(request)
    except DeliveryError as second:
        record = store.set_state(
            record,
            JobStatus.FAILED,
            target=target.name,
            error=f"{error}; 剪贴板兜底也失败: {second}",
            detail=f"{target.name} 投递失败",
        )
        return (
            DeliveryResult(target=target.name, status="failed", detail=str(error)),
            record,
        )

    detail = f"{target.name} 投递失败（{error}），已改为{result.detail}"
    record = store.set_state(
        record,
        JobStatus.COPIED,
        target=result.target,
        destination=result.destination,
        detail=detail,
    )
    return replace(result, detail=detail), record


def _final_paths(export: ExportResult, record: JobRecord) -> ExportResult:
    """Repoint the export result at ``Ready/`` after the atomic rename.

    The renderer wrote to ``.staging/.../files``; that path is gone the moment the
    job is committed, so reporting it to the user would hand back a dead path.
    """
    markdown = record.artifact_by_kind("markdown")
    normalized = record.artifact_by_kind("json")
    pdf = record.artifact_by_kind("pdf")
    return replace(
        export,
        pdf_path=record.artifact_path(pdf) if pdf else export.pdf_path,
        markdown_path=record.artifact_path(markdown) if markdown else None,
        json_path=record.artifact_path(normalized) if normalized else None,
    )


def mirror_export(export: ExportResult, target_pdf: Path) -> ExportResult:
    """Copy the job's files next to a user-chosen path.

    Recording redirects every output into the job directory, so the path a user
    picked in a save dialog would otherwise stay empty.  The companions follow the
    same stem (``a.pdf`` next to ``a.md`` / ``a.json``) because that is how the
    unrecorded export always behaved.

    Best effort by design: a failed copy must not turn a successful export into an
    error dialog.  The job directory still holds everything.
    """
    target = Path(target_pdf).expanduser().resolve()
    produced = export.pdf_path
    try:
        if not produced.is_file() or produced.resolve() == target:
            return export
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced, target)

        markdown = export.markdown_path
        if markdown is not None and markdown.is_file():
            shutil.copy2(markdown, target.with_suffix(".md"))
        normalized = export.json_path
        if normalized is not None and normalized.is_file():
            shutil.copy2(normalized, target.with_suffix(".json"))

        assets = produced.with_name(f"{produced.stem}_assets")
        if assets.is_dir():
            destination = target.parent / f"{target.stem}_assets"
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            shutil.copytree(assets, destination)
    except OSError:
        return export

    return replace(
        export,
        pdf_path=target,
        markdown_path=target.with_suffix(".md") if export.markdown_path else None,
        json_path=target.with_suffix(".json") if export.json_path else None,
    )


# -- manifest -------------------------------------------------------------

def _build_manifest(
    source: ChatSource,
    options: ExportOptions,
    conversation: Conversation,
    messages: Sequence[Message],
    scene: Scene | None,
) -> JobManifest:
    first = messages[0] if messages else None
    last = messages[-1] if messages else None
    return JobManifest(
        job_id=new_job_id(),
        conversation_id=conversation.id,
        conversation_name=conversation.name,
        created_at=utc_now(),
        source_kind=_source_kind(source),
        source_label=_source_label(source),
        wechat_version=_wechat_version(source),
        message_count=len(messages),
        start=options.start,
        end=options.end,
        query=options.query,
        scene_id=scene.id if scene else None,
        scene_name=scene.name if scene else None,
        first_message=_reference(first) if first else None,
        last_message=_reference(last) if last else None,
    )


def _reference(message: Message) -> MessageRef:
    return MessageRef(
        id=message.id,
        timestamp=message.timestamp,
        sender=message.sender,
        preview=message_preview(_preview_text(message)),
    )


def _preview_text(message: Message) -> str:
    if message.type is MessageType.IMAGE:
        return "[图片]"
    if message.type is MessageType.FILE:
        return f"[文件] {Path(message.content).name}"
    if message.type is MessageType.VOICE:
        return f"[语音] {message.transcript or ''}".strip()
    return message.content


def _notes(messages: Sequence[Message]) -> tuple[str, ...]:
    notes: list[str] = []
    if not messages:
        notes.append("没有消息符合当前筛选条件")
    untranscribed = [
        message
        for message in messages
        if message.type is MessageType.VOICE and not (message.transcript or "").strip()
    ]
    if untranscribed:
        notes.append(f"语音 {len(untranscribed)} 条未转写")
    images = sum(1 for message in messages if message.type is MessageType.IMAGE)
    if images:
        notes.append(f"图片 {images} 张")
    files = sum(1 for message in messages if message.type is MessageType.FILE)
    if files:
        notes.append(f"文件 {files} 个")
    return tuple(notes)


def _source_kind(source: ChatSource) -> str:
    name = type(source).__name__
    for suffix in ("ChatSource", "Source"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    return name.lower() or "unknown"


def _source_label(source: ChatSource) -> str:
    path = getattr(source, "path", None)
    if path:
        return str(path)
    account = getattr(source, "account", None)
    if account is not None:
        for attribute in ("account_dir", "id"):
            value = getattr(account, attribute, None)
            if value:
                return str(value)
    return type(source).__name__


def _wechat_version(source: ChatSource) -> str | None:
    holders = [source, getattr(source, "account", None)]
    for holder in holders:
        if holder is None:
            continue
        for attribute in ("wechat_version", "version"):
            value = getattr(holder, attribute, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


# -- output redirection ---------------------------------------------------


def _redirect_to_job(
    options: ExportOptions,
    files_dir: Path,
    conversation: Conversation,
    scene: Scene | None,
) -> ExportOptions:
    """Point every output at the job's ``files/`` directory.

    Callers keep passing the paths they care about; recording wins, because a job
    that writes half its artifacts outside its own directory cannot be moved,
    hashed, or delivered as a unit.
    """
    name = safe_filename(conversation.name)
    wants_markdown = options.markdown_path is not None or bool(scene and scene.markdown)
    wants_json = options.json_path is not None or bool(scene and scene.json_output)
    return replace(
        options,
        output_pdf=files_dir / f"{name}.pdf",
        markdown_path=files_dir / f"{name}.md" if wants_markdown else None,
        json_path=files_dir / f"{name}.json" if wants_json else None,
    )
