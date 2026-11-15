"""Scene and delivery controls, shared by both windows.

Both windows already agree on one export pipeline; they only differ in styling.
Putting the new controls in one widget keeps them from drifting apart the way the
two date pickers and two "keep PNG" checkboxes already did.

The widget deliberately owns no export logic: it answers two questions --
"which scene" and "where does it go" -- and returns plain objects
(:class:`Scene`, :class:`DeliveryTarget`) that the worker passes to
``pipeline.run_export``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..delivery import (
    AgentDelivery,
    ClipboardDelivery,
    DeliveryError,
    DeliveryTarget,
    FolderDelivery,
    ObsidianDelivery,
)
from ..paths import output_root
from ..scenes import Scene, SceneStore
from . import neumorphic as nm

TARGET_LABELS: tuple[tuple[str, str], ...] = (
    ("none", "只记录，不投递"),
    ("folder", "投递到文件夹"),
    ("obsidian", "投递到 Obsidian"),
    ("clipboard", "复制到剪贴板"),
    ("agent", "粘贴给 Agent"),
)

# Delivery defaults to the archive root rather than a second copy under
# Documents: one folder the user actually browses, not two.
DEFAULT_FOLDER = output_root()


def resolve_scene_range(
    scene: Scene | None,
    fallback_start: datetime,
    fallback_end: datetime,
) -> tuple[datetime, datetime]:
    """A scene with a window wins over the date pickers; otherwise they win.

    Choosing 「项目决策复盘」 means "the last 30 days" -- that is the whole point
    of a recipe. A scene with no window at all leaves the pickers untouched.
    """
    if scene is None:
        return fallback_start, fallback_end
    if scene.days is None and scene.start is None and scene.end is None:
        return fallback_start, fallback_end
    start, end = scene.window()
    return start or fallback_start, end or fallback_end


class SceneDeliveryBar(QWidget):
    """Two combos, a path field, and an agent field, shown only when relevant."""

    scene_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scenes: dict[str, Scene] = {}
        self._store = SceneStore()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        scene_row = QHBoxLayout()
        scene_row.setSpacing(8)
        self._scene_label = QLabel("场景")
        scene_row.addWidget(self._scene_label)
        self.scene_combo = nm.SoftComboBox()
        self.scene_combo.addItem("不使用场景", "")
        for scene in self._store.list():
            self._scenes[scene.id] = scene
            label = f"{scene.shortcut} · {scene.name}" if scene.shortcut else scene.name
            self.scene_combo.addItem(label, scene.id)
        self.scene_combo.currentIndexChanged.connect(self._on_scene_changed)
        scene_row.addWidget(self.scene_combo, 1)
        layout.addLayout(scene_row)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        self._target_label = QLabel("投递")
        target_row.addWidget(self._target_label)
        self.target_combo = nm.SoftComboBox()
        for value, label in TARGET_LABELS:
            self.target_combo.addItem(label, value)
        self.target_combo.currentIndexChanged.connect(self._refresh_visibility)
        target_row.addWidget(self.target_combo, 1)
        layout.addLayout(target_row)

        self.path_row = QWidget()
        path_layout = QHBoxLayout(self.path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.path_edit = nm.SoftLineEdit()
        self.path_edit.setPlaceholderText("投递目录或 Obsidian vault")
        browse = QPushButton("选择")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(browse)
        layout.addWidget(self.path_row)

        self.agent_row = QWidget()
        agent_layout = QVBoxLayout(self.agent_row)
        agent_layout.setContentsMargins(0, 0, 0, 0)
        agent_layout.setSpacing(4)
        self.agent_edit = nm.SoftLineEdit()
        self.agent_edit.setPlaceholderText("应用名或 exe，例如 claude、codex")
        self.dry_run_check = QCheckBox("只复制，不激活应用")
        agent_layout.addWidget(self.agent_edit)
        agent_layout.addWidget(self.dry_run_check)
        layout.addWidget(self.agent_row)

        for warning in self._store.last_warnings:
            self.scene_combo.setToolTip(warning)

        self._refresh_visibility()

    # -- public ----------------------------------------------------------

    def selected_scene(self) -> Scene | None:
        scene_id = self.scene_combo.currentData()
        return self._scenes.get(scene_id) if scene_id else None

    def target_name(self) -> str:
        return str(self.target_combo.currentData() or "none")

    def build_target(self) -> DeliveryTarget | None:
        """Construct the target, or explain what is missing before the export runs."""
        name = self.target_name()
        if name == "none":
            return None
        if name == "clipboard":
            return ClipboardDelivery()
        if name == "folder":
            path = self._required_path("请先选择投递目录")
            return FolderDelivery(path)
        if name == "obsidian":
            path = self._required_path("请先选择 Obsidian vault")
            if not Path(path).is_dir():
                raise DeliveryError(f"Obsidian vault 路径不存在：{path}")
            return ObsidianDelivery(path)
        if name == "agent":
            agent = self.agent_edit.text().strip()
            if not agent:
                raise DeliveryError("请填写要粘贴的 Agent 应用名，例如 claude")
            return AgentDelivery(agent, dry_run=self.dry_run_check.isChecked())
        raise DeliveryError(f"未知的投递方式：{name}")

    def set_busy(self, busy: bool) -> None:
        self.setEnabled(not busy)

    def apply_styles(self, *, fields: str = "", combos: str = "", labels: str = "") -> None:
        """Let the owning window impose its theme.

        The glass dashboard is dark-on-glass and the legacy window is light; a
        widget that hard-coded either palette would be wrong in the other one.
        """
        if fields:
            for editor in (self.path_edit, self.agent_edit):
                editor.setStyleSheet(fields)
        if combos:
            for combo in (self.scene_combo, self.target_combo):
                combo.setStyleSheet(combos)
        if labels:
            for label in (self._scene_label, self._target_label):
                label.setStyleSheet(labels)

    # -- internals -------------------------------------------------------

    def _required_path(self, message: str) -> str:
        path = self.path_edit.text().strip()
        if not path:
            raise DeliveryError(message)
        return path

    def _on_scene_changed(self) -> None:
        scene = self.selected_scene()
        if scene is not None and scene.target != "none":
            index = self.target_combo.findData(scene.target)
            if index >= 0:
                self.target_combo.setCurrentIndex(index)
        self._refresh_visibility()
        self.scene_changed.emit(scene)

    def _refresh_visibility(self) -> None:
        name = self.target_name()
        self.path_row.setVisible(name in {"folder", "obsidian"})
        self.agent_row.setVisible(name == "agent")
        if name == "folder" and not self.path_edit.text().strip():
            self.path_edit.setText(str(DEFAULT_FOLDER))
        if name == "obsidian":
            self.path_edit.setPlaceholderText("Obsidian vault 根目录")
        elif name == "folder":
            self.path_edit.setPlaceholderText("投递目录")

    def _browse(self) -> None:
        current = self.path_edit.text().strip()
        start = current if current and Path(current).is_dir() else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "选择投递目录", start)
        if chosen:
            self.path_edit.setText(chosen)
