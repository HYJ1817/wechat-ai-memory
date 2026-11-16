"""Neumorphic material: one surface colour, one fixed light source.

The whole system rests on two rules:

* every element is filled with the same base colour as the page -- depth is never
  expressed by a different fill, only by shadow;
* the light comes from the top left, always.  Raised means a white rim on the top
  left plus a cool grey shadow on the bottom right; recessed means the same pair
  turned inside the shape.

Qt has no ``box-shadow``, and a widget can only carry one ``QGraphicsEffect``, so
the two halves of the pair are produced differently:

* the outer shadow is a real ``QGraphicsDropShadowEffect`` -- it is drawn by the
  parent, which is the only way Qt lets a child cast a shadow outside its own
  rect.  This is what makes cards read as raised on a same-coloured page.
* the highlight is painted inside the shape as a clipped diagonal gradient.  It
  costs nothing, cannot be clipped by the widget rect, and reads as the lit edge.

A recessed shape needs no effect at all: both halves are gradients inside the
shape, which is why inputs and toggle tracks can be flat widgets.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QSizePolicy,
    QDateEdit,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QWidget,
)

# -- tokens (from the design reference) ------------------------------------

BASE = QColor("#e0e5ec")
SHADOW = QColor("#b8bcc2")
HIGHLIGHT = QColor("#ffffff")
BLURPLE = QColor("#6d5dfc")
CORAL = QColor("#ff6b6b")
MINT = QColor("#4ecdc4")
TEXT = QColor("#3d4451")
TEXT_MUTED = QColor("#6f7683")
TEXT_FAINT = QColor("#9aa1ad")

RADIUS_CARD = 24
RADIUS_CONTROL = 16
RADIUS_PILL = 999

# Denser than the 8/16px of the web reference: with a 16px column gap and a
# 1080px-wide window, an 8px offset plus 16px blur would have neighbouring cards
# painting into each other.  Half the values on the same ratio keep the material
# legible at desktop density without the shadows colliding.
CARD_OFFSET = 5
CARD_BLUR = 16
CONTROL_OFFSET = 3
CONTROL_BLUR = 8


def _with_alpha(color: QColor, alpha: int) -> QColor:
    tinted = QColor(color)
    tinted.setAlpha(alpha)
    return tinted


# -- raised ---------------------------------------------------------------


def apply_raised(
    widget: QWidget,
    *,
    offset: int = CARD_OFFSET,
    blur: int = CARD_BLUR,
    alpha: int = 190,
) -> QGraphicsDropShadowEffect:
    """Give ``widget`` the bottom-right half of the raised pair.

    Reuses an existing effect so a hover or a state change does not stack effects
    (Qt keeps only the last one anyway, and the old one leaks otherwise).
    """
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsDropShadowEffect):
        effect = QGraphicsDropShadowEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOffset(offset, offset)
    effect.setBlurRadius(blur)
    effect.setColor(_with_alpha(SHADOW, alpha))
    return effect


def damp_raised(widget: QWidget, *, factor: float = 0.5) -> None:
    """Shrink the shadow when the pointer is near -- "a hand shading the light"."""
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsDropShadowEffect):
        effect.setOffset(CARD_OFFSET * factor, CARD_OFFSET * factor)
        effect.setBlurRadius(CARD_BLUR * factor)


def restore_raised(widget: QWidget) -> None:
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsDropShadowEffect):
        effect.setOffset(CARD_OFFSET, CARD_OFFSET)
        effect.setBlurRadius(CARD_BLUR)


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _band(rect: QRectF, low: float = 6.0, high: float = 14.0) -> float:
    """Thickness of the shaded rim, in pixels.

    A percentage ramp looks right on a small control and wrong on a wide one: on a
    290px pill it washes two thirds of the shape, which reads as a white fill.
    A fixed rim keeps the shading on the edge whatever the element's size.
    """
    return max(low, min(high, min(rect.width(), rect.height()) * 0.24))


def _edge_wash(
    painter: QPainter,
    rect: QRectF,
    band: float,
    *,
    color: QColor,
    alpha: int,
    edges: tuple[str, ...],
) -> None:
    """Fill a fading band along each named edge, clipped to the shape.

    A single diagonal gradient only shades the corner it starts from; a real
    inner shadow follows the whole edge.  Four linear fills give that for the cost
    of four rects.
    """
    if alpha <= 0:
        return
    left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()

    if "top" in edges:
        gradient = QLinearGradient(QPointF(0, top), QPointF(0, top + band))
        gradient.setColorAt(0.0, _with_alpha(color, alpha))
        gradient.setColorAt(1.0, _with_alpha(color, 0))
        painter.fillRect(QRectF(left, top, rect.width(), band), gradient)
    if "left" in edges:
        gradient = QLinearGradient(QPointF(left, 0), QPointF(left + band, 0))
        gradient.setColorAt(0.0, _with_alpha(color, alpha))
        gradient.setColorAt(1.0, _with_alpha(color, 0))
        painter.fillRect(QRectF(left, top, band, rect.height()), gradient)
    if "bottom" in edges:
        gradient = QLinearGradient(QPointF(0, bottom), QPointF(0, bottom - band))
        gradient.setColorAt(0.0, _with_alpha(color, alpha))
        gradient.setColorAt(1.0, _with_alpha(color, 0))
        painter.fillRect(QRectF(left, bottom - band, rect.width(), band), gradient)
    if "right" in edges:
        gradient = QLinearGradient(QPointF(right, 0), QPointF(right - band, 0))
        gradient.setColorAt(0.0, _with_alpha(color, alpha))
        gradient.setColorAt(1.0, _with_alpha(color, 0))
        painter.fillRect(QRectF(right - band, top, band, rect.height()), gradient)


def paint_surface(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    *,
    fill: QColor | None = None,
    highlight: int = 210,
) -> None:
    """Flat base fill plus the top-left lit rim.  Draw the shadow separately."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = rounded_path(rect, radius)
    painter.fillPath(path, fill or BASE)

    if highlight:
        painter.setClipPath(path)
        _edge_wash(
            painter,
            rect,
            _band(rect),
            color=HIGHLIGHT,
            alpha=highlight,
            edges=("top", "left"),
        )
    painter.restore()


