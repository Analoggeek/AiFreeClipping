#!/usr/bin/env python3
"""Generate the platform icon files from resources/icons/app_icon.png.

Produces:
    resources/icons/app_icon.png    (1024x1024 master, committed)
    resources/icons/app_icon.ico    (Windows, multi-resolution)
    resources/icons/app_icon.icns   (macOS)
    resources/icons/app_icon_512.png

Run this after changing the master image:

    python scripts/make_icons.py
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "resources" / "icons"
MASTER = ICONS / "app_icon.png"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_TYPES = [
    (16, "icp4"), (32, "icp5"), (64, "icp6"), (128, "ic07"),
    (256, "ic08"), (512, "ic09"), (1024, "ic10"),
]


def load_master() -> "PILImage.Image":  # type: ignore[name-defined]
    from PIL import Image

    img = Image.open(MASTER).convert("RGBA")
    if img.size != (1024, 1024):
        img = img.resize((1024, 1024), Image.LANCZOS)
    return img


def png_bytes(img, size: int) -> bytes:
    """Encode a PIL image as PNG bytes at the requested size."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    img.resize((size, size), Image.LANCZOS).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_png_bytes(img, size: int) -> bytes:
    return png_bytes(img, size)


def write_ico(img) -> Path:
    """Write a multi-resolution .ico file by hand (no Pillow needed)."""
    out = ICONS / "app_icon.ico"
    header = struct.pack("<HHH", 0, 1, len(ICO_SIZES))
    offset = 6 + 16 * len(ICO_SIZES)
    entries = []
    blobs = []
    for size in ICO_SIZES:
        # PNG-compressed entries are accepted by Windows for every size.
        data = png_bytes(img, size)
        # In the ICO directory, width/height are single bytes and 0 means 256.
        dim = 0 if size >= 256 else size
        entries.append((dim, dim, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)

    with out.open("wb") as fh:
        fh.write(header)
        for e in entries:
            fh.write(struct.pack("<BBBBHHII", *e))
        for blob in blobs:
            fh.write(blob)
    return out


def write_icns(img) -> Path:
    """Write a macOS .icns file containing PNG representations."""
    out = ICONS / "app_icon.icns"
    body = b""
    header = b""
    for size, ostype in ICNS_TYPES:
        data = write_png_bytes(img, size)
        header += ostype.encode("ascii") + struct.pack(">I", len(data) + 8)
        body += data
    with out.open("wb") as fh:
        fh.write(b"icns")
        fh.write(struct.pack(">I", len(header) + len(body) + 8))
        fh.write(header)
        fh.write(body)
    return out


def main() -> int:
    if not MASTER.exists():
        raise SystemExit(f"missing master icon: {MASTER}")
    try:
        img = load_master()
    except ImportError:
        raise SystemExit("Pillow is required: pip install pillow")

    from PIL import Image

    Image.open(MASTER).convert("RGBA").resize((512, 512), Image.LANCZOS).save(
        ICONS / "app_icon_512.png"
    )
    print(f"wrote {ICONS / 'app_icon_512.png'}")

    ico = write_ico(img)
    print(f"wrote {ico}")

    icns = write_icns(img)
    print(f"wrote {icns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
