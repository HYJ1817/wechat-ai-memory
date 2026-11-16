"""Custom glassmorphism UI components for WeChat AI Memory (Modern Dashboard).

Implements true frosted glass via pre-blurred backdrop slice sampling,
along with custom-drawn toggle switches, gauges, conversation drawer items,
and authentic conversational chat bubble streams with avatars and date dividers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from PIL import Image

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..models import Message

from . import native_theme
from . import fluent as nm

class GlassCard(QFrame):
    """A Fluent layer: white surface, 1px stroke, 8px corners.

    Kept under its old name because the layouts refer to it; Fluent separates
    surfaces with a stroke rather than a shadow, so there is no elevation here.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        corner_radius: float = 24.0,
        tint: tuple[int, int, int, int] | None = None,
        border: tuple[int, int, int, int] | None = None,
        draw_shadow: bool = True,
        draw_highlight: bool = True,
    ) -> None:
        super().__init__(parent)
        self.corner_radius = corner_radius
        # A tint is only honoured when it is opaque: a translucent wash would be a
        # fill, and a fill would break the "same colour as the page" rule.
        self.tint_color = QColor(*tint) if tint is not None else None
        self.draw_shadow = draw_shadow
        self.draw_highlight = draw_highlight
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if draw_shadow:
            nm.apply_raised(self, offset=nm.CARD_OFFSET, blur=nm.CARD_BLUR)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width(), self.height())
        fill = nm.BASE
        if self.tint_color is not None and self.tint_color.alpha() >= 200:
            fill = self.tint_color
        nm.paint_surface(
            painter,
            rect,
            self.corner_radius,
            fill=fill,
            highlight=200 if self.draw_highlight else 0,
        )


