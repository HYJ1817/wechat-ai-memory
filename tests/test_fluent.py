from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from wechat_context_exporter.ui import fluent as fl
from wechat_context_exporter.ui import native_theme


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def light(monkeypatch):
    monkeypatch.setattr(native_theme, "_OVERRIDE", "light")
    monkeypatch.setattr(native_theme, "system_accent", lambda: None)
    return native_theme.active()


@pytest.fixture
def dark(monkeypatch):
    monkeypatch.setattr(native_theme, "_OVERRIDE", "dark")
    monkeypatch.setattr(native_theme, "system_accent", lambda: None)
    return native_theme.active()


def render_appearance(width: int, height: int, paint) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(native_theme.active().color("window"))
    painter = QPainter(pixmap)
    paint(painter)
    painter.end()
    return pixmap


def test_light_palette_matches_winui(light):
    assert light.window == "#F3F3F3"
    assert light.surface == "#FFFFFF"
    assert light.border == "#E5E5E5"
    assert light.text == "#1B1B1B"


def test_dark_palette_is_symmetric(dark):
    assert dark.window == "#202020"
    assert dark.surface == "#2B2B2B"
    assert dark.text == "#FFFFFF"


def test_scheme_follows_the_override(monkeypatch):
    monkeypatch.setattr(native_theme, "_OVERRIDE", "dark")
    assert native_theme.system_is_dark() is True
    monkeypatch.setattr(native_theme, "_OVERRIDE", "light")
    assert native_theme.system_is_dark() is False


def test_accent_comes_from_the_theme(monkeypatch):
    from PySide6.QtGui import QColor

    monkeypatch.setattr(native_theme, "_OVERRIDE", "light")
    monkeypatch.setattr(native_theme, "system_accent", lambda: QColor("#C239B3"))
    assert native_theme.active().accent == "#c239b3"
    assert native_theme.accent_qcolor().name() == "#c239b3"
    # #C239B3 is dark enough that Fluent puts white text on it.
    assert native_theme.active().accent_text == "#FFFFFF"


def test_surface_is_filled_and_stroked(app, light):
    pixmap = render_appearance(
        200,
        80,
        lambda painter: fl.paint_surface(painter, QRectF(0, 0, 200, 80), fl.ROUND_CARD),
    )
    image = pixmap.toImage()
    assert image.pixelColor(100, 40).name() == light.surface.lower()
    # The 1px stroke lands in the first pixel column.
    assert image.pixelColor(0, 40).name() == light.border.lower()


def test_well_uses_the_alternate_surface(app, light):
    pixmap = render_appearance(
        200, 80, lambda painter: fl.paint_well(painter, QRectF(0, 0, 200, 80))
    )
    assert pixmap.toImage().pixelColor(100, 40).name() == "#f9f9f9"


def test_field_paints_a_border_and_grows_no_shadow(app, light):
    field = fl.SoftLineEdit()
    field.resize(180, 32)
    field.setText("hello")
    image = field.grab().toImage()

    assert field.height() == fl.CONTROL_HEIGHT
    assert image.pixelColor(90, 16).name() == light.surface.lower()
    assert image.pixelColor(0, 16).name() == light.border_strong.lower()


def test_field_focus_draws_the_accent_underline(app, light):
    field = fl.SoftLineEdit()
    field.resize(180, 32)
    field.show()
    field.setFocus()
    app.processEvents()

    image = field.grab().toImage()
    underline = image.pixelColor(90, 31)
    assert underline.name() == light.accent.lower()
