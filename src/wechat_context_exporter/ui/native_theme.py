"""Design tokens for the neumorphic surface.

Neumorphism has exactly one surface colour: the page and every element share it,
and depth comes only from a fixed light source at the top left.  That constraint
is what makes a dark variant impossible -- on a dark backdrop there is no room
between "lit" and "shadowed" for the material to read -- so the app is light-only
by design, not by oversight.  ``system_is_dark()`` therefore reports False and is
kept only so callers do not have to special-case its absence.

Everything downstream reads these tokens: ``glass_widgets`` (the hand-painted
cards, buttons, and toggles) and the stylesheet rewrite in :func:`themed_qss`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtGui import QColor

from . import neumorphic


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


# Surface and window are deliberately the same value: any difference would break
# the illusion that elements are extruded from the page rather than stacked on it.
NEUMORPHIC = Palette(
    name="neumorphic",
    window=neumorphic.BASE.name(),
    surface=neumorphic.BASE.name(),
    surface_alt=neumorphic.BASE.name(),
    border=neumorphic.BASE.name(),
    border_strong="#cfd5de",
    text=neumorphic.TEXT.name(),
    text_muted=neumorphic.TEXT_MUTED.name(),
    text_faint=neumorphic.TEXT_FAINT.name(),
    accent=neumorphic.BLURPLE.name(),
    accent_text="#ffffff",
    hover="#e6ebf2",
    pressed="#d7dde5",
    divider="#d3d9e1",
)


def system_is_dark() -> bool:
    """Always light: the neumorphic material needs a light backdrop to exist."""
    return False


def active() -> Palette:
    return NEUMORPHIC


def ink(alpha: int = 255) -> QColor:
    """Text / line colour at the given alpha.

    Callers use alpha to build hierarchy (solid primary text, muted secondary,
    faint hairlines); mapping all of it onto one warm-grey keeps that hierarchy
    while matching the palette.
    """
    colour = QColor(neumorphic.TEXT)
    colour.setAlpha(alpha)
    return colour


def ink_rgba(alpha: int) -> str:
    colour = ink(alpha)
    return "rgba(%d, %d, %d, %d)" % (colour.red(), colour.green(), colour.blue(), alpha)


def accent_qcolor(alpha: int = 255) -> QColor:
    colour = QColor(neumorphic.BLURPLE)
    colour.setAlpha(alpha)
    return colour


def accent_rgba(alpha: int = 255) -> str:
    colour = accent_qcolor(alpha)
    return "rgba(%d, %d, %d, %d)" % (colour.red(), colour.green(), colour.blue(), alpha)


# Text written for the old light-on-dark UI used ``rgba(255,255,255,a)`` as its
# ink hierarchy; invert those to the palette's ink while keeping alpha.
_INK_QSS = re.compile(r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(\d+)\s*\)")
# Panels used the same triple with low alpha as a translucent wash.  On a
# same-colour page that reads as a grey fill, which neumorphism forbids, so those
# become transparent and let the painted material show through instead.
_WASH_MAX_ALPHA = 60
_WASH_QSS = re.compile(r"(background(?:-color)?\s*:\s*)rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(\d+)\s*\)")
_WARM_QSS = re.compile(r"rgba\(\s*255\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d+)\s*\)")


def _wash_to_transparent(match: re.Match) -> str:
    alpha = int(match.group(2))
    if alpha <= _WASH_MAX_ALPHA:
        return f"{match.group(1)}transparent"
    return match.group(0)


def _warm_to_accent(match: re.Match) -> str:
    green, blue, alpha = (int(match.group(i)) for i in (1, 2, 3))
    if green >= 150 and blue <= 210:
        return accent_rgba(alpha)
    return match.group(0)


def themed_qss(qss: str) -> str:
    """Rewrite light-on-dark colour literals for the neumorphic surface.

    A runtime string rewrite, not an f-string: Qt stylesheets are full of braces,
    so templating them would mean escaping every rule and would break the first
    time someone edited one.
    """
    qss = _WASH_QSS.sub(_wash_to_transparent, qss)
    qss = _INK_QSS.sub(lambda match: ink_rgba(int(match.group(1))), qss)
    return _WARM_QSS.sub(_warm_to_accent, qss)