class ToggleSwitch(QWidget):
    """Modern iOS / Smart Home style pill toggle switch with amber active glow and smooth animation."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None, checked: bool = False) -> None:
        super().__init__(parent)
        self._checked = checked
        self._knob_pos = 1.0 if checked else 0.0
        self.setFixedSize(40, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"knob_position", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def get_knob_position(self) -> float:
        return self._knob_pos

    def set_knob_position(self, pos: float) -> None:
        self._knob_pos = float(pos)
        self.update()

    knob_position = Property(float, get_knob_position, set_knob_position)

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, checked: bool, animated: bool = True) -> None:  # noqa: N802
        if self._checked != checked:
            self._checked = checked
            self._animate_to(1.0 if checked else 0.0, animated=animated)
            self.toggled.emit(self._checked)

    def _animate_to(self, target: float, animated: bool = True) -> None:
        if not animated or not self.isVisible():
            self._anim.stop()
            self._knob_pos = target
            self.update()
            return

        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(target)
        self._anim.start()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._animate_to(1.0 if self._checked else 0.0, animated=True)
            self.toggled.emit(self._checked)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        radius = h / 2.0
        rect = QRectF(0, 0, w, h)
        palette = native_theme.active()

        on = self._checked
        track = palette.color("accent") if on else palette.color("surface")
        stroke = palette.color("accent") if on else palette.color("border_strong")
        painter.setBrush(track)
        painter.setPen(QPen(stroke, 1.0))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        t = max(0.0, min(1.0, self._knob_pos))
        diameter = h - 8.0
        x = 4.0 + t * (w - 8.0 - diameter)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF") if on else palette.color("text_faint"))
        painter.drawEllipse(QRectF(x, 4.0, diameter, diameter))


class StorageGauge(QWidget):
    """Circular arc gauge inspired by smart home thermostat dials with smooth arc sweep animation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(170, 175)
        self._value_text = "0"
        self._unit_text = "页 PDF"
        self._subtitle = "预估导出规模"
        self._target_percentage = 0.0
        self._animated_percentage = 0.0

        self._anim = QPropertyAnimation(self, b"animated_percentage", self)
        self._anim.setDuration(450)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_animated_percentage(self) -> float:
        return self._animated_percentage

    def set_animated_percentage(self, val: float) -> None:
        self._animated_percentage = float(val)
        self.update()

    animated_percentage = Property(float, get_animated_percentage, set_animated_percentage)

    def set_data(
        self,
        value: str,
        unit: str,
        subtitle: str,
        percentage: float,
        animated: bool = True,
    ) -> None:
        self._value_text = value
        self._unit_text = unit
        self._subtitle = subtitle
        target = max(0.0, min(1.0, percentage))
        self._target_percentage = target

        if not animated or not self.isVisible():
            self._anim.stop()
            self._animated_percentage = target
            self.update()
            return

        self._anim.stop()
        self._anim.setStartValue(self._animated_percentage)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 8.0
        r = min(cx, cy) - 14.0
        arc_rect = QRectF(cx - r, cy - r, r * 2.0, r * 2.0)

        # 1. Background Arc Track
        start_angle = 210 * 16
        span_angle = -240 * 16
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(native_theme.ink(38), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawArc(arc_rect, start_angle, span_angle)

        # 2. Glowing Active Arc (warm amber with animated sweep)
        active_span = int(span_angle * max(0.03, self._animated_percentage))
        painter.setPen(
            QPen(native_theme.accent_qcolor(240), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawArc(arc_rect, start_angle, active_span)

        # 3. Center Value Text
        painter.setPen(native_theme.ink(250))
        font_large = QFont("Microsoft YaHei", 24, QFont.Weight.Bold)
        painter.setFont(font_large)
        val_w = painter.fontMetrics().horizontalAdvance(self._value_text)
        painter.drawText(QPointF(cx - val_w / 2.0, cy + 4.0), self._value_text)

        # 4. Center Unit Text
        font_unit = QFont("Microsoft YaHei", 10, QFont.Weight.Normal)
        painter.setFont(font_unit)
        painter.setPen(native_theme.ink(170))
        unit_w = painter.fontMetrics().horizontalAdvance(self._unit_text)
        painter.drawText(QPointF(cx - unit_w / 2.0, cy + 24.0), self._unit_text)

        # 5. Bottom Subtitle
        font_sub = QFont("Microsoft YaHei", 10, QFont.Weight.Normal)
        painter.setFont(font_sub)
        painter.setPen(native_theme.accent_qcolor(210))
        sub_w = painter.fontMetrics().horizontalAdvance(self._subtitle)
        painter.drawText(QPointF(cx - sub_w / 2.0, self.height() - 8.0), self._subtitle)


class WindowControlButton(QPushButton):
    """Sleek frosted window control button (minimize, maximize, close) for frameless window."""

    def __init__(
        self,
        icon_type: str,  # "min", "max", "close"
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.icon_type = icon_type
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width(), self.height())
        radius = 8.0

        # Window controls are the one place where a hover inverts the material:
        # pressing them is the only destructive gesture in the chrome.
        if self.icon_type == "close" and self._hovered:
            painter.fillPath(nm.rounded_path(rect, radius), nm.CORAL)
            pen_color = QColor(255, 255, 255)
        elif self._hovered:
            nm.paint_recessed(painter, rect, radius, strength=115)
            pen_color = nm.TEXT
        else:
            nm.paint_surface(painter, rect, radius, highlight=110)
            pen_color = nm.TEXT_MUTED

        # Draw icon
        painter.setPen(QPen(pen_color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = self.width() / 2.0, self.height() / 2.0

        if self.icon_type == "min":
            painter.drawLine(QPointF(cx - 4.5, cy), QPointF(cx + 4.5, cy))
        elif self.icon_type == "max":
            icon_rect = QRectF(cx - 4.5, cy - 4.5, 9, 9)
            painter.drawRect(icon_rect)
        elif self.icon_type == "close":
            s = 4.0
            painter.drawLine(QPointF(cx - s, cy - s), QPointF(cx + s, cy + s))
            painter.drawLine(QPointF(cx + s, cy - s), QPointF(cx - s, cy + s))


class MemorySpotlightCard(QFrame):
    """Frosted glass spotlight card displaying the memory cover artwork and timeline recap."""

    view_media_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(106)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._cover_pixmap: QPixmap | None = None
        self._title_text: str = "记忆时光画报 · 暮色水榭"
        self._subtitle_text: str = "精选记忆 · 高清原图与原声已留存本地"
        self._badge_text: str = "精选留念"
        self._load_cover_asset()
        self._init_ui()

    def _load_cover_asset(self) -> None:
        asset_dir = Path(__file__).resolve().parents[1] / "assets"
        cover_path = asset_dir / "memory_cover.png"
        if cover_path.exists():
            try:
                self._cover_pixmap = QPixmap(str(cover_path))
            except Exception:
                self._cover_pixmap = None

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(14)

        # 1. Left Thumbnail Container (120x84)
        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(120, 84)
        self.thumb_label.setStyleSheet(native_theme.themed_qss("""
            border: none;
            border-radius: 12px;
            background: transparent;
        """))
        self._update_thumb_pixmap()
        layout.addWidget(self.thumb_label)

        # 2. Middle Info
        v_info = QVBoxLayout()
        v_info.setSpacing(5)
        v_info.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Row 1: Title
        self.lbl_title = QLabel(self._title_text, self)
        self.lbl_title.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 250); font-size: 14px; font-weight: bold;"))
        v_info.addWidget(self.lbl_title)

        # Row 2: Badge + Subtitle
        h_sub = QHBoxLayout()
        h_sub.setSpacing(8)
        self.lbl_badge = QLabel(self._badge_text, self)
        self.lbl_badge.setStyleSheet(native_theme.themed_qss("""
            background: rgba(109, 93, 252, 235);
            border: none;
            border-radius: 6px;
            color: #ffffff;
            font-size: 10px;
            font-weight: bold;
            padding: 1px 7px;
        """))
        self.lbl_sub = QLabel(self._subtitle_text, self)
        self.lbl_sub.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 160); font-size: 11px;"))
        h_sub.addWidget(self.lbl_badge)
        h_sub.addWidget(self.lbl_sub)
        h_sub.addStretch(1)
        v_info.addLayout(h_sub)

        # Mini Timeline Scrubber
        h_scrub = QHBoxLayout()
        h_scrub.setSpacing(8)
        self.scrub_bar = QFrame(self)
        self.scrub_bar.setFixedHeight(3)
        self.scrub_bar.setStyleSheet(native_theme.themed_qss("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(255, 175, 95, 230),
                stop:0.65 rgba(255, 215, 160, 230),
                stop:1.0 rgba(255, 255, 255, 40));
            border-radius: 1px;
        """))
        scrub_label = QLabel("时光轴已就绪", self)
        scrub_label.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 120); font-size: 10px;"))
        h_scrub.addWidget(self.scrub_bar, stretch=1)
        h_scrub.addWidget(scrub_label)
        v_info.addLayout(h_scrub)

        layout.addLayout(v_info, stretch=1)

        # 3. Right Action Pill
        self.btn_action = PillButton("查看画报", self, active=True)
        self.btn_action.setFixedHeight(30)
        self.btn_action.setStyleSheet(native_theme.themed_qss("""
            QPushButton {
                background: rgba(255, 255, 255, 35);
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 15px;
                color: rgba(255, 255, 255, 230);
                font-size: 11px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: rgba(255, 175, 95, 200);
                border: 1px solid rgba(255, 215, 160, 250);
                color: #241208;
            }
        """))
        self.btn_action.clicked.connect(self.view_media_requested)
        layout.addWidget(self.btn_action)

    def _update_thumb_pixmap(self) -> None:
        if self._cover_pixmap and not self._cover_pixmap.isNull():
            scaled = self._cover_pixmap.scaled(
                120, 84, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )
            # Clip with rounded corners
            rounded = QPixmap(120, 84)
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, 120, 84), 11, 11)
            painter.setClipPath(path)
            dx = max(0, (scaled.width() - 120) // 2)
            dy = max(0, (scaled.height() - 84) // 2)
            painter.drawPixmap(0, 0, scaled, dx, dy, 120, 84)
            painter.end()
            self.thumb_label.setPixmap(rounded)

    def set_content(self, title: str, subtitle: str, badge: str) -> None:
        self._title_text = title
        self._subtitle_text = subtitle
        self._badge_text = badge
        self.lbl_title.setText(title)
        self.lbl_sub.setText(subtitle)
        self.lbl_badge.setText(badge)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width(), self.height())
        radius = 16.0

        nm.paint_surface(painter, rect, radius, highlight=170)


class PillButton(QPushButton):
    """Capsule button: raised at rest, recessed while held, blurple when primary."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
        active: bool = False,
        primary: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self._active = active
        self._primary = primary
        self._hovered = False
        self._held = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._shadow = nm.apply_raised(
            self, offset=nm.CONTROL_OFFSET, blur=nm.CONTROL_BLUR, alpha=130
        )
        self._sync_shadow()

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        self._sync_shadow()
        self.update()

    def _sync_shadow(self) -> None:
        """Only surfaces that are actually raised may cast a shadow."""
        raised = not self._active and not self._primary
        self._shadow.setEnabled(raised)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        if self._shadow.isEnabled():
            nm.damp_raised(self)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._held = False
        if self._shadow.isEnabled():
            nm.restore_raised(self)
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._held = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._held = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        palette = native_theme.active()
        rect = QRectF(0, 0, float(self.width()), float(self.height()))
        radius = nm.ROUND_CONTROL

        if self._primary:
            fill = palette.color("accent")
            if self._held:
                fill = fill.darker(112)
            elif self._hovered:
                fill = fill.lighter(112)
            nm.paint_surface(painter, rect, radius, fill=fill, border=fill)
            text_color = QColor(palette.accent_text)
            font_weight = QFont.Weight.DemiBold
        elif self._active or self._held:
            nm.paint_surface(
                painter,
                rect,
                radius,
                fill=palette.color("pressed"),
                border=palette.color("border_strong"),
            )
            text_color = palette.color("text")
            font_weight = QFont.Weight.DemiBold
        else:
            fill = palette.color("hover") if self._hovered else palette.color("surface")
            nm.paint_surface(
                painter, rect, radius, fill=fill, border=palette.color("border_strong")
            )
            text_color = palette.color("text")
            font_weight = QFont.Weight.Normal

        font = QFont("Microsoft YaHei", 10, font_weight)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(nm.text_point(rect, self.text(), painter.fontMetrics()), self.text())


class AvatarBadge(QWidget):
    """Circular frosted glass avatar badge with initial or icon."""

    def __init__(
        self,
        name: str,
        size: int = 36,
        is_outgoing: bool = False,
        is_group: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.avatar_name = name
        self.avatar_size = size
        self.is_outgoing = is_outgoing
        self.is_group = is_group
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        r = min(w, h) / 2.0
        center = QPointF(w / 2.0, h / 2.0)

        palette = native_theme.active()
        disc = QRectF(center.x() - r + 0.5, center.y() - r + 0.5, (r - 1.0) * 2.0, (r - 1.0) * 2.0)

        tint = palette.color("accent")
        tint.setAlpha(38 if self.is_outgoing else 0)
        painter.setPen(QPen(palette.color("border_strong"), 1.0))
        painter.setBrush(tint if self.is_outgoing else palette.color("surface_alt"))
        painter.drawEllipse(disc)

        text_color = palette.color("accent") if self.is_outgoing else palette.color("text_muted")

        painter.setPen(text_color)
        font = QFont("Microsoft YaHei")
        font.setPixelSize(max(10, int(self.avatar_size * 0.40)))
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        if self.is_group:
            char = "群"
        elif self.avatar_name:
            char = self.avatar_name[:1].upper()
        else:
            char = "友"

        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(char)
        th = fm.ascent() - fm.descent()
        painter.drawText(QPointF((w - tw) / 2.0, (h + th) / 2.0 - 0.5), char)


class ChatDateDivider(QWidget):
    """Centered date divider pill between different days."""

    def __init__(self, date_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 2, 20, 2)
        layout.setSpacing(12)

        line_left = QFrame()
        line_left.setFrameShape(QFrame.Shape.HLine)
        line_left.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 30); background: rgba(255, 255, 255, 30); max-height: 1px;"))

        pill = QLabel(f" {date_text} ")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setStyleSheet(native_theme.themed_qss("""
            QLabel {
                background: rgba(255, 255, 255, 25);
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 12px;
                color: rgba(255, 255, 255, 220);
                font-size: 11px;
                font-weight: bold;
                padding: 3px 14px;
            }
        """))

        line_right = QFrame()
        line_right.setFrameShape(QFrame.Shape.HLine)
        line_right.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 30); background: rgba(255, 255, 255, 30); max-height: 1px;"))

        layout.addWidget(line_left, stretch=1)
        layout.addWidget(pill, stretch=0)
        layout.addWidget(line_right, stretch=1)


class ChatSystemMessage(QWidget):
    """Subtle centered system event capsule."""

    def __init__(self, text: str, timestamp: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 2, 20, 2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pill = QLabel(f"●  {text}")
        pill.setStyleSheet(native_theme.themed_qss("""
            QLabel {
                background: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 10px;
                color: rgba(255, 255, 255, 185);
                font-size: 11px;
                padding: 3px 12px;
            }
        """))
        layout.addWidget(pill)


class SoftPanel(QFrame):
    """A recessed block for content that sits *inside* a card.

    Nested raised surfaces would fight the card's own shadow, so anything inside a
    card is pressed into it instead.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        radius: float = 12.0,
        strength: int = 130,
    ) -> None:
        super().__init__(parent)
        self.radius = radius
        self.strength = strength
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        nm.paint_well(painter, QRectF(0, 0, self.width(), self.height()), self.radius)


class SoftBubble(QFrame):
    """A message bubble: raised from the same surface, 16px corners.

    Incoming and outgoing bubbles deliberately share one material.  A second
    colour would be a fill, and a fill would compete with the light source; the
    side of the column and the sender label already say who is talking.
    """

    def __init__(
        self, parent: QWidget | None = None, *, radius: float = nm.ROUND_CARD, outgoing: bool = False
    ) -> None:
        super().__init__(parent)
        self.radius = radius
        self.outgoing = outgoing
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = native_theme.active()
        rect = QRectF(0, 0, self.width(), self.height())
        if self.outgoing:
            tint = palette.color("accent")
            tint.setAlpha(26)
            nm.paint_surface(painter, rect, self.radius, fill=tint, border=QColor(0, 0, 0, 0))
        else:
            nm.paint_surface(
                painter, rect, self.radius,
                fill=palette.color("surface_alt"), border=palette.color("border"),
            )


class ChatMessageCard(QWidget):
    """Authentic conversational bubble with avatar, adaptive width, and rich media."""

    def __init__(
        self,
        sender: str,
        content: str,
        timestamp: str = "",
        is_outgoing: bool = False,
        msg_type: str = "text",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.sender = sender
        self.content = content
        self.timestamp = timestamp
        self.is_outgoing = is_outgoing
        self.msg_type = msg_type
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Root layout for message row
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(10, 5, 10, 5)
        root_layout.setSpacing(10)

        # Avatar badge
        avatar = AvatarBadge(
            name="我" if is_outgoing else sender,
            size=36,
            is_outgoing=is_outgoing,
            is_group=False,
        )

        # Message column: metadata header + bubble
        msg_col = QVBoxLayout()
        msg_col.setContentsMargins(0, 0, 0, 0)
        msg_col.setSpacing(4)

        # Header metadata (sender & time)
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(2, 0, 2, 0)
        hdr_layout.setSpacing(8)

        lbl_sender = QLabel("我" if is_outgoing else sender)
        lbl_sender.setStyleSheet(
            f"color: {nm.BLURPLE.name() if is_outgoing else nm.TEXT.name()};"
            "font-size: 11px; font-weight: bold; background: transparent;"
        )
        time_display = timestamp.split(" ")[-1] if " " in timestamp else timestamp
        lbl_time = QLabel(time_display)
        lbl_time.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 130); font-size: 10px;"))

        if is_outgoing:
            hdr_layout.addStretch(1)
            hdr_layout.addWidget(lbl_time)
            hdr_layout.addWidget(lbl_sender)
        else:
            hdr_layout.addWidget(lbl_sender)
            hdr_layout.addWidget(lbl_time)
            hdr_layout.addStretch(1)
        msg_col.addLayout(hdr_layout)

        # Bubble container
        bubble_frame = SoftBubble(outgoing=is_outgoing)
        bubble_frame.setObjectName("msgBubble")

        bubble_layout = QVBoxLayout(bubble_frame)
        bubble_layout.setContentsMargins(12, 10, 12, 10)
        bubble_layout.setSpacing(6)

        # Resolve media content
        body_text = content
        if msg_type == "image":
            img_candidate = self._resolve_image_path(content)
            if img_candidate and img_candidate.is_file():
                pm = QPixmap(str(img_candidate))
                if not pm.isNull():
                    thumb_lbl = QLabel()
                    thumb_lbl.setPixmap(
                        pm.scaled(280, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                    thumb_lbl.setStyleSheet(native_theme.themed_qss("border-radius: 8px; border: 1px solid rgba(255, 255, 255, 60); background: transparent;"))
                    bubble_layout.addWidget(thumb_lbl)
            body_text = f"[图片] {Path(content).name}"
        elif msg_type == "file":
            body_text = f"[文件] {Path(content).name}"
        elif msg_type == "voice":
            body_text = "[语音] 3\""

        lbl_body = QLabel(body_text)
        lbl_body.setWordWrap(True)
        lbl_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_body.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 245); font-size: 12px; line-height: 1.45; background: transparent; border: none;"))
        bubble_layout.addWidget(lbl_body)

        # Adaptive width calculation
        fm = QFontMetrics(QFont("Microsoft YaHei", 12))
        bounding = fm.boundingRect(QRect(0, 0, 500, 10000), int(Qt.TextFlag.TextWordWrap), body_text)
        ideal_width = min(500, max(80, bounding.width() + 32))
        if msg_type == "image":
            ideal_width = max(ideal_width, 290)
        bubble_frame.setMaximumWidth(ideal_width)

        # Add bubble to message column with alignment
        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        if is_outgoing:
            bubble_row.addStretch(1)
            bubble_row.addWidget(bubble_frame, stretch=0)
        else:
            bubble_row.addWidget(bubble_frame, stretch=0)
            bubble_row.addStretch(1)
        msg_col.addLayout(bubble_row)

        # Assemble root layout with Avatar
        if is_outgoing:
            root_layout.addStretch(1)
            root_layout.addLayout(msg_col, stretch=0)
            root_layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        else:
            root_layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
            root_layout.addLayout(msg_col, stretch=0)
            root_layout.addStretch(1)

    def _resolve_image_path(self, path_str: str) -> Path | None:
        p = Path(path_str)
        if p.is_file():
            return p
        root = Path(__file__).resolve().parents[3]
        candidate = root / "examples" / path_str
        if candidate.is_file():
            return candidate
        return None


class ConversationItemWidget(QWidget):
    """Clickable conversation item card in the left list."""
    clicked = Signal(str)  # cid

    def __init__(
        self,
        cid: str,
        name: str,
        kind: str = "direct",
        snippet: str = "",
        timestamp: str = "",
        count: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cid = cid
        self.conv_name = name
        self.kind = kind
        self.snippet = snippet
        self.timestamp = timestamp
        self.count = count
        self._selected = False
        self._hovered = False

        self.setFixedHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # The row must not dictate the rail's width: a long snippet used to push
        # the list's minimum width past the viewport and clip the right edge.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setSpacing(10)

        # Left: Avatar
        self.avatar = AvatarBadge(
            name=name,
            size=40,
            is_group=(kind == "group"),
        )
        layout.addWidget(self.avatar)

        # Middle: Name and Snippet
        mid_col = QVBoxLayout()
        mid_col.setContentsMargins(0, 0, 0, 0)
        mid_col.setSpacing(2)

        self.lbl_title = QLabel(name)
        self.lbl_title.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 245); font-size: 13px; font-weight: bold; background: transparent;"))
        mid_col.addWidget(self.lbl_title)

        snippet_display = snippet if snippet else "无新消息"
        if len(snippet_display) > 22:
            snippet_display = snippet_display[:20] + "..."
        self.lbl_snippet = QLabel(snippet_display)
        self.lbl_snippet.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 140); font-size: 11px; background: transparent;"))
        # Both labels shrink instead of dictating the rail width; a long snippet
        # used to widen the whole settings column and clip its right edge.
        for label in (self.lbl_title, self.lbl_snippet):
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        mid_col.addWidget(self.lbl_snippet)
        layout.addLayout(mid_col, stretch=1)

        # Right: Time and Count Badge
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_time = QLabel(timestamp)
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_time.setStyleSheet(native_theme.themed_qss("color: rgba(255, 255, 255, 120); font-size: 10px; background: transparent;"))
        right_col.addWidget(self.lbl_time)

        self.lbl_badge = QLabel(f"{count} 条" if count > 0 else "")
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        palette = native_theme.active()
        self.lbl_badge.setStyleSheet(
            "QLabel { background: %s; border: none; border-radius: 9px; color: %s;"
            " font-size: 10px; font-weight: bold; padding: 1px 6px; }"
            % (palette.accent, palette.accent_text)
        )
        if count == 0:
            self.lbl_badge.hide()
        right_col.addWidget(self.lbl_badge)
        layout.addLayout(right_col)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def is_selected(self) -> bool:
        return self._selected

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.cid)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        rect = QRectF(2, 2, w - 4, h - 4)
        palette = native_theme.active()

        if self._selected:
            nm.paint_surface(
                painter, rect, nm.ROUND_CONTROL, fill=palette.color("hover"),
                border=QColor(0, 0, 0, 0),
            )
            nm.paint_accent_bar(painter, QRectF(6, (h - 20) / 2.0, 3, 20))
        elif self._hovered:
            nm.paint_surface(
                painter, rect, nm.ROUND_CONTROL, fill=palette.color("surface_alt"),
                border=QColor(0, 0, 0, 0),
            )


class ChatBubbleStream(QScrollArea):
    """Scrollable stream of chat bubbles with date dividers and system messages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # QScrollArea already scrolls per pixel; setVerticalScrollMode belongs to
        # QAbstractItemView and does not exist here.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet(native_theme.themed_qss("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(255, 255, 255, 12);
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 65);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 180, 100, 180);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """))
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.container = QWidget()
        self.container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        self.vbox.setSpacing(12)
        self.vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.container)

    def set_messages(self, messages: list[Message], max_display: int = 250) -> None:
        """Populate chat bubbles with smart date dividers and system messages."""
        while self.vbox.count() > 0:
            item = self.vbox.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        display_list = messages[:max_display]
        prev_date = None
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

        for msg in display_list:
            msg_date = msg.timestamp.date() if msg.timestamp else None
            if msg_date is not None and msg_date != prev_date:
                date_str = msg_date.strftime("%Y年%m月%d日")
                wday_str = weekdays[msg_date.weekday()]
                divider = ChatDateDivider(f"{date_str} {wday_str}")
                self.vbox.addWidget(divider)
                prev_date = msg_date

            msg_type_str = msg.type.value if hasattr(msg.type, "value") else str(msg.type)
            if msg_type_str == "system":
                card = ChatSystemMessage(
                    text=msg.content,
                    timestamp=msg.timestamp.strftime("%H:%M") if msg.timestamp else "",
                )
            else:
                time_str = msg.timestamp.strftime("%Y-%m-%d %H:%M") if msg.timestamp else ""
                card = ChatMessageCard(
                    sender=msg.sender,
                    content=msg.content,
                    timestamp=time_str,
                    is_outgoing=msg.is_outgoing,
                    msg_type=msg_type_str,
                )
            self.vbox.addWidget(card)

