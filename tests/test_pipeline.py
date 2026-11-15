from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from wechat_context_exporter.delivery import DeliveryError, DeliveryResult, FolderDelivery
from wechat_context_exporter.jobs import JobStatus, JobStore
from wechat_context_exporter.pipeline import mirror_export, run_export
from wechat_context_exporter.scenes import Scene
from wechat_context_exporter.service import ExportOptions, ExportService
from wechat_context_exporter.sources import JsonChatSource

SOURCE = "examples/demo_chat.json"


class FailingTarget:
    name = "obsidian"

    def __init__(self, message: str = "vault not found") -> None:
        self.message = message

    def deliver(self, request):
        raise DeliveryError(self.message)


class FakeClipboard:
    name = "clipboard"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests = []

    def deliver(self, request):
        self.requests.append(request)
        if self.fail:
            raise DeliveryError("clipboard refused the payload")
        return DeliveryResult(target="clipboard", status="copied", detail="3 个文件 + 80 字")


def options(**overrides) -> ExportOptions:
    payload = {
        "conversation_id": "eco-project",
        "output_pdf": Path("unused.pdf"),
        "start": datetime(2026, 8, 1),
        "end": datetime(2026, 8, 31),
    }
    payload.update(overrides)
    return ExportOptions(**payload)


def source() -> JsonChatSource:
    return JsonChatSource(SOURCE)


def test_one_shot_export_does_not_record(tmp_path):
    result = run_export(source(), options(output_pdf=tmp_path / "plain.pdf"))

    assert result.job is None
    assert result.delivery is None
    assert result.prompt is None
    assert (tmp_path / "plain.pdf").is_file()


def test_records_a_job_and_delivers_to_a_folder(tmp_path):
    store = JobStore(tmp_path / "jobs")
    scene = Scene(id="digest", name="群聊总结", prompt="列出待办，负责人缺失就写未指定")
    out = tmp_path / "out"

    result = run_export(
        source(), options(), store=store, scene=scene, target=FolderDelivery(out)
    )

    assert result.job is not None
    assert result.job.directory.parent == store.ready_dir
    assert result.job.state.status is JobStatus.DELIVERED
    assert result.job.state.destination == str(out / "2026-11-15 ECO 项目讨论群")

    manifest = result.job.manifest
    assert manifest.message_count == 8
    assert manifest.scene_id == "digest"
    assert manifest.scene_name == "群聊总结"
    assert manifest.first_message.id == "m001"
    assert manifest.last_message.id == "m008"

    assert result.prompt is not None
    assert "列出待办，负责人缺失就写未指定" in result.prompt
    assert "[m006]" in result.prompt
    assert str(result.job.files_dir) in result.prompt

    delivered = Path(result.delivery.destination)
    assert (delivered / "ECO 项目讨论群.pdf").is_file()
    assert (delivered / "ECO 项目讨论群.md").is_file()
    assert (delivered / "给 Agent 的提示词.txt").is_file()


def test_reported_paths_point_into_the_committed_job(tmp_path):
    store = JobStore(tmp_path / "jobs")
    result = run_export(source(), options(), store=store, scene=Scene(id="s", name="场景"))

    assert result.export.pdf_path.is_relative_to(result.job.files_dir)
    assert result.export.pdf_path.is_file()
    assert not (store.staging_dir / result.job.job_id).exists()


def test_scene_decides_which_companion_files_are_written(tmp_path):
    store = JobStore(tmp_path / "jobs")
    scene = Scene(id="text-only", name="只要文字", markdown=False, json_output=True)

    result = run_export(source(), options(), store=store, scene=scene)

    kinds = {artifact.kind for artifact in result.job.manifest.artifacts}
    assert kinds == {"pdf", "json"}


def test_artifacts_are_hashed_on_disk(tmp_path):
    import hashlib

    store = JobStore(tmp_path / "jobs")
    result = run_export(source(), options(), store=store)

    pdf = result.job.artifact_by_kind("pdf")
    body = result.job.artifact_path(pdf).read_bytes()
    assert pdf.sha256 == hashlib.sha256(body).hexdigest()
    assert pdf.size == len(body)


def test_a_missing_vault_falls_back_to_the_clipboard(tmp_path):
    store = JobStore(tmp_path / "jobs")
    fallback = FakeClipboard()

    result = run_export(
        source(),
        options(),
        store=store,
        scene=Scene(id="s", name="场景"),
        target=FailingTarget(),
        clipboard_fallback=fallback,
    )

    assert result.delivery is not None
    assert result.delivery.status == "copied"
    assert "vault not found" in result.delivery.detail
    assert result.job.state.status is JobStatus.COPIED
    assert fallback.requests and fallback.requests[0].job.job_id == result.job.job_id


def test_total_delivery_failure_marks_the_job_failed(tmp_path):
    store = JobStore(tmp_path / "jobs")

    result = run_export(
        source(),
        options(),
        store=store,
        target=FailingTarget("vault not found"),
        clipboard_fallback=FakeClipboard(fail=True),
    )

    assert result.ok is False
    assert result.delivery.status == "failed"
    assert result.job.state.status is JobStatus.FAILED
    assert "vault not found" in (result.job.state.error or "")
    assert "剪贴板兜底也失败" in (result.job.state.error or "")


def test_export_failure_keeps_the_wreckage_in_failed(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")

    def boom(self, source, options, progress=None):
        raise RuntimeError("renderer died")

    monkeypatch.setattr(ExportService, "export", boom)

    with pytest.raises(RuntimeError, match="renderer died"):
        run_export(source(), options(), store=store)

    failed = list(store.failed_dir.iterdir())
    assert len(failed) == 1
    records = store.list_jobs()
    assert records[0].state.status is JobStatus.FAILED
    assert "renderer died" in (records[0].state.error or "")
    assert not store.ready_dir.exists() or not list(store.ready_dir.iterdir())


def test_empty_selection_is_recorded_with_a_note(tmp_path):
    store = JobStore(tmp_path / "jobs")
    result = run_export(
        source(),
        options(start=datetime(2020, 1, 1), end=datetime(2020, 1, 2)),
        store=store,
        scene=Scene(id="s", name="场景"),
    )

    assert result.job.manifest.message_count == 0
    assert result.job.manifest.first_message is None
    assert "没有消息符合当前筛选条件" in result.job.manifest.notes


def test_mirror_export_puts_every_file_next_to_the_chosen_path(tmp_path):
    store = JobStore(tmp_path / "jobs")
    result = run_export(source(), options(), store=store, scene=Scene(id="s", name="场景"))

    target = tmp_path / "chosen" / "archive.pdf"
    mirrored = mirror_export(result.export, target)

    assert mirrored.pdf_path == target
    assert target.is_file()
    assert target.with_suffix(".md").is_file()
    assert target.with_suffix(".json").is_file()
    assert (target.parent / "archive_assets").is_dir()
    assert mirrored.markdown_path == target.with_suffix(".md")


def test_mirror_export_is_a_no_op_for_a_missing_source(tmp_path):
    store = JobStore(tmp_path / "jobs")
    result = run_export(source(), options(), store=store)

    missing = replace(result.export, pdf_path=tmp_path / "gone.pdf")
    assert mirror_export(missing, tmp_path / "target.pdf") == missing
