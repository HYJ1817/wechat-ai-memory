from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest

from wechat_context_exporter.jobs import (
    JobArtifact,
    JobError,
    JobManifest,
    JobState,
    JobStatus,
    JobStore,
    MessageRef,
    collect_artifacts,
    default_jobs_dir,
    utc_now,
)


def make_manifest(job_id: str = "20261115T230000-abc123", **overrides) -> JobManifest:
    payload = {
        "job_id": job_id,
        "conversation_id": "eco-project",
        "conversation_name": "生态项目组",
        "created_at": datetime(2026, 11, 15, 23, 0, 0),
        "source_kind": "json",
        "source_label": "examples/demo_chat.json",
        "message_count": 8,
        "start": datetime(2026, 8, 21),
        "end": datetime(2026, 8, 22),
    }
    payload.update(overrides)
    return JobManifest(**payload)


def read_state(directory) -> JobState:
    return JobState.from_dict(json.loads((directory / "state.json").read_text(encoding="utf-8")))


def test_manifest_roundtrip_preserves_nested_fields():
    manifest = make_manifest(
        scene_id="group-digest",
        scene_name="群聊总结",
        query="随机种子",
        wechat_version="4.1.13",
        artifacts=(JobArtifact("eco.pdf", "pdf", 1024, "a" * 64),),
        notes=("语音 2 条未转写",),
        first_message=MessageRef("m001", datetime(2026, 8, 21, 9, 0), "林工", "早上好"),
        last_message=MessageRef("m008", datetime(2026, 8, 21, 18, 30), "周工", "明天继续"),
    )

    assert JobManifest.from_json(manifest.to_json()) == manifest


def test_manifest_rejects_inverted_window():
    with pytest.raises(JobError):
        make_manifest(start=datetime(2026, 8, 22), end=datetime(2026, 8, 21))


def test_artifact_name_cannot_escape_the_job_directory():
    for name in ("../escape.pdf", "sub/dir.pdf", "", "."):
        with pytest.raises(JobError):
            JobArtifact(name=name, kind="pdf", size=1, sha256="0" * 64)


def test_commit_is_the_only_way_into_ready(tmp_path):
    store = JobStore(tmp_path / "jobs")
    manifest = make_manifest()
    payload = b"%PDF-1.4 fake body"

    handle = store.begin(manifest)
    assert store.list_jobs() == []
    assert not (store.ready_dir / manifest.job_id).exists()

    (handle.files_dir / "eco.pdf").write_bytes(payload)
    (handle.files_dir / "eco_assets").mkdir()
    artifacts = collect_artifacts(handle.files_dir)
    record = handle.commit(artifacts)

    assert record.state.status is JobStatus.READY
    assert (store.ready_dir / manifest.job_id / "files" / "eco.pdf").read_bytes() == payload
    assert not (store.staging_dir / manifest.job_id).exists()

    on_disk = JobManifest.from_json(
        (record.directory / "manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk.artifacts == tuple(artifacts)
    assert on_disk.artifacts[0].sha256 == hashlib.sha256(payload).hexdigest()
    assert [artifact.kind for artifact in on_disk.artifacts] == ["pdf"]


def test_context_manager_moves_a_crashed_job_to_failed(tmp_path):
    store = JobStore(tmp_path / "jobs")
    manifest = make_manifest()

    with pytest.raises(RuntimeError):
        with store.begin(manifest) as handle:
            (handle.files_dir / "partial.pdf").write_bytes(b"half a page")
            raise RuntimeError("renderer died")

    failed = store.failed_dir / manifest.job_id
    assert (failed / "files" / "partial.pdf").read_bytes() == b"half a page"
    state = read_state(failed)
    assert state.status is JobStatus.FAILED
    assert "renderer died" in (state.error or "")
    assert not (store.staging_dir / manifest.job_id).exists()


def test_set_state_counts_delivery_attempts(tmp_path):
    store = JobStore(tmp_path / "jobs")
    record = store.begin(make_manifest()).commit([])
    assert record.state.attempts == 0

    record = store.set_state(
        record,
        JobStatus.DELIVERED,
        target="folder",
        destination=str(tmp_path / "out"),
    )
    assert record.state.attempts == 1
    assert record.state.destination == str(tmp_path / "out")

    record = store.set_state(record, JobStatus.FAILED, error="target folder is gone")
    assert record.state.attempts == 2
    assert record.state.error == "target folder is gone"
    assert read_state(record.directory).status is JobStatus.FAILED


def test_list_jobs_sorts_newest_first_and_skips_broken_directories(tmp_path):
    store = JobStore(tmp_path / "jobs")
    store.begin(make_manifest("20261115T220000-aaaaaa")).commit([])
    store.begin(make_manifest("20261115T230000-bbbbbb")).commit([])

    broken = store.ready_dir / "20261115T210000-cccccc"
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{not json at all", encoding="utf-8")

    assert [record.job_id for record in store.list_jobs()] == [
        "20261115T230000-bbbbbb",
        "20261115T220000-aaaaaa",
    ]
    assert store.last_warnings
    assert "20261115T210000-cccccc" in store.last_warnings[0]


def test_prune_keeps_jobs_that_were_never_delivered(tmp_path):
    store = JobStore(tmp_path / "jobs")
    delivered = store.begin(make_manifest("20261115T220000-aaaaaa")).commit([])
    store.set_state(
        delivered,
        JobStatus.DELIVERED,
        target="folder",
        destination=str(tmp_path / "out"),
    )
    undelivered = store.begin(make_manifest("20261115T230000-bbbbbb")).commit([])

    future = utc_now() + timedelta(days=90)
    assert store.prune(30, now=future) == ["20261115T220000-aaaaaa"]
    assert not (store.ready_dir / "20261115T220000-aaaaaa").exists()
    assert (store.ready_dir / undelivered.job_id).exists()

    assert store.prune(30, now=future, keep_unfinished=False) == ["20261115T230000-bbbbbb"]


def test_recover_stale_preserves_interrupted_artifacts(tmp_path):
    store = JobStore(tmp_path / "jobs")
    manifest = make_manifest()
    handle = store.begin(manifest)
    (handle.files_dir / "partial.pdf").write_bytes(b"half a page")

    assert store.recover_stale() == [manifest.job_id]
    assert (store.failed_dir / manifest.job_id / "files" / "partial.pdf").is_file()
    state = read_state(store.failed_dir / manifest.job_id)
    assert state.status is JobStatus.FAILED
    assert "interrupted" in (state.error or "")
    assert store.list_jobs()[0].state.status is JobStatus.FAILED


def test_jobs_dir_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("WECHAT_AI_MEMORY_JOBS_DIR", str(tmp_path / "portable"))
    assert default_jobs_dir() == tmp_path / "portable"
