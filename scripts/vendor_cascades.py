#!/usr/bin/env python3
"""Fetch OpenCV Haar cascade XML files into resources/cascades.

The ``opencv-python-headless`` wheels do not ship the cascade data files, so CLIPOS
vendors them.  They are fetched once at build time and then work fully offline.

    python scripts/vendor_cascades.py
"""
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "resources" / "cascades"

CASCADES = {
    "haarcascade_frontalface_default.xml":
        "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml",
    "haarcascade_frontalface_alt2.xml":
        "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_alt2.xml",
    "haarcascade_profileface.xml":
        "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_profileface.xml",
    "haarcascade_upperbody.xml":
        "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_upperbody.xml",
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, url in CASCADES.items():
        target = DEST / name
        if target.exists() and target.stat().st_size > 1000:
            print(f"  [skip] {name}")
            ok += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "clipos-builder"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            target.write_bytes(data)
            print(f"  [get ] {name} ({len(data) // 1024} KB)")
            ok += 1
        except Exception as exc:
            print(f"  [fail] {name}: {exc}")
    print(f"{ok}/{len(CASCADES)} cascades available in {DEST}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
