from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wechat_context_exporter.delivery import (
    AgentDelivery,
    ClipboardDelivery,
    DeliveryError,
    DeliveryRequest,
    FolderDelivery,
    ObsidianDelivery,
    ordered_artifacts,
)
from wechat_context_exporter.jobs import JobManifest, JobStore, collect_artifacts
from wechat_context_exporter.scenes import Scene


class FakeBackend:
    """Records what would have been pasted; never touches the real clipboard."""

    def __init__(self, *, copy: bool = True, activate: bool = True, paste: bool = True) -> None:
        self.calls: list[tuple] = []
        self._copy = copy
        self._activate = activate
        self._paste = paste

    def copy(self, *, text=None, files=()):
        self.calls.append(("copy", text, tuple(files)))
        return self._copy

    def activate(self, app):
        self.calls.append(("activate", app))
        return self._activate

    def paste(self):
        self.calls.append(("paste",))
        return self._paste


def make_job(tmp_path: Path, *, conversation: str = "生态项目组", names=("eco.pdf", "eco.md", "eco.json")):
    store = JobStore(tmp_path / "jobs")
    manifest = JobManifest(
        job_id="20261115T230000-abc123",
        conversation_id="eco-project",
        conversation_name=conversation,
        created_at=datetime(2026, 11, 15, 23, 0, 0),
        source_kind="json",
        message_count=8,
        start=datetime(2026, 8, 21),
        end=datetime(2026, 8, 22),
    )
    handle = store.begin(manifest)
    for name in names:
        (handle.files_dir / name).write_bytes(f"payload:{name}".encode())
    assets = handle.files_dir / "eco_assets"
    assets.mkdir()
    (assets / "0001_m001.png").write_bytes(b"png")
    return handle.commit(collect_artifacts(handle.files_dir))


def test_folder_delivery_creates_a_dated_per_conversation_folder(tmp_path):
    job = make_job(tmp_path)
    root = tmp_path / "out"
    request = DeliveryRequest(job=job, prompt="总结这个群")

    result = FolderDelivery(root).deliver(request)

    destination = root / "2026-11-15 生态项目组"
    assert result.status == "delivered"
    assert Path(result.destination) == destination
    for name in ("eco.pdf", "eco.md", "eco.json"):
        assert (destination / name).read_bytes() == f"payload:{name}".encode()
    assert (destination / "eco_assets" / "0001_m001.png").is_file()
    assert (destination / "给 Agent 的提示词.txt").read_text(encoding="utf-8") == "总结这个群"


def test_folder_delivery_strips_characters_windows_rejects(tmp_path):
    job = make_job(tmp_path, conversation='项目/组: "A" *?')
    result = FolderDelivery(tmp_path / "out").deliver(DeliveryRequest(job=job))

    name = Path(result.destination).name
    assert not set(name) & set('<>:"/\\|?*')
    assert name.startswith("2026-11-15 ")


def test_obsidian_note_carries_frontmatter_and_relative_links(tmp_path):
    job = make_job(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    scene = Scene(id="decision-review", name="项目决策复盘")

    result = ObsidianDelivery(vault).deliver(
        DeliveryRequest(job=job, scene=scene, prompt="还原决策记录")
    )

    note = vault / "微信记忆" / "2026-11" / "2026-11-15 生态项目组.md"
    assert Path(result.destination) == note
    text = note.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert 'conversation: "生态项目组"' in text
    assert f"job_id: {job.job_id}" in text
    assert "message_count: 8" in text
    assert 'scene: "项目决策复盘"' in text
    assert "window_start: 2026-08-21" in text
    assert "## 交给 Agent 的任务" in text
    assert "还原决策记录" in text

    attachment_dir = vault / "微信记忆" / "_附件" / job.job_id
    assert (attachment_dir / "eco.pdf").is_file()
    assert (attachment_dir / "eco_assets" / "0001_m001.png").is_file()
    assert "[eco.pdf](<../_附件/" in text
    assert f"# 生态项目组 · 2026-08-22" in text


def test_obsidian_requires_an_existing_vault(tmp_path):
    job = make_job(tmp_path)
    with pytest.raises(DeliveryError, match="vault not found"):
        ObsidianDelivery(tmp_path / "missing").deliver(DeliveryRequest(job=job))


def test_clipboard_copies_text_and_files_together(tmp_path):
    job = make_job(tmp_path)
    backend = FakeBackend()

    result = ClipboardDelivery(backend).deliver(
        DeliveryRequest(job=job, prompt="按 [消息ID] 引用")
    )

    assert result.status == "copied"
    assert backend.calls[0][0] == "copy"
    text, files = backend.calls[0][1], backend.calls[0][2]
    assert "按 [消息ID] 引用" in text
    assert [Path(item).name for item in files] == ["eco.pdf", "eco.md", "eco.json"]


def test_clipboard_falls_back_to_a_path_list_without_a_prompt(tmp_path):
    job = make_job(tmp_path)
    backend = FakeBackend()

    ClipboardDelivery(backend).deliver(DeliveryRequest(job=job))

    text = backend.calls[0][1]
    assert "生态项目组" in text
    assert "eco.pdf" in text


def test_clipboard_raises_when_the_backend_refuses(tmp_path):
    job = make_job(tmp_path)
    with pytest.raises(DeliveryError, match="refused"):
        ClipboardDelivery(FakeBackend(copy=False)).deliver(DeliveryRequest(job=job))


def test_agent_delivers_when_window_and_paste_succeed(tmp_path):
    job = make_job(tmp_path)
    backend = FakeBackend()

    result = AgentDelivery("claude", backend=backend).deliver(
        DeliveryRequest(job=job, prompt="列待办")
    )

    assert result.status == "delivered"
    assert result.destination == "claude"
    assert backend.calls == [("copy", "列待办", ()), ("activate", "claude"), ("paste",)]


def test_agent_leaves_the_clipboard_ready_when_the_window_is_missing(tmp_path):
    job = make_job(tmp_path)
    backend = FakeBackend(activate=False)

    result = AgentDelivery("codex", backend=backend).deliver(
        DeliveryRequest(job=job, prompt="列待办")
    )

    assert result.status == "copied"
    assert "Ctrl+V" in result.detail
    assert ("paste",) not in backend.calls


def test_agent_attaches_files_when_path_only_is_disabled(tmp_path):
    job = make_job(tmp_path)
    backend = FakeBackend()

    AgentDelivery("claude", backend=backend, path_only=False).deliver(
        DeliveryRequest(job=job, prompt="列待办")
    )

    assert len(backend.calls[0][2]) == 3


def test_agent_dry_run_never_touches_another_application(tmp_path):
    job = make_job(tmp_path)
    backend = FakeBackend()

    result = AgentDelivery("claude", backend=backend, dry_run=True).deliver(
        DeliveryRequest(job=job, prompt="列待办")
    )

    assert result.status == "copied"
    assert [call[0] for call in backend.calls] == ["copy"]


def test_ordered_artifacts_puts_the_pdf_first(tmp_path):
    job = make_job(tmp_path)
    assert [path.suffix for path in ordered_artifacts(job)] == [".pdf", ".md", ".json"]


def test_copy_artifacts_refuses_a_job_without_files(tmp_path):
    job = make_job(tmp_path, names=())
    with pytest.raises(DeliveryError, match="no artifacts"):
        FolderDelivery(tmp_path / "out").deliver(DeliveryRequest(job=job))
