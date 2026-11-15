from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def isolated_app_state(tmp_path, monkeypatch):
    """Keep the suite out of the user's real job history and scene file.

    The GUI records every export as a job; without this, running the tests would
    append to ``%LOCALAPPDATA%\\WeChatAIMemory\\jobs`` on the developer's machine.
    The override is an environment variable rather than a monkeypatched function
    so it also covers modules that imported ``default_jobs_dir`` directly.
    """
    monkeypatch.setenv("WECHAT_AI_MEMORY_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("WECHAT_AI_MEMORY_SCENES_FILE", str(tmp_path / "scenes.json"))
    monkeypatch.setenv("WECHAT_AI_MEMORY_OUTPUT_DIR", str(tmp_path / "archive"))


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path, monkeypatch):
    """Keep the test suite out of the user's real configuration.

    Both windows use ``QSettings("LocalTools", "WeChatContextExporter")`` --
    which on Windows is the user's actual registry-backed settings -- and
    GlassDashboardWindow writes ``outputPath`` on export and
    ``dashboardGeometry`` on close.  Running the suite must not rewrite those.

    Two things are worth knowing here:

    * ``QSettings.setDefaultFormat(Format.IniFormat)`` does NOT redirect this.
      Measured on this machine, ``QSettings(org, app)`` still reports
      ``Format.NativeFormat`` and keeps pointing at
      ``\\HKEY_CURRENT_USER\\Software\\...`` even after setDefaultFormat() and
      setPath() are called.  Substituting the name is the only reliable way.

    * The substitution is applied to every loaded module whose name ends in
      ``ui.dashboard_window`` / ``ui.main_window``, not just the one obtained
      via import.  If a test ever re-imports one of those modules, a second
      module object exists, and a class from the first one would keep writing
      to the registry while the patch sat on the second.

    * ``PySide6.QtCore.QSettings`` itself is patched as well.  Without that,
      running a single non-UI test file would fail: the UI modules are imported
      lazily by the tests that need them, so the module-level patch above finds
      nothing to patch and an ``assert patched`` guard would abort every
      CLI/service test.  Patching the attribute on the Qt module covers any UI
      module imported after this fixture runs.
    """
    from PySide6 import QtCore
    from PySide6.QtCore import QSettings as RealQSettings

    ini_path = str(tmp_path / "qsettings.ini")

    class IsolatedQSettings(RealQSettings):
        """A ``QSettings`` that always points at this test's ini file.

        Subclassing instead of returning a different object keeps ``isinstance``
        checks, ``QSettings.Format``, and any other class attribute working, so
        code that introspects the class still behaves like production.
        """

        def __init__(self, *args, **kwargs):
            super().__init__(ini_path, RealQSettings.Format.IniFormat)

    monkeypatch.setattr(QtCore, "QSettings", IsolatedQSettings, raising=False)

    suffixes = ("ui.dashboard_window", "ui.main_window")
    for name, module in list(sys.modules.items()):
        if module is not None and name.endswith(suffixes):
            monkeypatch.setattr(module, "QSettings", IsolatedQSettings, raising=False)

    yield
