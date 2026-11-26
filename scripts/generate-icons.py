"""Build all platform icons from the selected brand mark (Pillow only)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "brand" / "logo-mark.png"


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE}")
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — copying PNG as a fallback icon")
        for target in ("brand/icon.png", "brand/icon.ico", "brand/icon.icns"):
            shutil.copyfile(SOURCE, ROOT / target)
        return
    image = Image.open(SOURCE).convert("RGBA")
    square = min(image.size)
    image = image.crop(
        ((image.width - square) // 2, (image.height - square) // 2,
         (image.width + square) // 2, (image.height + square) // 2)
    )
    image = image.resize((512, 512), Image.LANCZOS)
    image.save(ROOT / "brand" / "icon.png", optimize=True)
    image.resize((256, 256), Image.LANCZOS).save(
        ROOT / "brand" / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    try:
        image.resize((512, 512), Image.LANCZOS).save(
            ROOT / "brand" / "icon.icns",
            sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)],
        )
    except Exception as exc:  # some Pillow builds lack the ICNS writer
        print("ICNS writer unavailable:", exc, file=sys.stderr)
        shutil.copyfile(ROOT / "brand" / "icon.png", ROOT / "brand" / "icon.icns")
    print("Icons written to brand/icon.png, brand/icon.ico, brand/icon.icns")


if __name__ == "__main__":
    main()
