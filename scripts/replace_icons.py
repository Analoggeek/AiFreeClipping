#!/usr/bin/env python3
"""Replace emoji icons in the UI source with geometric glyphs.

Emoji coverage varies wildly between platforms (and is absent in many minimal
Linux font sets), which makes icons render as tofu boxes.  The replacements below
all live in the Basic Multilingual Plane and are present in DejaVu Sans, which
ships with virtually every system -- so the UI looks identical everywhere.
"""
from __future__ import annotations

import pathlib
import re

REPLACEMENTS = {
    # Emoji -> geometric symbol
    "🎬": "◧",   # film frames
    "✂": "✂",   # scissors (already geometric, keep)
    "⤓": "↓",   # download arrow
    "💾": "▤",   # storage
    "🖥": "▣",   # computer
    "🧠": "◍",   # memory
    "🎮": "◆",   # gpu
    "⚡": "◈",   # acceleration
    "🔒": "▣",   # lock
    "🔗": "↗",   # link
    "⬇": "↓",   # down arrow
    "⬆": "↑",
    "🎨": "◐",
    "📁": "▣",
    "📦": "▣",
    "🔥": "▲",
    "⭐": "★",
    "✅": "✓",
    "❌": "✕",
    "⏱": "◷",
    "⌛": "◷",
    "⏳": "◷",
    "🔍": "⌕",
    "🎯": "◎",
    "🏆": "★",
    "🤖": "◈",
    "💡": "✧",
    "🔧": "⚙",
    "📊": "▥",
    "📈": "▥",
    "🎙": "◉",
    "🎵": "♪",
    "🅿": "P",
    "🅰": "A",
    "⚠": "⚠",
    "⚠️": "⚠",
    "🔔": "◔",
    "🕐": "◷",
}

# Navigation / label glyphs that are already safe but should be normalised
SAFE_NAV = {
    "⌂": "⌂",  # house
    "✦": "✦",  # star
    "▤": "▤",  # list
    "▶": "▶",  # play
    "◫": "◫",  # panels
    "☰": "☰",  # lines
    "◈": "◈",  # diamond
    "⚙": "⚙",  # gear
    "⭳": "↓",
    "↻": "↻",
    "→": "→",
}


def apply(path: pathlib.Path) -> int:
    text = path.read_text(encoding="utf-8")
    original = text
    changed = 0
    for old, new in REPLACEMENTS.items():
        if old in text:
            changed += text.count(old)
            text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1] / "clipos"
    total = 0
    for p in root.rglob("*.py"):
        total += apply(p)
    print(f"replaced {total} emoji glyphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
