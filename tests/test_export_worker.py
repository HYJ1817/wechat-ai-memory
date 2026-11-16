from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from wechat_context_exporter.delivery import FolderDelivery
from wechat_context_exporter.jobs import JobStatus, JobStore
from wechat_context_exporter.scenes import Scene
from wechat_context_exporter.service import ExportOptions
from wechat_context_exporter.sources import JsonChatSource
from wechat_context_exporter.ui.main_window import ExportWorker

SOURCE = "examples/demo_chat.json"


def make_options(**overrides) -> ExportOptions:
    payload = {
        "conversation_id": "eco-project",
        "output_pdf": Path("unused.pdf"),
        "start": datetime(2026, 8, 1),
        "end": datetime(2026, 8, 31),
    }
    payload.update(overrides)
    return ExportOptions(**payload)


def run_worker(worker: ExportWorker) -> tuple[list, list]:
    QApplication.instance() or QApplication([])
    completed: list = []
    failed: list = []
    worker.completed.connect(completed.append)
    worker.failed.connect(failed.append)
    worker.run()
    return completed, failed


def test_worker_records_the_job_and_returns_the_export_result(tmp_path):
    store = JobStore(tmp_path / "jobs")
    worker = ExportWorker(
        JsonChatSource(SOURCE),
        make_options(),
        store=store,
        scene=Scene(id="digest", name="群聊总结", prompt="列出待办"),
    )

    completed, failed = run_worker(worker)

    assert failed == []
    assert len(completed) == 1
    assert completed[0].message_count == 8
    assert worker.run_result is not None
    assert worker.run_result.job.state.status is JobStatus.READY
    assert (worker.run_result.job.directory / "manifest.json").is_file()
    assert worker.run_result.prompt is not None
    assert "列出待办" in worker.run_result.prompt


def test_worker_delivers_to_the_chosen_target(tmp_path):
    out = tmp_path / "out"
    worker = ExportWorker(
        JsonChatSource(SOURCE),
        make_options(),
        store=JobStore(tmp_path / "jobs"),
        target=FolderDelivery(out),
    )

    _, failed = run_worker(worker)

    assert failed == []
    assert worker.run_result.delivery is not None
    assert worker.run_result.job.state.status is JobStatus.DELIVERED
    delivered = next(out.iterdir())
    assert delivered.name.endswith("ECO 项目讨论群")
    assert (delivered / "ECO 项目讨论群.pdf").is_file()


def test_worker_reports_an_invalid_range_without_creating_a_job(tmp_path):
    store = JobStore(tmp_path / "jobs")
    worker = ExportWorker(
        JsonChatSource(SOURCE),
        make_options(start=datetime(2026, 9, 1), end=datetime(2026, 8, 1)),
        store=store,
    )

    completed, failed = run_worker(worker)

    assert completed == []
    assert failed and "cannot be after" in failed[0]
    assert store.list_jobs() == []
