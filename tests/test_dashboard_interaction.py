"""Interaction and packaging regression tests for GlassDashboardWindow.

Two things are covered here that previously had no protection at all:

1. Edge resizing on the frameless window (it had no resize support, and on
   Windows it cannot use WM_NCHITTEST because the window carries no
   WS_THICKFRAME).
2. The packaging import graph: ``app.py`` is the PyInstaller entry, so the
   glass dashboard must stay reachable from it or it silently drops out of the
   built exe.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from wechat_context_exporter.ui.dashboard_window import (  # noqa: E402
    BLUR_DOWNSCALE,
    BLUR_RADIUS,
    RESIZE_BOTTOM,
    RESIZE_LEFT,
    RESIZE_RIGHT,
    RESIZE_TOP,
    GlassDashboardWindow,
)

BACKDROP_ASSET = (
    PROJECT_ROOT / "src" / "wechat_context_exporter" / "assets" / "glass_background.jpg"
)

DEMO_JSON = str(PROJECT_ROOT / "examples" / "demo_chat.json")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setOrganizationName("WBGlassDashboardTest")
    app.setApplicationName("WBGlassDashboardTest")
    return app


def _make_window() -> GlassDashboardWindow:
    _app()
    window = GlassDashboardWindow(demo_json=DEMO_JSON)
    window.resize(1340, 890)
    window.show()
    return window


def _mouse(window, event_type, x, y, buttons, button=Qt.MouseButton.LeftButton):
    local = QPointF(x, y)
    glob = QPointF(window.mapToGlobal(QPoint(int(x), int(y))))
    return QMouseEvent(event_type, local, glob, button, buttons,
                       Qt.KeyboardModifier.NoModifier)


# --------------------------------------------------------------------------
# edge hit detection (pure logic)
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# actual resizing through synthesized mouse events
# --------------------------------------------------------------------------




# --------------------------------------------------------------------------
# backdrop rebuild strategy
# --------------------------------------------------------------------------



# --------------------------------------------------------------------------
# edge events must survive the central widget (propagation guard)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# packaging guard
# --------------------------------------------------------------------------
def test_packaging_entry_reaches_glass_dashboard() -> None:
    """``app.py`` is the PyInstaller entry for both specs.

    PyInstaller collects only what is reachable from that file's import graph,
    so if this wiring is ever broken the glass dashboard will silently be
    absent from the built exe again -- with no error anywhere.

    Deliberately a static source check.  An earlier version popped these
    modules from sys.modules and re-imported them, which produced a *second*
    dashboard_window module object; classes from the first one then kept
    writing to the real registry while the test isolation sat on the second.
    """
    entry_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "from wechat_context_exporter.ui.launch import main" in entry_source, (
        "app.py must import the shared launcher so both windows are collected"
    )

    launch_source = (
        PROJECT_ROOT / "src" / "wechat_context_exporter" / "ui" / "launch.py"
    ).read_text(encoding="utf-8")
    assert "from .dashboard_window import GlassDashboardWindow" in launch_source, (
        "launch.py must statically import the glass window"
    )
    assert "from .main_window import" in launch_source, (
        "launch.py must statically import the classic window"
    )

    # the graph must also resolve at runtime
    import wechat_context_exporter.ui.launch  # noqa: F401

    for module_name in (
        "wechat_context_exporter.ui.dashboard_window",
        "wechat_context_exporter.ui.glass_widgets",
        "wechat_context_exporter.ui.main_window",
    ):
        assert module_name in sys.modules, module_name


# --------------------------------------------------------------------------
# settings persistence
# --------------------------------------------------------------------------
def test_dashboard_geometry_is_persisted() -> None:
    """A second window must come back at the size the first one was left at.

    Constructed directly rather than through _make_window(), which forces a
    fixed size and would mask a restore failure.
    """
    _app()

    first = GlassDashboardWindow(demo_json=DEMO_JSON)
    first.resize(1420, 940)
    first.show()
    first.close()

    second = GlassDashboardWindow(demo_json=DEMO_JSON)
    assert (second.width(), second.height()) == (1420, 940), second.size()
    second.close()


def test_settings_are_isolated_from_the_real_store() -> None:
    """Guard the guard: the suite must never touch the user's real QSettings.

    GlassDashboardWindow writes outputPath/dashboardGeometry, and its store is
    QSettings("LocalTools", "WeChatContextExporter") -- the user's actual
    registry key on Windows.  If tests/conftest.py stops redirecting it, this
    test fails instead of silently rewriting the user's configuration.
    """
    from PySide6.QtCore import QSettings

    window = _make_window()
    file_name = window._settings.fileName()
    window.close()

    assert "HKEY_CURRENT_USER" not in file_name, file_name
    assert window._settings.format() == QSettings.Format.IniFormat


# --------------------------------------------------------------------------
# export must actually work
# --------------------------------------------------------------------------
def test_export_button_produces_a_pdf(tmp_path, monkeypatch) -> None:
    """Drive the real export click path.

    This window used to build ExportOptions with invented keyword names
    (output_pdf_path / keyword / start_date / ...), so clicking export raised
    TypeError -- the app's core feature was dead in the new UI.  Rendering
    tests never noticed because they never pressed the button.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    window = _make_window()
    for _ in range(80):
        QApplication.processEvents()

    assert window._source is not None, "demo JSON did not load"
    assert window._filtered_messages, "no messages available to export"

    target = tmp_path / "memory.pdf"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(target), "PDF 文件 (*.pdf)")),
    )
    # the success path shows a modal dialog, which would block the test
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    window._on_export_clicked()

    deadline = time.time() + 120
    while time.time() < deadline:
        worker = window._active_worker
        if worker is None or not worker.isRunning():
            break
        QApplication.processEvents()
        time.sleep(0.05)
    for _ in range(60):
        QApplication.processEvents()

    assert target.exists(), "export produced no PDF"
    assert target.stat().st_size > 1000, target.stat().st_size
    window.close()


def test_export_options_match_the_service_dataclass(monkeypatch) -> None:
    """Cheap guard: the keywords the dashboard passes must exist on
    ExportOptions, so a rename in service.py fails here rather than at click."""
    import inspect

    from wechat_context_exporter.service import ExportOptions

    valid = set(inspect.signature(ExportOptions).parameters)
    required = {
        "conversation_id",
        "output_pdf",
        "start",
        "end",
        "include_image_pages",
        "pages_dir",
        "markdown_path",
        "json_path",
        "query",
    }
    assert required <= valid, f"missing from ExportOptions: {sorted(required - valid)}"

    source = inspect.getsource(GlassDashboardWindow._on_export_clicked)
    for name in required:
        assert f"{name}=" in source, f"_on_export_clicked does not pass {name}="


def test_remembered_output_path_is_only_restored_when_usable(tmp_path) -> None:
    """A path left behind by the test suite must not become the user's default.

    pytest writes into the OS temp directory; that path survives the folder, so
    restoring it would point the export button at somewhere that no longer exists.
    """
    from wechat_context_exporter.ui.dashboard_window import GlassDashboardWindow

    # tmp_path itself lives under the OS temp directory, so the "usable" case
    # has to be a real folder outside it.
    assert GlassDashboardWindow._restorable_output(str(Path.cwd() / "keep.pdf")) is True

    leftover = Path(tempfile.gettempdir()) / "pytest-of-someone" / "out.pdf"
    assert GlassDashboardWindow._restorable_output(str(leftover)) is False

    assert GlassDashboardWindow._restorable_output(str(tmp_path / "gone" / "out.pdf")) is False
