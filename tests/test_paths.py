from __future__ import annotations

import os
from pathlib import Path

from wechat_context_exporter import paths


def test_default_root_is_the_archive_folder(monkeypatch):
    monkeypatch.delenv(paths.OUTPUT_DIR_ENV, raising=False)
    root = paths.default_output_root()

    if os.name == "nt":
        assert root == Path("C:/微信记忆")
    else:
        assert root == Path.home() / "微信记忆"


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.OUTPUT_DIR_ENV, str(tmp_path / "elsewhere"))
    assert paths.output_root() == tmp_path / "elsewhere"


def test_default_export_path_creates_the_folder(monkeypatch, tmp_path):
    target = tmp_path / "archive"
    monkeypatch.setenv(paths.OUTPUT_DIR_ENV, str(target))

    path = paths.default_export_path("会话_memory")

    assert path == target / "会话_memory.pdf"
    assert target.is_dir()


def test_suffix_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.OUTPUT_DIR_ENV, str(tmp_path))
    assert paths.default_export_path("x", ".md").suffix == ".md"


def test_unwritable_root_does_not_raise(monkeypatch, tmp_path):
    """A missing drive must fail at the write, not while suggesting a path."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv(paths.OUTPUT_DIR_ENV, str(blocker / "child"))

    assert paths.output_root(create=True) == blocker / "child"
