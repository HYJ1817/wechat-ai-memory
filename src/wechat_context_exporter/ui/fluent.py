"""WinUI 3 surfaces: flat fills, 1px strokes, accent underline on focus.

Fluent does not model depth with shadows on ordinary controls; it uses a stroke,
a hover fill and an accent bar.  So the whole material here is two primitives:

* :func:`paint_surface` -- a rounded rect with a fill and a 1px stroke, used by
  cards, buttons and list rows;
* :func:`paint_well` -- the same but on the sunken fill, for read-only blocks.

The module deliberately keeps the names the widgets already called (``apply_raised``
and friends) so the repaint could happen without rewriting every call site; the
elevation helpers are now no-ops because Fluent does not raise anything.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QDateEdit, QLineEdit, QSizePolicy

from . import native_theme

ROUND_CARD = 8
ROUND_CONTROL = 4
CONTROL_HEIGHT = 32

# Kept for call sites that still ask for elevation values.
CARD_OFFSET = CARD_BLUR = CONTROL_OFFSET = CONTROL_BLUR = 0


def _palette():
    return native_theme.active()


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_surface(
    painter: QPainter,
    rect: QRectF,
    radius: float = ROUND_CARD,
    *,
    fill: QColor | None = None,
    highlight: int = 0,
    border: QColor | None = None,
) -> None:
    """A Fluent layer: rounded fill plus a hairline stroke.

    ``highlight`` is accepted and ignored -- it belonged to the neumorphic rim.
    """
    palette = _palette()
    fill_colour = QColor(fill) if fill is not None else palette.color("surface")
    if border is not None:
        stroke = QColor(border)
    elif fill is not None:
        stroke = fill_colour.darker(104)
    else:
        stroke = palette.color("border")

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = rounded_path(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius)
    painter.fillPath(shape, fill_colour)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(stroke, 1.0))
    painter.drawPath(shape)
    painter.restore()


def paint_well(painter: QPainter, rect: QRectF, radius: float = ROUND_CONTROL, **_) -> None:
    """A sunken block (estimate, media retention) on the alternate surface."""
    palette = _palette()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = rounded_path(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius)
    painter.fillPath(shape, palette.color("surface_alt"))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(palette.color("divider"), 1.0))
    painter.drawPath(shape)
    painter.restore()


def paint_recessed(painter: QPainter, rect: QRectF, radius: float = ROUND_CONTROL, **kwargs) -> None:
    """Old name for :func:`paint_well`; kept so untouched call sites keep working."""
    paint_well(painter, rect, radius, **kwargs)


def paint_accent_bar(painter: QPainter, rect: QRectF) -> None:
    """The 3px selection pill WinUI puts left of an active navigation item."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_palette().color("accent"))
    painter.drawRoundedRect(rect, rect.width() / 2.0, rect.width() / 2.0)
    painter.restore()


class _NoElevation:
    """Stand-in for the old drop-shadow effect (Fluent raises nothing)."""

    def setEnabled(self, _enabled: bool) -> None:  # noqa: N802
        return

    def isEnabled(self) -> bool:  # noqa: N802
        return False


def apply_raised(widget, **_kwargs) -> _NoElevation:
    return _NoElevation()


def damp_raised(_widget) -> None:
    return


def restore_raised(_widget) -> None:
    return


# -- compatible re-exports used by the widget module -----------------------


class _Tokens:
    """Theme colours resolved on access, so light/dark needs no call-site work."""

    @property
    def TEXT(self) -> QColor:  # noqa: N802
        return _palette().color("text")

    @property
    def TEXT_MUTED(self) -> QColor:  # noqa: N802
        return _palette().color("text_muted")

    @property
    def BASE(self) -> QColor:  # noqa: N802
        return _palette().color("surface")

    @property
    def BLURPLE(self) -> QColor:  # noqa: N802
        return _palette().color("accent")

    @property
    def CORAL(self) -> QColor:  # noqa: N802
        return QColor("#C42B1C")

    @property
    def MINT(self) -> QColor:  # noqa: N802
        return QColor("#0F7B0F")


_tokens = _Tokens()


def __getattr__(name: str):
    """Expose the colour tokens as ``fluent.TEXT`` etc. without freezing them."""
    if name in {"TEXT", "TEXT_MUTED", "BASE", "BLURPLE", "CORAL", "MINT"}:
        return getattr(_tokens, name)
    raise AttributeError(name)


def input_qss(*, padding: str = "6px 10px", popup: bool = False) -> str:
    qss = f"""
        background: transparent;
        border: none;
        color: {_palette().text};
        padding: {padding};
        selection-background-color: {_palette().accent};
        selection-color: {_palette().accent_text};
    """
    if not popup:
        return qss
    return qss + f"""
        QComboBox QAbstractItemView {{
            background: {_palette().surface};
            color: {_palette().text};
            border: 1px solid {_palette().border};
            padding: 4px;
            outline: none;
            selection-background-color: {_palette().hover};
            selection-color: {_palette().text};
        }}
    """


class _FluentField:
    """A WinUI text field: 1px stroke, white fill, 2px accent underline on focus."""

    def _init_field(self, radius: int) -> None:
        self._radius = radius
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setStyleSheet(input_qss())

    def _paint_field(self, painter: QPainter) -> None:
        palette = _palette()
        rect = QRectF(self.rect())
        paint_surface(painter, rect, self._radius, border=palette.color("border_strong"))
        if self.hasFocus():
            pen = QPen(palette.color("accent"), 2.0)
            painter.setPen(pen)
            bottom = rect.bottom() - 1.0
            painter.drawLine(
                QPointF(rect.left() + self._radius, bottom),
                QPointF(rect.right() - self._radius, bottom),
            )


class SoftLineEdit(_FluentField, QLineEdit):
    def __init__(self, *args, radius: int = ROUND_CONTROL, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_field(radius)
        self.setFrame(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_field(painter)
        painter.end()
        super().paintEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.update()


class SoftComboBox(_FluentField, QComboBox):
    def __init__(self, *args, radius: int = ROUND_CONTROL, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_field(radius)
        self.setStyleSheet(input_qss(padding="5px 10px", popup=True))
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_field(painter)
        painter.end()
        super().paintEvent(event)


class SoftDateEdit(_FluentField, QDateEdit):
    def __init__(self, *args, radius: int = ROUND_CONTROL, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_field(radius)
        self.setFrame(False)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_field(painter)
        painter.end()
        super().paintEvent(event)


def text_point(rect: QRectF, text: str, font_metrics) -> QPointF:
    width = font_metrics.horizontalAdvance(text)
    height = font_metrics.ascent() - font_metrics.descent()
    return QPointF(
        rect.left() + (rect.width() - width) / 2.0,
        rect.top() + (rect.height() + height) / 2.0 - 1.0,
    )
