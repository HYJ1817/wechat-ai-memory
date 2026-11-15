"""Shared application launcher for every entry point.

Why this module exists
----------------------
PyInstaller bundles only the modules reachable from the *entry script's* import
graph.  Both specs (``packaging/windows/*.spec``) use ``app.py`` as the entry,
and ``app.py`` previously imported ``main_window`` only -- so
``dashboard_window`` / ``glass_widgets`` were never collected and the glass
dashboard silently did not ship in the built exe.

Both windows are therefore imported here, and ``app.py`` imports this module.
Do not move these imports behind a function in a way that hides them from
static analysis, and keep ``hiddenimports=[]`` in the specs valid.

Usage
-----
    python app.py              -> glass dashboard (default)
    python app.py --classic    -> classic main window
    python app.py <file.json>  -> glass dashboard, loading a JSON archive
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ..rendering.fonts import FontBook
from .dashboard_window import GlassDashboardWindow
from .main_window import APP_ID, APP_NAME, MainWindow, application_icon

# Which UI a bare launch gets.  Flip to "classic" to make the old window the
# default again without touching the entry scripts.
# The modern dashboard is neumorphic now, not glass; the value is kept short
# because it is only ever compared against this constant.
DEFAULT_UI = "modern"


def _find_json_argument(argv: Sequence[str]) -> str | None:
    for argument in argv[1:]:
        if argument.endswith(".json") and Path(argument).is_file():
            return argument
    return None


def _build_application(argv: Sequence[str]) -> QApplication:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    app = QApplication(list(argv))
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("LocalTools")
    app.setWindowIcon(application_icon())
    app.setStyle("Fusion")

    try:
        font_id = QFontDatabase.addApplicationFont(str(FontBook.discover().regular_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    except RuntimeError:
        pass

    return app


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    use_classic = "--classic" in arguments or "-c" in arguments
    demo_json = _find_json_argument(arguments)

    app = _build_application(arguments)

    if use_classic:
        window = MainWindow()
    elif DEFAULT_UI == "modern":
        window = GlassDashboardWindow(demo_json=demo_json)
    else:
        window = MainWindow()

    window.show()
    return app.exec()