def paint_raised(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    *,
    fill: QColor | None = None,
    hover: bool = False,
) -> None:
    """The whole raised material, for widgets that draw their own shadow."""
    paint_surface(painter, rect, radius, fill=fill, highlight=230 if hover else 190)


# -- recessed -------------------------------------------------------------


def paint_recessed(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    *,
    fill: QColor | None = None,
    strength: int = 155,
    lit: bool = False,
) -> None:
    """Inset pair: dark wash from the top left, white wash from the bottom right.

    ``lit`` tints the inset shadow toward blurple, which is how a focused input
    keeps its recess while still showing focus.
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = rounded_path(rect, radius)
    painter.fillPath(path, fill or BASE)
    painter.setClipPath(path)

    shadow = BLURPLE if lit else SHADOW
    band = _band(rect)
    _edge_wash(
        painter,
        rect,
        band,
        color=shadow,
        alpha=strength if not lit else max(60, strength // 2),
        edges=("top", "left"),
    )
    _edge_wash(
        painter,
        rect,
        band,
        color=HIGHLIGHT,
        alpha=240,
        edges=("bottom", "right"),
    )

    painter.setClipping(False)
    painter.restore()


def paint_inset_line(painter: QPainter, rect: QRectF, radius: float, *, width: float = 1.4) -> None:
    """A hairline that only exists as a shadow, for separating stacked rows."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(_with_alpha(SHADOW, 90), width))
    painter.drawRoundedRect(rect, radius, radius)
    painter.restore()


# -- widgets that are recessed by nature -----------------------------------


def input_qss(
    *, radius: int = RADIUS_CONTROL, padding: str = "8px 14px", popup: bool = False
) -> str:
    """Styling for the text layer only; the material is painted underneath.

    ``background: transparent`` is what lets :class:`SoftLineEdit` draw the
    recess first and then let Qt paint the text on top of it.

    ``popup`` adds the dropdown rules through the descendant selector instead of
    styling ``view()`` directly.  Touching ``view()`` builds the popup list as a
    separate top-level window at construction time, and that window crashes during
    interpreter shutdown on CI (access violation with no Python frame).
    """
    qss = f"""
        background: transparent;
        border: none;
        border-radius: {radius}px;
        color: {TEXT.name()};
        padding: {padding};
        selection-background-color: {BLURPLE.name()};
        selection-color: #ffffff;
    """
    if not popup:
        return qss
    return qss + f"""
        QComboBox QAbstractItemView {{
            background: {BASE.name()};
            color: {TEXT.name()};
            border: none;
            border-radius: 10px;
            padding: 4px;
            outline: none;
            selection-background-color: {BLURPLE.name()};
            selection-color: #ffffff;
        }}
    """


class SoftLineEdit(QLineEdit):
    """A line edit that sits in the page rather than on top of it."""

    def __init__(self, *args, radius: int = RADIUS_CONTROL, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._radius = radius
        self.setStyleSheet(input_qss(radius=radius))
        self.setFrame(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_recessed(painter, QRectF(self.rect()), self._radius)
        painter.end()
        super().paintEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.update()


class SoftComboBox(QComboBox):
    """Same material as :class:`SoftLineEdit`; the popup stays a native list."""

    def __init__(self, *args, radius: int = RADIUS_CONTROL, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._radius = radius
        # Popup styling goes through the stylesheet selector: calling view()
        # here would build a top-level popup window that outlives the app and
        # crashes at shutdown.
        self.setStyleSheet(input_qss(radius=radius, padding="5px 10px", popup=True))
        # Long items ("投递到 Obsidian") would otherwise force a minimum width the
        # settings rail cannot give, and the scroll content overflows sideways.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_recessed(painter, QRectF(self.rect()), self._radius)
        painter.end()
        super().paintEvent(event)


class SoftDateEdit(QDateEdit):
    def __init__(self, *args, radius: int = RADIUS_CONTROL, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._radius = radius
        self.setStyleSheet(input_qss(radius=radius, padding="6px 12px"))
        self.setFrame(False)
        # QDateEdit's size hint is ~176px once the calendar button is counted; a
        # pair of them then overflows a 330px settings rail. An explicit minimum
        # overrides that hint, and stretch still divides the row evenly.
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_recessed(painter, QRectF(self.rect()), self._radius)
        painter.end()
        super().paintEvent(event)


def soft_text_qss(*, size: int = 12, weight: int = 400, color: QColor | None = None) -> str:
    """Convenience for QLabel styling that keeps the type scale honest."""
    tone = color or TEXT
    return f"color: {tone.name()}; font-size: {size}px; font-weight: {weight};"


def text_point(rect: QRectF, text: str, font_metrics) -> QPointF:
    """Centre a string inside ``rect`` -- used by the hand-painted buttons."""
    width = font_metrics.horizontalAdvance(text)
    height = font_metrics.ascent() - font_metrics.descent()
    return QPointF(
        rect.left() + (rect.width() - width) / 2.0,
        rect.top() + (rect.height() + height) / 2.0 - 1.0,
    )
