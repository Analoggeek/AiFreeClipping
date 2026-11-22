"""Locate the bundled resources in every installation layout.

CLIPOS ships its FFmpeg binaries, face cascades, face models, icons and sound
effects inside the application bundle.  Depending on how the app is installed
those files live in one of three places:

* a frozen PyInstaller bundle -- under ``sys._MEIPASS``;
* an installed package -- next to the ``clipos`` package directory;
* a source checkout -- at the repository root.

Every module that needs a bundled asset should call :func:`resource_dir`
instead of walking up the filesystem itself.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Sub-directories that hold bundled assets.
RESOURCE_SUBDIRS = ("ffmpeg", "cascades", "models", "icons", "sounds", "templates")


def _candidate_roots() -> list[Path]:
    """Every place the bundled resources might live, most specific first."""
    roots: list[Path] = []

    # 1. A frozen PyInstaller bundle.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))

    # 2. An explicit override (used by the app entry point and by tests).
    env = os.environ.get("CLIPOS_RESOURCES")
    if env:
        roots.append(Path(env))

    # 3. The repository / installation root, found by walking up from this file.
    here = Path(__file__).resolve()
    for parent in here.parents:
        roots.append(parent)

    return roots


def resource_dir(name: str) -> Path:
    """Return the directory holding the bundled resource called ``name``.

    The returned path always exists when the app is packaged correctly; when
    it cannot be found the path is still returned so callers can report a
    helpful error instead of crashing.
    """
    for root in _candidate_roots():
        # Resources may sit directly under the root, or one level down when
        # CLIPOS_RESOURCES points at the "resources" directory itself.
        for candidate in (root / "resources" / name, root / name):
            if candidate.exists():
                return candidate
    # Fall back to the most likely location so error messages are useful.
    return Path(__file__).resolve().parents[2] / "resources" / name


def resource_file(*parts: str) -> Path:
    """Return the path of a bundled file, e.g. ``resource_file("sounds", "pop.wav")``."""
    return resource_dir(parts[0]).joinpath(*parts[1:])


def has_resource(name: str) -> bool:
    """True when the named bundled resource directory is present."""
    return resource_dir(name).exists()
