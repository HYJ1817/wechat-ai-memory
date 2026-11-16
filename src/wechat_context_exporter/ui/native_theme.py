"""WinUI 3 tokens: Mica-neutral surfaces, system accent, light and dark.

The app is Windows-only, so the visual language follows the shell it lives in:
the window colour is the Mica base, content sits on a white (or #2B2B2B) layer,
and every separation is a 1px stroke rather than a shadow.

Two values are read from the OS instead of being hard-coded:

* ``AppsUseLightTheme`` decides light or dark.
* ``AccentColor`` (stored ABGR under ``HKCU\\...\\DWM``) drives selection, focus
  and the primary button, so changing the accent in Windows Settings changes the
  app.

``WAM_UI_THEME=light|dark`` overrides the scheme for tests and offscreen renders.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace

from PySide6.QtGui import QColor

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_DWM = r"Software\Microsoft\Windows\DWM"
_OVERRIDE = os.environ.get("WAM_UI_THEME", "").strip().lower()


@dataclass(frozen=True, slots=True)
class Palette:
    name: str
    window: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_text: str
    hover: str
    pressed: str
    divider: str

    def color(self, role: str) -> QColor:
        return QColor(getattr(self, role))


LIGHT = Palette(
    name="light",
    window="#F3F3F3",
    surface="#FFFFFF",
    surface_alt="#F9F9F9",
    border="#E5E5E5",
    border_strong="#D6D6D6",
    text="#1B1B1B",
    text_muted="#5D5D5D",
    text_faint="#8A8A8A",
    accent="#005FB8",
    accent_text="#FFFFFF",
    hover="#F5F5F5",
    pressed="#EDEDED",
    divider="#EBEBEB",
)

DARK = Palette(
    name="dark",
    window="#202020",
    surface="#2B2B2B",
    surface_alt="#323232",
    border="#3A3A3A",
    border_strong="#474747",
    text="#FFFFFF",
    text_muted="#C5C5C5",
    text_faint="#9A9A9A",
    accent="#60CDFF",
    accent_text="#003B5C",
    hover="#333333",
    pressed="#292929",
    divider="#383838",
)


def _registry_value(path: str, name: str):
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        try:
            return winreg.QueryValueEx(key, name)[0]
        finally:
            key.Close()
    except (ImportError, OSError, ValueError):
        return None


def system_is_dark() -> bool:
    if _OVERRIDE == "dark":
        return True
    if _OVERRIDE == "light":
        return False
    value = _registry_value(_PERSONALIZE, "AppsUseLightTheme")
    # An absent key means a fresh profile; Windows ships light by default.
    return False if value is None else value == 0


def system_accent() -> QColor | None:
    """The user's accent colour, stored ABGR (0xAABBGGRR)."""
    value = _registry_value(_DWM, "AccentColor")
    if value is None:
        return None
    return QColor(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)


def _accent_text_for(colour: QColor) -> str:
    luminance = (0.299 * colour.red() + 0.587 * colour.green() + 0.114 * colour.blue()) / 255.0
    return "#FFFFFF" if luminance < 0.55 else "#101010"


def active() -> Palette:
    palette = DARK if system_is_dark() else LIGHT
    accent = system_accent()
    if accent is None or not accent.isValid():
        return palette
    return replace(palette, accent=accent.name(), accent_text=_accent_text_for(accent))


def ink(alpha: int = 255) -> QColor:
    colour = QColor(active().text)
    colour.setAlpha(alpha)
    return colour


def ink_rgba(alpha: int) -> str:
    colour = ink(alpha)
    return "rgba(%d, %d, %d, %d)" % (colour.red(), colour.green(), colour.blue(), alpha)


def accent_qcolor(alpha: int = 255) -> QColor:
    colour = QColor(active().accent)
    colour.setAlpha(alpha)
    return colour


def accent_rgba(alpha: int = 255) -> str:
    colour = accent_qcolor(alpha)
    return "rgba(%d, %d, %d, %d)" % (colour.red(), colour.green(), colour.blue(), alpha)


# Stylesheets written for the dark-only builds used white ink; on a light palette
# that is invisible, so the alpha is preserved and the colour inverted.
_INK_QSS = re.compile(r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(\d+)\s*\)")
_WARM_QSS = re.compile(r"rgba\(\s*255\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d+)\s*\)")


def _warm_to_accent(match: re.Match) -> str:
    green, blue, alpha = (int(match.group(i)) for i in (1, 2, 3))
    if green >= 150 and blue <= 210:
        return accent_rgba(alpha)
    return match.group(0)


def themed_qss(qss: str) -> str:
    if active().name == "light":
        qss = _INK_QSS.sub(lambda match: ink_rgba(int(match.group(1))), qss)
    return _WARM_QSS.sub(_warm_to_accent, qss)
