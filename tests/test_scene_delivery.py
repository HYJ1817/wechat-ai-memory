from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from wechat_context_exporter.delivery import (
    AgentDelivery,
    ClipboardDelivery,
    DeliveryError,
    FolderDelivery,
    ObsidianDelivery,
)
from wechat_context_exporter.scenes import BUILTIN_SCENES, Scene
from wechat_context_exporter.ui.scene_delivery import (
    DEFAULT_FOLDER,
    SceneDeliveryBar,
    resolve_scene_range,
)


@pytest.fixture
def bar():
    QApplication.instance() or QApplication([])
    widget = SceneDeliveryBar()
    yield widget
    widget.deleteLater()


def select_scene(bar: SceneDeliveryBar, scene_id: str) -> Scene:
    index = bar.scene_combo.findData(scene_id)
    assert index >= 0, f"{scene_id} missing from the combo"
    bar.scene_combo.setCurrentIndex(index)
    scene = bar.selected_scene()
    assert scene is not None
    return scene


def test_bar_lists_no_scene_plus_every_builtin(bar):
    ids = [bar.scene_combo.itemData(index) for index in range(bar.scene_combo.count())]
    assert ids[0] == ""
    assert ids[1:] == [scene.id for scene in BUILTIN_SCENES]
    assert bar.selected_scene() is None


def test_choosing_a_scene_presets_its_delivery_target(bar):
    select_scene(bar, "decision-review")
    assert bar.target_name() == "obsidian"
    assert bar.path_row.isVisibleTo(bar)
    assert not bar.agent_row.isVisibleTo(bar)

    select_scene(bar, "group-digest")
    assert bar.target_name() == "folder"
    assert bar.path_edit.text() == str(DEFAULT_FOLDER)


def test_target_switches_which_fields_are_shown(bar):
    bar.target_combo.setCurrentIndex(bar.target_combo.findData("clipboard"))
    assert not bar.path_row.isVisibleTo(bar)
    assert not bar.agent_row.isVisibleTo(bar)
    assert isinstance(bar.build_target(), ClipboardDelivery)

    bar.target_combo.setCurrentIndex(bar.target_combo.findData("agent"))
    assert bar.agent_row.isVisibleTo(bar)
    assert not bar.path_row.isVisibleTo(bar)


def test_folder_target_needs_no_typed_path(bar):
    bar.target_combo.setCurrentIndex(bar.target_combo.findData("folder"))
    target = bar.build_target()
    assert isinstance(target, FolderDelivery)
    assert str(target.root) == str(DEFAULT_FOLDER)


def test_obsidian_target_requires_an_existing_vault(bar, tmp_path):
    bar.target_combo.setCurrentIndex(bar.target_combo.findData("obsidian"))
    with pytest.raises(DeliveryError, match="请先选择 Obsidian vault"):
        bar.build_target()

    bar.path_edit.setText(str(tmp_path / "missing"))
    with pytest.raises(DeliveryError, match="不存在"):
        bar.build_target()

    bar.path_edit.setText(str(tmp_path))
    assert isinstance(bar.build_target(), ObsidianDelivery)


def test_agent_target_requires_an_application(bar):
    bar.target_combo.setCurrentIndex(bar.target_combo.findData("agent"))
    with pytest.raises(DeliveryError, match="Agent 应用名"):
        bar.build_target()

    bar.agent_edit.setText("claude")
    target = bar.build_target()
    assert isinstance(target, AgentDelivery)
    assert target.app == "claude"
    assert target.dry_run is False


def test_no_delivery_returns_none(bar):
    assert bar.build_target() is None


def test_scene_window_overrides_the_pickers():
    scene = Scene(id="recent", name="最近七天", days=7)
    start, end = resolve_scene_range(
        scene, datetime(2026, 8, 1, 0, 0), datetime(2026, 8, 31, 23, 59)
    )
    assert end > start
    assert (end - start).days == 7


def test_scene_without_a_window_keeps_the_pickers():
    scene = Scene(id="plain", name="无窗口", prompt="只是提示词")
    fallback = (datetime(2026, 8, 1), datetime(2026, 8, 31))
    assert resolve_scene_range(scene, *fallback) == fallback
    assert resolve_scene_range(None, *fallback) == fallback
