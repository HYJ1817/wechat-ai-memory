"""Modern Glassmorphism Dashboard Window for WeChat AI Memory.

Full card-based UI matching the smart-home aesthetic:
- True frosted glass panels via pre-blurred backdrop slice sampling
- Circular storage arc gauge
- Smooth pill toggle switches
- Chat bubble stream replacing raw QTableWidget
- Seamless integration with WeChat4LocalSource and JsonChatSource
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, time
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageFilter
from PySide6.QtCore import (
    QDate,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..delivery import DeliveryError
from ..jobs import JobStore, default_jobs_dir
from ..models import Message, MessageType
from ..paths import default_export_path
from ..pipeline import mirror_export
from ..scenes import Scene
from ..service import ExportOptions, ExportResult
from ..sources import (
    ChatSource,
    JsonChatSource,
    WeChat4LocalSource,
    discover_wechat4_accounts,
)
from ..sources.wechat4_crypto import extract_image_key
from ..voice import VoiceTranscriber
from . import native_theme
from . import fluent as nm
from .glass_widgets import (
    AvatarBadge,
    ChatBubbleStream,
    ChatDateDivider,
    ChatMessageCard,
    ChatSystemMessage,
    ConversationItemWidget,
    GlassCard,
    PillButton,
    SoftPanel,
    StorageGauge,
    ToggleSwitch,
    WindowControlButton,
)
from .main_window import (
    ConversationSearchDialog,
    ExportWorker,
    ImageKeyWorker,
    MessageLoadWorker,
    SourceLoadWorker,
    VoiceTranscriptionWorker,
    application_icon,
    asset_icon,
)
from .scene_delivery import SceneDeliveryBar, resolve_scene_range

BLUR_RADIUS = 32

# --- backdrop rebuild strategy ----------------------------------------------
# The previous implementation ran a full rebuild on EVERY resize event:
# measured at 38.8 ms (1280x880) and 61.4 ms (1920x1080) on this machine.
# That was tolerable only while the frameless window could not be resized by
# hand; with edge resizing enabled it makes every drag step stutter.
#
# Now a resize event only rescales the existing pixmaps -- measured 2.7 / 3.4 ms,
# i.e. 14-18x cheaper -- so glass panels always have a correctly sized backdrop
# and never render blank mid-drag.  The accurate rebuild is deferred until the
# size settles, and is itself somewhat cheaper (28.8 / 37.2 ms) because the blur
# runs at 1/4 resolution: a radius-32 blur destroys far more detail than the
# quarter-resolution grid can carry, so the result is visually indistinguishable
# (verified: 0.084/255 mean per-channel difference against the old output).
BACKDROP_SETTLE_MS = 120
BLUR_DOWNSCALE = 4

# --- frameless window edge resizing -----------------------------------------
# The window is created with Qt.FramelessWindowHint and on Windows carries no
# WS_THICKFRAME (verified on this machine: GWL_STYLE == 0x86000000, i.e. plain
# WS_POPUP).  Without that style, returning HTLEFT/HTBOTTOM from WM_NCHITTEST
# does not actually resize the window, so resizing is implemented in Qt's own
# mouse handling instead.  Side benefit: it is testable offscreen.
RESIZE_MARGIN = 7

RESIZE_LEFT = 1
RESIZE_RIGHT = 2
RESIZE_TOP = 4
RESIZE_BOTTOM = 8

_RESIZE_CURSORS = {
    RESIZE_LEFT: Qt.CursorShape.SizeHorCursor,
    RESIZE_RIGHT: Qt.CursorShape.SizeHorCursor,
    RESIZE_TOP: Qt.CursorShape.SizeVerCursor,
    RESIZE_BOTTOM: Qt.CursorShape.SizeVerCursor,
    RESIZE_LEFT | RESIZE_TOP: Qt.CursorShape.SizeFDiagCursor,
    RESIZE_RIGHT | RESIZE_BOTTOM: Qt.CursorShape.SizeFDiagCursor,
    RESIZE_RIGHT | RESIZE_TOP: Qt.CursorShape.SizeBDiagCursor,
    RESIZE_LEFT | RESIZE_BOTTOM: Qt.CursorShape.SizeBDiagCursor,
}

TITLE_BAR_HEIGHT = 65


class GlassDashboardWindow(QMainWindow):
    """The modern glassmorphism dashboard main window."""

    def __init__(self, demo_json: str | None = None) -> None:
        super().__init__()

        # Deliberately the same store the classic window uses (see
        # main_window.py) -- a second config store would drift apart.
        # Known keys: "{mode}SourcePath" (wechat/json) and "outputPath".
        self._settings = QSettings("LocalTools", "WeChatContextExporter")

        self.setWindowTitle("微信 AI 记忆库 (Modern Dashboard)")
        self.setWindowIcon(application_icon())
        self.resize(1340, 890)
        self.setMinimumSize(1180, 780)

        # Geometry is stored as explicit size/position rather than the opaque
        # saveGeometry() blob.  Two reasons: the values stay readable in the
        # settings store, and -- unlike restoreGeometry() -- they are actually
        # verifiable under the offscreen platform, where restoreGeometry()
        # returns True but silently clamps the window to its minimum size.
        saved_size = self._settings.value("dashboardSize")
        if isinstance(saved_size, QSize) and saved_size.isValid():
            self.resize(saved_size)

        saved_position = self._settings.value("dashboardPos")
        if isinstance(saved_position, QPoint) and self._position_is_visible(saved_position):
            self.move(saved_position)

        # Window chrome belongs to the operating system.  Letting Windows draw
        # the title bar also buys Snap, the system menu, Win+arrow and correct
        # multi-monitor behaviour -- all of which the previous frameless window
        # either faked or went without.
        self._drag_pos: QPoint | None = None

        self._source: ChatSource | None = None
        self._current_cid: str | None = None
        self._all_conversations: list = []
        self._conv_widgets: dict[str, ConversationItemWidget] = {}
        self._messages: list[Message] = []
        self._filtered_messages: list[Message] = []
        self._active_worker: QThread | None = None
        self._export_output: Path | None = None

        # Build UI layout
        self._init_ui()

        # If demo_json is passed, load it immediately
        if demo_json and os.path.isfile(demo_json):
            self._load_json_path(demo_json)
        else:
            # Auto-discover accounts
            QTimer.singleShot(100, self._auto_discover)

    # -- frameless window interaction --------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        """Flat themed window background.

        No photo backdrop, no blur, no glow, no rim light -- the OS draws the
        frame now, so the client area is just the window colour.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(), native_theme.active().color("window"))

    # --------------------------------------------------------------------------
    # UI Layout Construction
    # --------------------------------------------------------------------------
    def _init_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(28, 16, 28, 20)
        root_layout.setSpacing(14)

        # ---- 1. Top Bar ----
        top_bar = self._build_top_bar()
        root_layout.addLayout(top_bar)

        # ---- 2. Main Workspace: one settings rail, one preview ----
        # Three columns split the inputs across the outer two and squeezed the
        # middle; the classic window kept every input in a single scannable column
        # and gave the rest of the width to the content. Same idea here.
        workspace = QHBoxLayout()
        workspace.setSpacing(20)

        self.settings_card = self._build_settings_card()
        self.left_card = self.settings_card  # kept for existing callers
        workspace.addWidget(self.settings_card, stretch=0)

        self.center_card = self._build_chat_card()
        workspace.addWidget(self.center_card, stretch=1)

        root_layout.addLayout(workspace, stretch=1)

        # ---- 3. Status Bar ----
        # Always present (not only during work): a persistent status line with
        # progress, remaining time and the connection summary is what makes a
        # long export legible instead of looking frozen.
        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(
            native_theme.themed_qss("color: rgba(255, 255, 255, 175); font-size: 11px;")
        )
        status_row.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: %s; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: %s; border-radius: 2px; }"
            % (native_theme.ink_rgba(35), native_theme.accent_rgba(255))
        )
        status_row.addWidget(self.progress_bar, stretch=1)

        # Media retention lives with the other run-level status: it used to sit in
        # the settings rail, where it cost the export controls 35px of height.
        self.lbl_media_lost = QLabel("")
        self.lbl_media_lost.setStyleSheet("color: #B4560E; font-size: 11px;")
        self.lbl_media_lost.setToolTip("本地媒体留存")
        status_row.addWidget(self.lbl_media_lost)

        self.media_bar = QProgressBar()
        self.media_bar.setTextVisible(False)
        self.media_bar.setFixedSize(90, 4)
        self.media_bar.setRange(0, 100)
        self.media_bar.setValue(100)
        self.media_bar.setToolTip("本地媒体留存")
        self.media_bar.setStyleSheet(
            "QProgressBar { background: %s; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background: %s; border-radius: 2px; }"
            % (native_theme.ink_rgba(40), native_theme.accent_rgba(255))
        )
        status_row.addWidget(self.media_bar)

        self.status_detail = QLabel("本地处理 · 数据不出机")
        self.status_detail.setStyleSheet(
            native_theme.themed_qss("color: rgba(255, 255, 255, 175); font-size: 11px;")
        )
        status_row.addWidget(self.status_detail)

        root_layout.addLayout(status_row)

    def _set_status(self, text: str) -> None:
        """Update the top-bar pill and the bottom status line together."""
        self.status_pill.setText(text)
        self.status_label.setText(text.lstrip("● ").strip() or "就绪")

    def _set_status_detail(self, text: str) -> None:
        self.status_detail.setText(text)

    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(14)

        # App Logo & Title
        title_box = QHBoxLayout()
        title_box.setSpacing(10)
        title_lbl = QLabel("微信 AI 记忆库", self)
        title_lbl.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 245); font-size: 19px; font-weight: bold;"))
        version_lbl = QLabel("v0.3.8-alpha.1", self)
        version_lbl.setStyleSheet(native_theme.themed_qss("color: rgba(255, 210, 160, 160); font-size: 11px; margin-top: 5px;"))
        title_box.addWidget(title_lbl)
        title_box.addWidget(version_lbl)
        bar.addLayout(title_box)

        bar.addStretch(1)

        # Segmented Filter Pills in the middle
        self.pill_all = PillButton("全部消息", self, active=True)
        self.pill_img = PillButton("带图片", self, active=False)
        self.pill_voice = PillButton("带语音", self, active=False)
        self.pill_all.clicked.connect(lambda: self._set_type_filter(None))
        self.pill_img.clicked.connect(lambda: self._set_type_filter("image"))
        self.pill_voice.clicked.connect(lambda: self._set_type_filter("voice"))

        bar.addWidget(self.pill_all)
        bar.addWidget(self.pill_img)
        bar.addWidget(self.pill_voice)

        bar.addStretch(1)

        # Privacy Badge
        privacy_pill = PillButton("本地处理 · 数据不出机", self, active=False)
        privacy_pill.setEnabled(False)
        bar.addWidget(privacy_pill)

        # Status Pill Badge
        self.status_pill = PillButton("● 未连接", self, active=False)
        self.status_pill.setStyleSheet(native_theme.themed_qss("color: rgba(255, 200, 190, 220);"))
        bar.addWidget(self.status_pill)

        # No custom min/max/close buttons: the system title bar provides them,
        # along with Snap, the system menu and Win+arrow.
        return bar

    def _section_header(self, text: str, number: str) -> QWidget:
        """Numbered section heading, the way the classic sidebar labels its groups."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        index = QLabel(number)
        index.setStyleSheet(f"color: {nm.BLURPLE.name()}; font-size: 10px; font-weight: bold;")
        title = QLabel(text)
        title.setStyleSheet(
            native_theme.themed_qss("color: rgba(255, 255, 255, 205); font-size: 12px; font-weight: bold;")
        )
        row.addWidget(index)
        row.addWidget(title)
        row.addStretch(1)
        return widget

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            native_theme.themed_qss("color: rgba(255, 255, 255, 140); font-size: 11px;")
        )
        return label

    def _transparent_scroll(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        """A frameless, transparent scroll area that does not paint over the card."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        area.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        area.viewport().setAutoFillBackground(False)
        area.setStyleSheet(native_theme.themed_qss("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical {
                border: none;
                background: rgba(255, 255, 255, 16);
                width: 6px;
                margin: 0px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 95);
                min-height: 20px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 175, 95, 160);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """))
        area.viewport().setStyleSheet(
            native_theme.themed_qss("background: transparent; background-color: transparent;")
        )

        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        container.setAutoFillBackground(False)
        container.setStyleSheet(
            native_theme.themed_qss("background: transparent; background-color: transparent;")
        )
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 4, 0)
        inner.setSpacing(0)
        area.setWidget(container)
        return area, container, inner

    def _build_settings_card(self) -> GlassCard:
        """Every input in one rail: 01 数据源 → 02 记忆范围 → 03 归档设置.

        The classic window put all of its inputs in a single column and gave the
        rest of the width to the content; the export button stayed pinned at the
        bottom. This is the same arrangement with the Fluent material, so the
        preview gets the width instead of a third cramped column.
        """
        card = GlassCard(self, corner_radius=24, tint=(255, 255, 255, 26))
        card.setFixedWidth(372)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(2)
        self.source_desc_lbl = QLabel("本机微信 (未连接)")
        self.source_desc_lbl.setStyleSheet(
            native_theme.themed_qss("color: rgba(255, 255, 255, 140); font-size: 11px;")
        )
        head.addWidget(self.source_desc_lbl)
        outer.addLayout(head)

        scroll, _container, body = self._transparent_scroll()

        # ---- 01 数据源 ----
        body.addWidget(self._section_header("数据源", "01"))
        body.addSpacing(6)

        # Four compact actions in one row: two rows cost 40px the rail does not
        # have, and the labels are obvious enough to stand alone.
        source_row = QHBoxLayout()
        source_row.setSpacing(6)
        self.btn_connect = PillButton("连接", self, primary=True)
        self.btn_connect.setToolTip("连接本机微信账户")
        self.btn_connect.setFixedHeight(30)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_open_json = PillButton("导入", self)
        self.btn_open_json.setToolTip("从 JSON 文件导入聊天记录")
        self.btn_open_json.setFixedHeight(30)
        self.btn_open_json.clicked.connect(self._on_open_json)
        self.btn_read_img = PillButton("原图", self)
        self.btn_read_img.setFixedHeight(30)
        self.btn_read_img.setToolTip("解密并恢复图片原图")
        self.btn_read_img.clicked.connect(self._on_extract_images)
        self.btn_read_img.setEnabled(False)
        self.btn_transcribe = PillButton("语音", self)
        self.btn_transcribe.setFixedHeight(30)
        self.btn_transcribe.setToolTip("本地转写语音消息")
        self.btn_transcribe.clicked.connect(self._on_transcribe_voice)
        self.btn_transcribe.setEnabled(False)
        for button in (
            self.btn_connect,
            self.btn_open_json,
            self.btn_read_img,
            self.btn_transcribe,
        ):
            # Four buttons across 320px: let them shrink instead of demanding
            # their text width and widening the whole rail.
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            source_row.addWidget(button, stretch=1)
        body.addLayout(source_row)

        # ---- 02 记忆范围 ----
        body.addSpacing(14)
        range_head = QHBoxLayout()
        range_head.setSpacing(8)
        range_head.addWidget(self._section_header("记忆范围", "02"))
        self.btn_pick_contact = PillButton("全部", self)
        self.btn_pick_contact.setFixedHeight(24)
        self.btn_pick_contact.setStyleSheet(
            native_theme.themed_qss("font-size: 10px; color: rgba(255, 215, 160, 220); padding: 0 10px;")
        )
        self.btn_pick_contact.clicked.connect(self._on_pick_conversation)
        range_head.addWidget(self.btn_pick_contact)
        body.addLayout(range_head)
        body.addSpacing(10)

        body.addWidget(self._field_label("联系人 / 群聊"))
        body.addSpacing(4)
        self.conv_search_box = nm.SoftLineEdit()
        self.conv_search_box.setPlaceholderText("搜索联系人或群聊...")
        self.conv_search_box.textChanged.connect(self._filter_conversations)
        body.addWidget(self.conv_search_box)
        body.addSpacing(8)

        self.conv_scroll, self.conv_container, self.conv_vbox = self._transparent_scroll()
        self.conv_scroll.setMinimumHeight(134)
        self.conv_vbox.setContentsMargins(0, 0, 0, 0)
        self.conv_vbox.setSpacing(6)
        self.conv_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        body.addWidget(self.conv_scroll)
        body.addSpacing(12)

        body.addWidget(self._field_label("时间范围"))
        body.addSpacing(4)
        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        self.date_start = nm.SoftDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addYears(-1))
        self.date_start.dateChanged.connect(self._filter_messages)
        self.date_end = nm.SoftDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.dateChanged.connect(self._filter_messages)
        sep = QLabel("→")
        sep.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 140); font-weight: bold;"))
        date_row.addWidget(self.date_start, stretch=1)
        date_row.addWidget(sep)
        date_row.addWidget(self.date_end, stretch=1)
        body.addLayout(date_row)
        body.addSpacing(16)

        body.addSpacing(12)

        # ---- 03 归档设置 ----
        body.addSpacing(14)
        body.addWidget(self._section_header("归档设置", "03"))
        body.addSpacing(6)

        # Where it goes and who receives it change on every export, so they sit
        # at the top of the section; the format boxes are usually set once.
        body.addWidget(self._field_label("输出位置"))
        body.addSpacing(4)
        self.output_edit = nm.SoftLineEdit()
        self.output_edit.setText(self._default_export_path())
        self.output_edit.setCursorPosition(0)
        self.output_edit.setToolTip(self.output_edit.text())
        body.addWidget(self.output_edit)

        body.addSpacing(10)
        self.scene_bar = SceneDeliveryBar()
        self.scene_bar.setMinimumWidth(0)
        self.scene_bar.scene_changed.connect(self._apply_scene_to_controls)
        self.scene_bar.apply_styles(
            labels=native_theme.themed_qss("color: rgba(255, 255, 255, 150); font-size: 11px;"),
        )
        body.addWidget(self.scene_bar)

        body.addSpacing(6)
        body.addWidget(self._field_label("导出内容"))
        body.addSpacing(6)

        check_style = (
            "QCheckBox { color: %s; font-size: 12px; spacing: 9px; }"
            "QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px;"
            " border: none; background: %s; }"
            "QCheckBox::indicator:checked { background: %s; }"
            % (native_theme.ink_rgba(210), nm.BASE.name(), native_theme.accent_rgba(255))
        )
        # Short labels: the long ones ("PDF 视觉档案 · 必选") do not fit two per
        # row in a 330px rail, and the tooltip carries the full meaning.
        self.check_pdf = QCheckBox("PDF 档案")
        self.check_pdf.setToolTip("PDF 视觉档案（必选）")
        self.check_pdf.setChecked(True)
        self.check_pdf.setEnabled(False)
        self.check_markdown = QCheckBox("Markdown")
        self.check_markdown.setToolTip("同时生成可搜索的 Markdown")
        self.check_markdown.setChecked(True)
        self.check_json = QCheckBox("JSON")
        self.check_json.setToolTip("同时生成可再导入的规范化 JSON")
        self.check_json.setChecked(True)
        self.switch_image_pages = QCheckBox("图片独立页")
        self.switch_image_pages.setToolTip("高清图片独立成页")
        self.switch_image_pages.setChecked(True)
        self.switch_keep_png = QCheckBox("保留渲染 PNG")
        self.switch_keep_png.setChecked(False)
        for box in (
            self.check_pdf,
            self.check_markdown,
            self.check_json,
            self.switch_image_pages,
            self.switch_keep_png,
        ):
            box.setStyleSheet(check_style)

        check_row1 = QHBoxLayout()
        check_row1.setSpacing(10)
        check_row1.addWidget(self.check_pdf, stretch=1)
        check_row1.addWidget(self.check_markdown, stretch=1)
        check_row1.addWidget(self.check_json, stretch=1)
        check_row2 = QHBoxLayout()
        check_row2.setSpacing(10)
        check_row2.addWidget(self.switch_image_pages, stretch=1)
        check_row2.addWidget(self.switch_keep_png, stretch=1)
        body.addLayout(check_row1)
        body.addSpacing(2)
        body.addLayout(check_row2)
        self.switch_image_pages.toggled.connect(self._refresh_export_estimate)
        self.switch_keep_png.toggled.connect(self._refresh_export_estimate)

        body.addStretch(1)
        outer.addWidget(scroll, stretch=1)

        # One line instead of a boxed panel: the estimate is a caption for the
        # button, and the 40px it saves lets the conversation list show two whole
        # rows instead of one and a half.
        self.lbl_export_est = QLabel("请先连接微信或加载会话数据")
        self.lbl_export_est.setWordWrap(True)
        self.lbl_export_est.setStyleSheet(
            native_theme.themed_qss("color: rgba(255, 255, 255, 170); font-size: 11px;")
        )
        outer.addWidget(self.lbl_export_est)

        # Pinned at the bottom of the rail, like the classic window's action bar.
        self.btn_export = PillButton("导出记忆档案", self, primary=True)
        self.btn_export.setFixedHeight(46)
        self.btn_export.clicked.connect(self._on_export_clicked)
        outer.addWidget(self.btn_export)

        return card

    def _build_chat_card(self) -> GlassCard:
        card = GlassCard(self, corner_radius=24, tint=(255, 255, 255, 26))
        layout = QVBoxLayout(card)
        # 24px padding: the preview is the widest surface in the window and the
        # old 22/18 made the stream look pressed against the card edge.
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Row
        header = QHBoxLayout()
        header.setSpacing(12)

        v_title = QVBoxLayout()
        v_title.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.lbl_chat_title = QLabel("微信记忆时光流")
        self.lbl_chat_title.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 245); font-size: 17px; font-weight: bold;"))
        self.lbl_chat_tag = QLabel("未选择")
        self.lbl_chat_tag.setStyleSheet(native_theme.themed_qss("""
            background: transparent;
            border: none;
            color: rgba(255, 255, 255, 170);
            font-size: 10px;
            padding: 2px 8px;
        """))
        title_row.addWidget(self.lbl_chat_title)
        title_row.addWidget(self.lbl_chat_tag)
        title_row.addStretch(1)
        v_title.addLayout(title_row)

        self.lbl_chat_sub = QLabel("请在左侧选择联系人或群聊加载对话记录")
        self.lbl_chat_sub.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 140); font-size: 11px;"))
        v_title.addWidget(self.lbl_chat_sub)
        header.addLayout(v_title, stretch=1)

        # In-Chat Search Box
        self.search_box = nm.SoftLineEdit()
        self.search_box.setPlaceholderText("搜索当前记录...")
        self.search_box.setFixedWidth(220)
        self.search_box.textChanged.connect(self._filter_messages)
        header.addWidget(self.search_box)

        layout.addLayout(header)

        # Chat Bubble Stream View
        self.chat_stream = ChatBubbleStream(self)
        layout.addWidget(self.chat_stream, stretch=1)

        return card

    # --------------------------------------------------------------------------
    # Widget Helper Builders
    # --------------------------------------------------------------------------
    def _build_mini_stat(self, value: str, label: str) -> QWidget:
        box = SoftPanel(radius=14, strength=85)
        # Four cells across a 330px rail: none of them may demand a fixed width,
        # or the settings column overflows its viewport and gets clipped.
        box.setMinimumWidth(0)
        box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 7, 4, 7)
        lay.setSpacing(2)
        val_lbl = QLabel(value)
        val_lbl.setObjectName("statVal")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 245); font-size: 15px; font-weight: bold; border: none;"))
        cap_lbl = QLabel(label)
        cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap_lbl.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 140); font-size: 10px; border: none;"))
        for lbl in (val_lbl, cap_lbl):
            lbl.setMinimumWidth(0)
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(val_lbl)
        lay.addWidget(cap_lbl)
        return box

    def _build_switch_row(self, label_text: str, switch_widget: ToggleSwitch) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 225); font-size: 11px;"))
        row.addWidget(lbl)
        row.addStretch(1)
        row.addWidget(switch_widget)
        return row

    def _build_status_bullet(self, name: str, status: str, ok: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(native_theme.themed_qss(f"color: {'rgba(150, 245, 190, 230)' if ok else 'rgba(255, 140, 110, 230)'}; font-size: 10px;"))
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 200); font-size: 11px;"))
        status_lbl = QLabel(status)
        status_lbl.setObjectName("statusText")
        status_lbl.setStyleSheet(native_theme.themed_qss(f"color: {'rgba(170, 250, 205, 220)' if ok else 'rgba(255, 160, 140, 220)'}; font-size: 10px;"))

        row.addWidget(dot)
        row.addWidget(name_lbl)
        row.addStretch(1)
        row.addWidget(status_lbl)
        return row

    def _auto_discover(self) -> None:
        try:
            accounts = discover_wechat4_accounts()
            if accounts:
                acct = accounts[0]
                self.source_desc_lbl.setText(f"账号: {acct.account_id}")
                self.source_desc_lbl.setToolTip(str(acct.storage_dir))
        except Exception:
            pass

    def _set_type_filter(self, filter_type: str | None) -> None:
        self.pill_all.set_active(filter_type is None)
        self.pill_img.set_active(filter_type == "image")
        self.pill_voice.set_active(filter_type == "voice")
        self._current_type_filter = filter_type
        self._filter_messages()

    def _on_connect_clicked(self) -> None:
        confirm = QMessageBox.question(
            self,
            "连接微信",
            "连接时会重启微信一次，并可能要求扫码确认。微信原始数据库不会被修改。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._set_status("● 正在连接...")
        self.btn_connect.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)

        self._active_worker = SourceLoadWorker("wechat", "")
        self._active_worker.progress.connect(self._on_worker_progress)
        self._active_worker.completed.connect(self._on_source_ready)
        self._active_worker.failed.connect(self._on_worker_failed)
        self._active_worker.start()

    def _on_open_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择聊天记录 JSON", "", "JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        self._load_json_path(path)

    def _load_json_path(self, path: str) -> None:
        try:
            source = JsonChatSource(path)
            self._on_source_ready(source)
        except Exception as exc:
            self._on_worker_failed(str(exc))

    def _on_worker_progress(self, current: int, total: int, message: str) -> None:
        self._set_status(f"● {message}")

    def _populate_conversation_list(self, conversations: list) -> None:
        """Populate the left conversation drawer list."""
        while self.conv_vbox.count() > 0:
            item = self.conv_vbox.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._conv_widgets.clear()

        for conv in conversations:
            count = 0
            snippet = ""
            last_time = ""
            if isinstance(self._source, JsonChatSource):
                try:
                    msgs = self._source.get_messages(conv.id)
                    count = len(msgs)
                    if msgs:
                        last_msg = msgs[-1]
                        snippet = f"{last_msg.sender}: {last_msg.content}"
                        if last_msg.timestamp:
                            last_time = last_msg.timestamp.strftime("%m-%d")
                except Exception:
                    pass

            kind_str = conv.kind.value if hasattr(conv.kind, "value") else str(conv.kind)
            item_widget = ConversationItemWidget(
                cid=conv.id,
                name=conv.name,
                kind=kind_str,
                snippet=snippet,
                timestamp=last_time,
                count=count,
                parent=self.conv_container,
            )
            item_widget.clicked.connect(self._switch_conversation)
            self.conv_vbox.addWidget(item_widget)
            self._conv_widgets[conv.id] = item_widget

    def _filter_conversations(self, text: str) -> None:
        """Filter conversation list by keyword."""
        query = text.strip().lower()
        for _cid, w in self._conv_widgets.items():
            match = (query in w.conv_name.lower()) or (query in w.snippet.lower())
            w.setVisible(match)

    def _on_source_ready(self, source: ChatSource) -> None:
        self._source = source
        self.progress_bar.setValue(0)
        self.btn_connect.setEnabled(True)
        self.btn_read_img.setEnabled(isinstance(source, WeChat4LocalSource))
        self.btn_transcribe.setEnabled(True)

        conversations = source.list_conversations()
        self._all_conversations = conversations
        if not conversations:
            self._set_status("● 无会话数据")
            return

        # Populate the left conversation list
        self._populate_conversation_list(conversations)

        # Select first conversation
        first_cid = conversations[0].id
        self._switch_conversation(first_cid)

    def _on_pick_conversation(self) -> None:
        if not self._source:
            QMessageBox.information(self, "提示", "请先连接微信或加载会话数据。")
            return
        conversations = self._all_conversations or self._source.list_conversations()
        if not conversations:
            QMessageBox.information(self, "提示", "未找到任何会话。")
            return
        choices = [(f"{c.name} ({c.id})", c.id) for c in conversations]
        dialog = ConversationSearchDialog(choices, self._current_cid, self)
        if dialog.exec():
            selected_item = dialog.choice_list.currentItem()
            if selected_item:
                selected_cid = selected_item.data(Qt.ItemDataRole.UserRole)
                if selected_cid and selected_cid != self._current_cid:
                    self._switch_conversation(str(selected_cid))

    def _switch_conversation(self, cid: str) -> None:
        if not self._source:
            return
        self._current_cid = cid

        # Update item selection state
        for item_cid, widget in self._conv_widgets.items():
            widget.set_selected(item_cid == cid)

        conv_name = cid
        conv_kind = "direct"
        for c in (self._all_conversations or self._source.list_conversations()):
            if c.id == cid:
                conv_name = c.name
                conv_kind = c.kind.value if hasattr(c.kind, "value") else str(c.kind)
                break

        self.lbl_chat_title.setText(conv_name)
        self.lbl_chat_tag.setText("群聊" if conv_kind == "group" else "私聊")
        self.lbl_chat_tag.setStyleSheet(
            "background: rgba(120, 160, 220, 45); border: 1px solid rgba(140, 190, 255, 90); "
            "border-radius: 8px; color: rgba(200, 230, 255, 230); font-size: 10px; padding: 2px 8px;"
            if conv_kind == "group" else
            "background: rgba(140, 200, 170, 45); border: 1px solid rgba(170, 230, 200, 90); "
            "border-radius: 8px; color: rgba(210, 255, 230, 230); font-size: 10px; padding: 2px 8px;"
        )
        self.source_desc_lbl.setText(f"当前: {conv_name}")
        self._set_status("● 正在读取会话...")

        if isinstance(source := self._source, JsonChatSource):
            self._on_messages_loaded(source.get_messages(cid))
        else:
            self._active_worker = MessageLoadWorker(self._source, cid)
            self._active_worker.completed.connect(self._on_messages_loaded)
            self._active_worker.failed.connect(self._on_worker_failed)
            self._active_worker.start()

    def _on_messages_loaded(self, messages: list[Message]) -> None:
        self._messages = messages
        total_count = len(messages)
        self._set_status(f"● 已连接 · {total_count:,} 条")
        self.status_pill.setStyleSheet(native_theme.themed_qss("color: rgba(140, 255, 195, 240);"))

        # Update the conversation item badge and snippet in left list if missing
        if self._current_cid and self._current_cid in self._conv_widgets:
            item_w = self._conv_widgets[self._current_cid]
            if item_w.count == 0 and messages:
                item_w.count = len(messages)
                item_w.lbl_badge.setText(f"{len(messages)} 条")
                item_w.lbl_badge.show()
                item_w.lbl_snippet.setText(f"{messages[-1].sender}: {messages[-1].content}"[:22])
                if messages[-1].timestamp:
                    item_w.lbl_time.setText(messages[-1].timestamp.strftime("%m-%d"))

        # Update date ranges from messages
        if messages:
            dates = [m.timestamp.date() for m in messages if m.timestamp]
            if dates:
                min_d, max_d = min(dates), max(dates)
                self.date_start.blockSignals(True)
                self.date_end.blockSignals(True)
                self.date_start.setDate(QDate(min_d.year, min_d.month, min_d.day))
                self.date_end.setDate(QDate(max_d.year, max_d.month, max_d.day))
                self.date_start.blockSignals(False)
                self.date_end.blockSignals(False)

        self._filter_messages()


    def _on_worker_failed(self, error_msg: str) -> None:
        self.progress_bar.setValue(0)
        self.btn_connect.setEnabled(True)
        self._set_status("● 连接失败")
        self.status_pill.setStyleSheet(native_theme.themed_qss("color: rgba(255, 140, 120, 240);"))
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            print(f"[Worker Error] {error_msg}", file=sys.stderr, flush=True)
            return
        QMessageBox.critical(self, "操作失败", error_msg)

    def _filter_messages(self) -> None:
        if not self._messages:
            self.chat_stream.set_messages([])
            self.lbl_chat_sub.setText("尚未加载消息")
            return

        q_start = self.date_start.date()
        q_end = self.date_end.date()
        start_dt = datetime.combine(datetime(q_start.year(), q_start.month(), q_start.day()).date(), time.min)
        end_dt = datetime.combine(datetime(q_end.year(), q_end.month(), q_end.day()).date(), time.max)
        search_kw = self.search_box.text().strip().lower()
        filter_type = getattr(self, "_current_type_filter", None)

        filtered = []
        img_count = 0
        total_chars = 0
        active_days = set()

        for m in self._messages:
            if m.timestamp:
                if not (start_dt <= m.timestamp <= end_dt):
                    continue
                active_days.add(m.timestamp.date())

            if filter_type == "image" and m.type != MessageType.IMAGE:
                continue
            if filter_type == "voice" and m.type != MessageType.VOICE:
                continue

            if search_kw:
                if search_kw not in m.content.lower() and search_kw not in m.sender.lower():
                    continue

            if m.type == MessageType.IMAGE:
                img_count += 1
            total_chars += len(m.content)
            filtered.append(m)

        self._filtered_messages = filtered

        # Update chat stream
        self.chat_stream.set_messages(filtered)
        chars_text = f"~{total_chars:,}" if total_chars < 10000 else f"~{total_chars / 1000:.1f}k"
        self.lbl_chat_sub.setText(
            f"筛选出 {len(filtered):,} 条记忆 · {img_count:,} 张图片 · "
            f"跨越 {len(active_days)} 个活跃日 · {chars_text} 字"
        )

        # Update Gauge & Estimate
        self._update_storage_gauge(len(filtered), img_count)

    def _update_storage_gauge(self, msg_count: int, img_count: int) -> None:
        est_pages = max(1, int(msg_count / 12.0) + (img_count if self.switch_image_pages.isChecked() else 0))
        est_mb = max(1.0, est_pages * 0.48)
        est_minutes = max(0.1, msg_count * 0.059 / 60.0)

        if est_mb >= 1024:
            size_text = f"{est_mb / 1024.0:.1f} GB"
        else:
            size_text = f"{est_mb:.0f} MB"

        self.lbl_export_est.setText(
            f"导出预估：{est_pages:,} 页 · 约 {size_text} · 约 {est_minutes:.1f} 分钟 · 本地完成"
        )
        self._update_media_retention(img_count)

    def _refresh_export_estimate(self) -> None:
        """Recompute the estimate when an option that changes it is toggled."""
        messages = self._filtered_messages
        images = sum(1 for message in messages if message.type is MessageType.IMAGE)
        self._update_storage_gauge(len(messages), images)

    def _update_media_retention(self, img_count: int) -> None:
        """Show how much of the media in range is still on disk.

        WeChat purges old media, so a message whose original file is gone is
        exported as text only.  Surfacing that here means the user learns about
        it before exporting, instead of meeting "[图片]" afterwards.
        """
        lost = sum(
            1
            for message in self._filtered_messages
            if message.type is MessageType.IMAGE and message.image_path is None
        )
        total = img_count + lost
        if total <= 0:
            self.lbl_media_lost.setText("")
            self.media_bar.setValue(100)
            return

        self.lbl_media_lost.setText(f"{lost} 张已丢失" if lost else "全部可用")
        self.media_bar.setValue(int(round(100.0 * img_count / total)))

    def _on_extract_images(self) -> None:
        if not isinstance(self._source, WeChat4LocalSource):
            return
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self._set_status("● 正在扫描图片密钥...")

        self._active_worker = ImageKeyWorker(self._source)
        self._active_worker.progress.connect(self._on_worker_progress)
        self._active_worker.completed.connect(self._on_images_extracted)
        self._active_worker.failed.connect(self._on_worker_failed)
        self._active_worker.start()

    def _on_images_extracted(self, key: object) -> None:
        self.progress_bar.setValue(0)
        self._set_status("● 图片密钥解析成功")
        QMessageBox.information(self, "成功", "图片密钥提取成功，可导出高清原图！")

    def _on_transcribe_voice(self) -> None:
        if not self._messages:
            return
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self._set_status("● 正在转写语音...")

        self._active_worker = VoiceTranscriptionWorker(self._messages)
        self._active_worker.progress.connect(self._on_worker_progress)
        self._active_worker.completed.connect(self._on_voice_transcribed)
        self._active_worker.failed.connect(self._on_worker_failed)
        self._active_worker.start()

    def _on_voice_transcribed(self, messages: list[Message]) -> None:
        self.progress_bar.setValue(0)
        self._messages = messages
        self._filter_messages()
        self._set_status("● 语音转写完成")
        QMessageBox.information(self, "成功", "语音转写完成，内容已同步至记忆流！")

    def _selected_range(self) -> tuple[datetime, datetime]:
        start_date = self.date_start.date().toPython()
        end_date = self.date_end.date().toPython()
        return datetime.combine(start_date, time.min), datetime.combine(end_date, time.max)

    @staticmethod
    def _restorable_output(path: str) -> bool:
        """Whether a remembered output path is worth restoring.

        A run started by the test suite leaves ``pytest-of-...`` under the OS temp
        directory, and that path outlives the folder it pointed at. Restoring it
        would show the user a destination that no longer exists.
        """
        candidate = Path(path).expanduser()
        try:
            if not candidate.parent.is_dir():
                return False
            candidate.resolve().relative_to(Path(tempfile.gettempdir()).resolve())
        except (ValueError, OSError):
            return True
        return False

    def _default_export_path(self) -> str:
        saved = str(self._settings.value("outputPath", ""))
        if saved and self._restorable_output(saved):
            return saved
        return str(
            default_export_path(f"WeChat_Memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        )

    def _on_export_clicked(self) -> None:
        if not self._source or not self._filtered_messages:
            QMessageBox.warning(self, "无法导出", "当前没有可导出的记忆消息，请先连接或筛选。")
            return

        try:
            target = self.scene_bar.build_target()
        except DeliveryError as exc:
            QMessageBox.warning(self, "投递设置不完整", str(exc))
            return
        scene = self.scene_bar.selected_scene()

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出记忆档案 PDF",
            self.output_edit.text().strip() or self._default_export_path(),
            "PDF 文件 (*.pdf)",
        )
        if not out_path:
            return

        output = Path(out_path).expanduser().resolve()
        cid = self._current_cid or self._source.list_conversations()[0].id
        start, end = resolve_scene_range(scene, *self._selected_range())
        # ExportOptions lives in service.py; these keyword names must match that
        # dataclass exactly (output_pdf / start / end / pages_dir /
        # markdown_path / json_path / query).  This window previously called an
        # invented API (output_pdf_path / keyword / start_date / ...), so the
        # export button raised TypeError the moment it was clicked.
        options = ExportOptions(
            conversation_id=cid,
            output_pdf=output,
            start=start,
            end=end,
            include_image_pages=self.switch_image_pages.isChecked(),
            pages_dir=(
                output.with_name(f"{output.stem}_pages")
                if self.switch_keep_png.isChecked()
                else None
            ),
            markdown_path=output.with_suffix(".md") if self.check_markdown.isChecked() else None,
            json_path=output.with_suffix(".json") if self.check_json.isChecked() else None,
            query=self.search_box.text().strip() or (scene.query if scene else None),
        )
        self._settings.setValue("outputPath", str(output))
        self._export_output = output

        self.btn_export.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self._set_status("● 正在导出记忆档案...")

        self._active_worker = ExportWorker(
            self._source,
            options,
            store=JobStore(default_jobs_dir()),
            scene=scene,
            target=target,
        )
        self._active_worker.progress.connect(self._on_export_progress)
        self._active_worker.completed.connect(self._on_export_completed)
        self._active_worker.failed.connect(self._on_worker_failed)
        self._active_worker.start()

    def _apply_scene_to_controls(self, scene: Scene | None) -> None:
        """Mirror a scene's output choices into the checkboxes."""
        if scene is None:
            return
        self.switch_image_pages.setChecked(scene.include_image_pages)
        self.check_markdown.setChecked(scene.markdown)
        self.check_json.setChecked(scene.json_output)

    def _on_export_progress(self, current: int, total: int, message: str) -> None:
        self.progress_bar.show()
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self._set_status(f"● {message} ({current}/{total})")
        else:
            self.progress_bar.setRange(0, 0)
            self._set_status(f"● {message}")

    def _on_export_completed(self, result: ExportResult) -> None:
        self.progress_bar.setValue(0)
        self.btn_export.setEnabled(True)
        self._set_status("● 导出完成")
        self.status_detail.setText(f"上次导出 {datetime.now():%H:%M}")

        # List what was actually produced rather than only the PDF path -- with
        # Markdown/JSON enabled the user gets three files and previously had no
        # way to know.
        produced = [f"PDF · {result.page_count} 页"]
        if result.markdown_path:
            produced.append("Markdown")
        if result.json_path:
            produced.append("JSON")
        if result.pages_dir:
            produced.append("渲染 PNG")

        run = self._active_worker.run_result if isinstance(self._active_worker, ExportWorker) else None
        mirrored = mirror_export(result, self._export_output) if self._export_output else result
        final_path = mirrored.pdf_path
        summary = (
            f"记忆档案导出成功\n\n"
            f"消息 {result.message_count:,} 条\n"
            f"产物：{' · '.join(produced)}\n\n"
            f"{final_path}"
        )
        if run is not None and run.job is not None:
            summary += f"\n\n任务 {run.job.job_id}"
            if run.delivery is not None:
                summary += f"\n{run.delivery.describe()}"
        QMessageBox.information(self, "导出成功", summary)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            # normalGeometry() so that closing while maximized does not persist
            # the maximized size as the restored one.
            geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
            self._settings.setValue("dashboardSize", geometry.size())
            self._settings.setValue("dashboardPos", geometry.topLeft())
        except Exception:
            pass
        super().closeEvent(event)

    @staticmethod
    def _position_is_visible(position: QPoint) -> bool:
        """Do not restore onto a monitor that is no longer attached."""
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().contains(position):
                return True
        return False
