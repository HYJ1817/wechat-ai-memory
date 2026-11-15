from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from wechat_context_exporter.ui import native_theme
from wechat_context_exporter.ui import neumorphic as nm


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def render(width: int, height: int, paint, radius: float = 12.0) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(nm.BASE)
    painter = QPainter(pixmap)
    paint(painter, QRectF(0, 0, width, height), radius)
    painter.end()
    return pixmap


def test_tokens_match_the_design_reference():
    assert nm.BASE.name() == "#e0e5ec"
    assert nm.SHADOW.name() == "#b8bcc2"
    assert nm.HIGHLIGHT.name() == "#ffffff"
    assert nm.BLURPLE.name() == "#6d5dfc"
    assert nm.CORAL.name() == "#ff6b6b"
    assert nm.MINT.name() == "#4ecdc4"
    assert nm.TEXT.name() == "#3d4451"


def test_page_and_elements_share_one_colour():
    palette = native_theme.active()
    assert palette.name == "neumorphic"
    assert palette.window == palette.surface == palette.surface_alt == nm.BASE.name()


def test_the_ui_is_light_only():
    assert native_theme.system_is_dark() is False


def test_low_alpha_white_backgrounds_become_transparent():
    qss = native_theme.themed_qss(
        "QFrame { background: rgba(255, 255, 255, 22); border: 1px solid rgba(255,255,255,55); }"
    )
    assert "background: transparent" in qss
    # The ink rewrite still applies to borders and text.
    assert "rgba(61, 68, 81, 55)" in qss


def test_opaque_white_backgrounds_are_kept():
    qss = native_theme.themed_qss("QLabel { background: rgba(255, 255, 255, 200); }")
    assert "transparent" not in qss


def test_raised_surface_is_the_base_colour_with_a_lit_top_left(app):
    pixmap = render(200, 80, lambda painter, rect, radius: nm.paint_surface(painter, rect, radius))

    centre = pixmap.toImage().pixelColor(100, 40)
    edge = pixmap.toImage().pixelColor(6, 40)
    assert centre.rgb() == nm.BASE.rgb()
    assert edge.red() > centre.red(), "the top-left edge should be lit"


def test_recessed_surface_is_dark_top_left_and_light_bottom_right(app):
    pixmap = render(200, 80, lambda painter, rect, radius: nm.paint_recessed(painter, rect, radius))
    image = pixmap.toImage()

    centre = image.pixelColor(100, 40)
    top_left = image.pixelColor(6, 40)
    bottom_right = image.pixelColor(194, 40)

    assert centre.rgb() == nm.BASE.rgb()
    assert top_left.red() < centre.red(), "inset shadow must darken the top-left edge"
    assert bottom_right.red() > centre.red(), "inset light must brighten the bottom-right edge"


def test_recessed_keeps_the_page_colour_in_the_middle_at_any_width(app):
    """The rim is a fixed thickness, so a wide control does not turn white."""
    wide = render(
        600, 32, lambda painter, rect, radius: nm.paint_recessed(painter, rect, radius), radius=16
    )
    assert wide.toImage().pixelColor(480, 16).rgb() == nm.BASE.rgb()


def test_raised_effect_is_reused_and_damped(app):
    from PySide6.QtWidgets import QWidget

    widget = QWidget()
    effect = nm.apply_raised(widget)
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert widget.graphicsEffect() is effect
    assert effect.offset().x() == nm.CARD_OFFSET

    nm.damp_raised(widget)
    assert effect.offset().x() < nm.CARD_OFFSET

    nm.restore_raised(widget)
    assert effect.offset().x() == nm.CARD_OFFSET

    again = nm.apply_raised(widget)
    assert again is effect, "applying twice must not stack effects"


def test_soft_inputs_paint_without_a_border(app):
    field = nm.SoftLineEdit()
    field.resize(180, 32)
    field.setText("hello")
    pixmap = field.grab()
    image = pixmap.toImage()

    assert image.pixelColor(4, 16).red() < image.pixelColor(90, 16).red()
    assert "border: none" in field.styleSheet()


def test_soft_combo_styles_its_view_in_place(app):
    combo = nm.SoftComboBox()
    combo.addItems(["a", "b"])
    assert combo.view() is not None
    assert combo.count() == 2
