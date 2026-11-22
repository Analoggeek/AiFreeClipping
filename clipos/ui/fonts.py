"""Font discovery and registration for CLIPOS.

Desktop systems expose fonts through the OS font service, which Qt finds
automatically.  Minimal container images sometimes have fonts on disk but no
usable fontconfig cache, leaving Qt with zero families.  This module registers
font files directly with Qt in that case so the UI is never rendered with
tofu boxes.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFontDatabase

log = logging.getLogger(__name__)

_FONT_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/System/Library/Fonts",          # macOS
    "/Library/Fonts",                 # macOS
    "C:/Windows/Fonts",               # Windows
]

# Families we want available for captions, in order of preference.
CAPTION_FONT_CANDIDATES = [
    "Inter", "SF Pro Display", "Helvetica Neue", "Segoe UI", "Roboto",
    "DejaVu Sans", "Liberation Sans", "Arial", "Noto Sans",
]

_registered = False


def _font_files() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for d in _FONT_DIRS:
        base = Path(d)
        if not base.exists():
            continue
        try:
            for ext in ("ttf", "otf", "ttc"):
                for f in base.rglob(f"*.{ext}"):
                    key = str(f)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(f)
        except (OSError, PermissionError):
            continue
    return out


def ensure_fonts() -> list[str]:
    """Make sure Qt has at least one usable font family. Returns family names."""
    global _registered
    if _registered:
        return QFontDatabase.families()

    families = QFontDatabase.families()
    if families:
        _registered = True
        return families

    log.info("no font families registered; loading font files directly")
    loaded: list[str] = []
    for path in _font_files():
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid != -1:
            loaded.extend(QFontDatabase.applicationFontFamilies(fid))
    families = QFontDatabase.families()
    log.info("registered %d font families from disk", len(families))
    _registered = True
    return families


def available_families() -> list[str]:
    """Sorted list of font families for the caption font picker."""
    ensure_fonts()
    try:
        return sorted(set(QFontDatabase.families()))
    except Exception:
        return []


def pick_caption_font() -> str:
    """Choose the best available caption font for this system."""
    families = set(available_families())
    for candidate in CAPTION_FONT_CANDIDATES:
        if candidate in families:
            return candidate
    return "DejaVu Sans" if "DejaVu Sans" in families else (
        families.pop() if families else "Sans Serif"
    )


def font_file_for(family: str) -> str | None:
    """Find a TTF/OTF file on disk for a family (used for ASS rendering)."""
    for path in _font_files():
        try:
            if family.lower() in path.stem.lower().replace(" ", ""):
                return str(path)
        except Exception:
            continue
    return None
