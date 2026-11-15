from __future__ import annotations

import json
from datetime import datetime

import pytest

from wechat_context_exporter.jobs import JobManifest
from wechat_context_exporter.scenes import (
    BUILTIN_SCENES,
    CITATION_RULE,
    Scene,
    SceneError,
    SceneStore,
    default_scene_path,
    render_prompt,
)


def make_manifest(**overrides) -> JobManifest:
    payload = {
        "job_id": "20261115T230000-abc123",
        "conversation_id": "eco-project",
        "conversation_name": "生态项目组",
        "created_at": datetime(2026, 11, 15, 23, 0, 0),
        "source_kind": "json",
        "message_count": 8,
        "start": datetime(2026, 8, 21),
        "end": datetime(2026, 8, 22),
    }
    payload.update(overrides)
    return JobManifest(**payload)


def test_builtin_scenes_are_well_formed():
    ids = [scene.id for scene in BUILTIN_SCENES]
    assert len(ids) == len(set(ids))
    assert [scene.shortcut for scene in BUILTIN_SCENES] == [1, 2, 3, 4]
    for scene in BUILTIN_SCENES:
        assert scene.builtin
        assert scene.prompt.strip()
        assert scene.target in {"folder", "obsidian", "clipboard", "agent", "none"}


def test_window_uses_days_relative_to_now():
    scene = Scene(id="recent", name="最近一周", days=7)
    start, end = scene.window(datetime(2026, 11, 15, 23, 7, 55, 123456))

    assert start == datetime(2026, 11, 8, 23, 7, 55)
    assert end == datetime(2026, 11, 15, 23, 7, 55, 123456)


def test_explicit_window_wins_over_days():
    scene = Scene(
        id="pinned",
        name="固定窗口",
        days=30,
        start=datetime(2026, 8, 1),
        end=datetime(2026, 8, 31),
    )
    assert scene.window(datetime(2026, 11, 15)) == (
        datetime(2026, 8, 1),
        datetime(2026, 8, 31),
    )


def test_scene_without_window_selects_everything():
    assert Scene(id="all", name="全部").window() == (None, None)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "Bad Id", "name": "x"},
        {"id": "ok", "name": " "},
        {"id": "ok", "name": "x", "days": 0},
        {"id": "ok", "name": "x", "target": "email"},
        {"id": "ok", "name": "x", "shortcut": 10},
        {"id": "ok", "name": "x", "start": datetime(2026, 9, 1), "end": datetime(2026, 8, 1)},
    ],
)
def test_invalid_scenes_are_rejected(kwargs):
    with pytest.raises(SceneError):
        Scene(**kwargs)


def test_scene_roundtrip_through_dict():
    scene = Scene(
        id="my-digest",
        name="我的总结",
        description="自定义",
        days=3,
        query="上线",
        markdown=False,
        target="agent",
        prompt="只列风险",
        shortcut=7,
    )
    assert Scene.from_dict(scene.to_dict()) == scene


def test_store_lists_builtins_then_user_scenes(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    store.save(Scene(id="mine", name="我的场景", target="folder"))

    listed = store.list()
    assert [scene.id for scene in listed[: len(BUILTIN_SCENES)]] == [
        scene.id for scene in BUILTIN_SCENES
    ]
    assert listed[-1].id == "mine"
    assert store.last_warnings == []


def test_user_scene_overrides_builtin_and_delete_restores_it(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    store.save(Scene(id="group-digest", name="我的群聊总结", days=3))

    overridden = store.get("group-digest")
    assert overridden.name == "我的群聊总结"
    assert overridden.days == 3
    assert not overridden.builtin

    assert store.delete("group-digest") is True
    restored = store.get("group-digest")
    assert restored.name == "群聊总结"
    assert restored.builtin
    assert store.delete("group-digest") is False


def test_corrupt_scene_file_falls_back_to_builtins(tmp_path):
    path = tmp_path / "scenes.json"
    path.write_text("{ this is not json", encoding="utf-8")

    store = SceneStore(path)
    assert [scene.id for scene in store.list()] == [scene.id for scene in BUILTIN_SCENES]
    assert store.last_warnings and "unreadable" in store.last_warnings[0]


def test_malformed_entries_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "scenes.json"
    path.write_text(
        json.dumps({"scenes": [{"id": "good", "name": "好的"}, {"id": "BAD ID", "name": "坏"}]}),
        encoding="utf-8",
    )

    store = SceneStore(path)
    assert store.get("good").name == "好的"
    assert any("BAD ID" in warning or "scene id" in warning for warning in store.last_warnings)


def test_unknown_scene_error_lists_available_ids(tmp_path):
    store = SceneStore(tmp_path / "scenes.json")
    with pytest.raises(SceneError) as excinfo:
        store.get("nope")
    assert "group-digest" in str(excinfo.value)


def test_render_prompt_carries_scope_and_citation_rule(tmp_path):
    scene = Scene(id="digest", name="群聊总结", prompt="列出待办，负责人缺失就写未指定")
    manifest = make_manifest()
    archive = tmp_path / "eco.pdf"

    text = render_prompt(scene, manifest, [archive])

    assert f"【归档】{archive}" in text
    assert "【会话】生态项目组（eco-project）" in text
    assert "2026-08-21 ~ 2026-08-22" in text
    assert "【消息数】8" in text
    assert manifest.job_id in text
    assert "列出待办，负责人缺失就写未指定" in text
    assert CITATION_RULE in text


def test_render_prompt_substitutes_known_placeholders(tmp_path):
    scene = Scene(id="digest", name="群聊总结", prompt="{conversation} 在 {start} 之后发生了什么？")
    text = render_prompt(scene, make_manifest(), [tmp_path / "eco.md"])
    assert "生态项目组 在 2026-08-21 之后发生了什么？" in text


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("关注 {weather} 的影响", "关注 {weather} 的影响"),
        ("进度 5% { 未闭合", "进度 5% { 未闭合"),
    ],
)
def test_render_prompt_survives_odd_placeholders(tmp_path, prompt, expected):
    scene = Scene(id="odd", name="怪模板", prompt=prompt)
    text = render_prompt(scene, make_manifest(), [tmp_path / "eco.md"])
    assert expected in text


def test_render_prompt_without_files_says_so(tmp_path):
    text = render_prompt(Scene(id="odd", name="怪模板"), make_manifest())
    assert "（无归档文件" in text


def test_default_scene_path_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.delenv("WECHAT_AI_MEMORY_SCENES_FILE", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_scene_path() == tmp_path / "WeChatAIMemory" / "scenes.json"


def test_scene_path_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("WECHAT_AI_MEMORY_SCENES_FILE", str(tmp_path / "portable.json"))
    assert default_scene_path() == tmp_path / "portable.json"
