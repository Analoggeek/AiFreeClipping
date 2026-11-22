#!/usr/bin/env python3
"""Fetch static FFmpeg + FFprobe binaries for every CLIPOS target platform.

Run once before building an installer:

    python scripts/vendor_ffmpeg.py

Binaries land in ``resources/ffmpeg/<platform-key>/`` and are consumed at runtime by
``clipos.core.ffmpeg``.  They are intentionally excluded from git (574 MB) and are
fetched by the build pipeline instead.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "resources" / "ffmpeg"

FFMPEG_PKGS = {
    "linux-x64": "@ffmpeg-installer/linux-x64",
    "linux-ia32": "@ffmpeg-installer/linux-ia32",
    "darwin-x64": "@ffmpeg-installer/darwin-x64",
    "darwin-arm64": "@ffmpeg-installer/darwin-arm64",
    "win32-x64": "@ffmpeg-installer/win32-x64",
    "win32-ia32": "@ffmpeg-installer/win32-ia32",
}

# ffprobe-static ships every platform inside one tarball.
FFPROBE_TARBALL = "https://registry.npmjs.org/ffprobe-static/-/ffprobe-static-3.1.0.tgz"
FFPROBE_LAYOUT = {
    "linux-x64": ("bin/linux/x64/ffprobe", "ffprobe"),
    "linux-ia32": ("bin/linux/ia32/ffprobe", "ffprobe"),
    "darwin-x64": ("bin/darwin/x64/ffprobe", "ffprobe"),
    "darwin-arm64": ("bin/darwin/arm64/ffprobe", "ffprobe"),
    "win32-x64": ("bin/win32/x64/ffprobe.exe", "ffprobe.exe"),
    "win32-ia32": ("bin/win32/ia32/ffprobe.exe", "ffprobe.exe"),
}


def _latest_tarball(pkg: str) -> str:
    enc = urllib.parse.quote(pkg, safe="")
    with urllib.request.urlopen(f"https://registry.npmjs.org/{enc}", timeout=60) as resp:
        data = json.load(resp)
    version = data["dist-tags"]["latest"]
    return data["versions"][version]["dist"]["tarball"]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "clipos-builder"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def fetch_ffmpeg() -> None:
    for key, pkg in FFMPEG_PKGS.items():
        target = DEST / key
        exe = target / ("ffmpeg.exe" if key.startswith("win32") else "ffmpeg")
        if exe.exists():
            print(f"  [skip] {key} already present")
            continue
        url = _latest_tarball(pkg)
        tmp = ROOT / ".vendor-tmp" / f"{key}.tgz"
        print(f"  [get ] {pkg} <- {url}")
        _download(url, tmp)
        extract_dir = ROOT / ".vendor-tmp" / key
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tmp) as tf:
            tf.extractall(extract_dir)
        src = extract_dir / "package" / ("ffmpeg.exe" if key.startswith("win32") else "ffmpeg")
        if not src.exists():
            raise SystemExit(f"ffmpeg binary missing in package for {key}")
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, exe)
        exe.chmod(0o755)
        shutil.rmtree(extract_dir, ignore_errors=True)
        tmp.unlink(missing_ok=True)


def fetch_ffprobe() -> None:
    tmp = ROOT / ".vendor-tmp" / "ffprobe.tgz"
    print(f"  [get ] ffprobe-static <- {FFPROBE_TARBALL}")
    _download(FFPROBE_TARBALL, tmp)
    extract_dir = ROOT / ".vendor-tmp" / "ffprobe"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tmp) as tf:
        tf.extractall(extract_dir)
    for key, (rel, name) in FFPROBE_LAYOUT.items():
        src = extract_dir / "package" / rel
        if not src.exists():
            print(f"  [warn] ffprobe missing for {key}")
            continue
        target = DEST / key / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        target.chmod(0o755)
    shutil.rmtree(extract_dir, ignore_errors=True)
    tmp.unlink(missing_ok=True)


def main() -> int:
    print("Vendoring FFmpeg + FFprobe for CLIPOS ...")
    DEST.mkdir(parents=True, exist_ok=True)
    fetch_ffmpeg()
    fetch_ffprobe()
    shutil.rmtree(ROOT / ".vendor-tmp", ignore_errors=True)
    total = sum(f.stat().st_size for f in DEST.rglob("*") if f.is_file())
    print(f"Done. {total / 1024 / 1024:.0f} MB in {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
