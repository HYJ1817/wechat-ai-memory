"""
Glass morphism effects for modern UI.
Provides blur effects and transparency helpers for Qt widgets.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsDropShadowEffect, QWidget


def apply_glass_effect(widget: QWidget, blur_radius: float = 20.0) -> None:
    """
    Apply glass morphism blur effect to a widget.

    Args:
        widget: The widget to apply the effect to
        blur_radius: Blur intensity (default: 20.0)
    """
    blur = QGraphicsBlurEffect()
    blur.setBlurRadius(blur_radius)
    widget.setGraphicsEffect(blur)


def apply_shadow(
    widget: QWidget,
    offset_x: float = 0,
    offset_y: float = 4,
    blur_radius: float = 16,
    color: tuple[int, int, int, int] = (0, 0, 0, 30)
) -> None:
    """
    Apply drop shadow to a widget for depth effect.

    Args:
        widget: The widget to apply shadow to
        offset_x: Horizontal shadow offset
        offset_y: Vertical shadow offset
        blur_radius: Shadow blur radius
        color: Shadow color as (r, g, b, a) tuple
    """
    shadow = QGraphicsDropShadowEffect()
    shadow.setOffset(offset_x, offset_y)
    shadow.setBlurRadius(blur_radius)
    shadow.setColor(QColor(*color))
    widget.setGraphicsEffect(shadow)


def apply_card_shadow(widget: QWidget) -> None:
    """
    Apply a standard card shadow for glass panels.

    Args:
        widget: The widget to apply card shadow to
    """
    apply_shadow(
        widget,
        offset_x=0,
        offset_y=2,
        blur_radius=12,
        color=(100, 80, 60, 25)
    )


def apply_elevated_shadow(widget: QWidget) -> None:
    """
    Apply an elevated shadow for floating elements like buttons.

    Args:
        widget: The widget to apply elevated shadow to
    """
    apply_shadow(
        widget,
        offset_x=0,
        offset_y=4,
        blur_radius=20,
        color=(120, 90, 60, 35)
    )


class GlassPanel(QWidget):
    """
    A custom widget that provides a glass morphism panel effect.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAutoFillBackground(False)
        self.setAttribute(115)  # Qt::WA_TranslucentBackground

    def paintEvent(self, event):
        """Custom paint event for glass effect background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw semi-transparent rounded rectangle
        rect = QRect(0, 0, self.width(), self.height())
        painter.setBrush(QColor(255, 255, 255, 180))  # 70% opacity white
        painter.setPen(QColor(255, 255, 255, 100))  # Border
        painter.drawRoundedRect(rect, 16, 16)
