"""AI Clipper Pro — local-first AI video studio backend."""
from __future__ import annotations

import json
from pathlib import Path

FALLBACK_VERSION = "6.0.1"


def _package_version() -> str:
    """Read the app version from package.json when it is available."""
    for candidate in (
        Path(__file__).resolve().parents[2] / "package.json",
        Path(getattr(__import__("sys"), "_MEIPASS", ".")) / "package.json",
    ):
        try:
            return json.loads(candidate.read_text(encoding="utf-8")).get("version", FALLBACK_VERSION)
        except Exception:
            continue
    return FALLBACK_VERSION


__version__ = _package_version()
