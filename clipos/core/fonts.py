"""Font discovery for FFmpeg.

FFmpeg's ``drawtext`` filter has to be told which font file to use.  Some
builds ship a compiled-in default, but others -- the macOS builds in
particular -- do not, and the filter then stops with

    No font filename provided

The ``ass`` filter has the same problem in a different way: it looks for
the fonts named in the subtitle file in the system font directories, and
falls back to a default that may not exist either.

This module finds a real font file on every platform, so the renderer can
always pass an explicit ``fontfile=`` and a ``fontsdir=``.
"""
from __future__ import annotations

import os
import hashlib
import tempfile
from pathlib import Path

from .logging_setup import get_logger

log = get_logger(__name__)

# Directories that hold real font files on each platform.  The order
# matters: the first match is the one that is used.
_FONT_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/System/Library/Fonts",          # macOS
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",                 # macOS
    os.environ.get("WINDIR", "C:/Windows") + "/Fonts",
    "/Windows/Fonts",
]

# Fonts we would rather use, in order of preference.  The first one that
# is actually on disk wins.
_PREFERRED = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "Arial Bold.ttf",
    "arialbd.ttf",
    "Arial.ttf",
    "arial.ttf",
    "Helvetica.ttc",
    "Helvetica.ttc",
    "SFNSDisplay.ttf",
    "Verdana.ttf",
    "verdana.ttf",
    "LiberationSans-Regular.ttf",
    "NotoSans-Regular.ttf",
]

# A last resort: any font file at all in a known directory.
_FALLBACK_GLOBS = ("*.ttf", "*.otf", "*.ttc")

# Cached so that a long render does not walk the font directories again
# and again.
_resolved: Path | None = None
_resolved_dir: Path | None = None
_looked = False


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    for raw in _FONT_DIRS:
        if not raw:
            continue
        path = Path(raw)
        try:
            if path.is_dir():
                dirs.append(path)
        except OSError:
            continue
    return dirs


def find_font_file() -> Path | None:
    """Return a usable font file, or ``None`` if the system has none."""
    global _resolved, _looked
    if _looked:
        return _resolved
    _looked = True

    dirs = _candidate_dirs()

    # The preferred fonts first -- they are known to render legibly.
    for name in _PREFERRED:
        for base in dirs:
            try:
                candidate = base / name
                if candidate.is_file():
                    _resolved = candidate
                    return _resolved
            except OSError:
                continue

    # Then anything at all.  The directories are walked a few levels deep
    # because the fonts on a Linux machine usually sit in a subdirectory
    # such as /usr/share/fonts/truetype/dejavu.
    for base in dirs:
        for pattern in _FALLBACK_GLOBS:
            try:
                found = sorted(base.rglob(pattern))
            except OSError:
                continue
            if found:
                _resolved = found[0]
                return _resolved

    log.warning("no font file found on this system")
    return None


def font_dir() -> Path | None:
    """An isolated font staging directory, NEVER the whole OS font library.

    libass imports every file in fontsdir before using its platform provider.
    On macOS that unnecessarily parsed supplemental collections (including the
    NISC18030 metadata warning in the reported crash). Keep system discovery to
    CoreText; explicitly import only our single fallback font.
    """
    global _resolved_dir
    if _resolved_dir is not None and _resolved_dir.is_dir():
        return _resolved_dir
    font=find_font_file()
    if font is None:return None
    try:
        if not 0<font.stat().st_size<=64*1024*1024:return None
        content=font.read_bytes()
        if content[:4] not in (b'\x00\x01\x00\x00',b'OTTO',b'ttcf',b'true'):return None
        from .config import PATHS
        directory=PATHS.cache/'ffmpeg-fonts'/hashlib.sha256(content).hexdigest()[:24]
        directory.mkdir(parents=True,exist_ok=True)
        target=directory/('fallback'+font.suffix.lower())
        if not target.exists() or target.read_bytes()!=content:
            fd,name=tempfile.mkstemp(prefix='.font-',dir=directory)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(content)
                os.replace(name,target)
            finally:Path(name).unlink(missing_ok=True)
        _resolved_dir=directory
        return directory
    except OSError as exc:
        log.warning('Isolated caption font unavailable; using OS provider only: %s',exc)
        return None


def drawtext_font_args() -> str:
    """The ``fontfile=`` argument for the ``drawtext`` filter.

    An empty string when no font could be found, which lets the filter
    use its own default rather than failing on a missing argument.
    """
    font = find_font_file()
    if font is None:
        return ""
    escaped = _escape_font_path(font)
    # The trailing colon separates this argument from the next one.
    return f"fontfile='{escaped}':"


def fontsdir_arg() -> str:
    """The ``fontsdir=`` argument for the ``ass`` filter."""
    base = font_dir()
    if base is None:
        return ""
    escaped = _escape_font_path(base)
    # The trailing colon separates this argument from the next one.
    return f"fontsdir='{escaped}':"


def _escape_font_path(path):
    value=str(path).replace('\\','/')
    for char in (':',"'",'[',']',','):
        value=value.replace(char,'\\'+char)
    return value
