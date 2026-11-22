#!/usr/bin/env python3
"""Fetch static FFmpeg + FFprobe binaries for every CLIPOS target platform.

Run once before building an installer:

    python scripts/vendor_ffmpeg.py

Binaries land in ``resources/ffmpeg/<platform-key>/`` and are consumed at runtime by
``clipos.core.ffmpeg``.  They are intentionally excluded from git (652 MB) and are
fetched by the build pipeline instead.

Every downloaded binary is checked: the architecture recorded in the file name has
to match the architecture the file really is.  A package that puts an Intel
binary in the Apple Silicon folder is worse than no binary at all -- the
application then runs under Rosetta, or not at all.
"""
from __future__ import annotations

import json
import shutil
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clipos.core.binary_arch import (  # noqa: E402
    EXPECTED_ARCH,
    binary_arch,
    check_arch,
)

DEST = ROOT / "resources" / "ffmpeg"

FFMPEG_PKGS = {
    "linux-x64": "@ffmpeg-installer/linux-x64",
    "linux-ia32": "@ffmpeg-installer/linux-ia32",
    "darwin-x64": "@ffmpeg-installer/darwin-x64",
    "darwin-arm64": "@ffmpeg-installer/darwin-arm64",
    "win32-x64": "@ffmpeg-installer/win32-x64",
    "win32-ia32": "@ffmpeg-installer/win32-ia32",
}

# ffprobe comes from its own set of packages, one per platform.
#
# The "ffprobe-static" tarball cannot be used: its bin/darwin/arm64/ffprobe is
# really an Intel binary, so on an Apple Silicon machine it would only run
# under Rosetta -- and not at all when Rosetta is not installed.
FFPROBE_PKGS = {
    "linux-x64": ("@ffprobe-installer/linux-x64", "ffprobe"),
    "linux-ia32": ("@ffprobe-installer/linux-ia32", "ffprobe"),
    "darwin-x64": ("@ffprobe-installer/darwin-x64", "ffprobe"),
    "darwin-arm64": ("@ffprobe-installer/darwin-arm64", "ffprobe"),
    "win32-x64": ("@ffprobe-installer/win32-x64", "ffprobe.exe"),
    "win32-ia32": ("@ffprobe-installer/win32-ia32", "ffprobe.exe"),
}

# --------------------------------------------------------------------------------------
# Downloading
# --------------------------------------------------------------------------------------
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


def _extract(tarball: Path, work_dir: Path) -> Path:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball) as tf:
        tf.extractall(work_dir)
    return work_dir / "package"


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
        package = _extract(tmp, ROOT / ".vendor-tmp" / key)
        src = package / ("ffmpeg.exe" if key.startswith("win32") else "ffmpeg")
        if not src.exists():
            raise SystemExit(f"ffmpeg binary missing in package for {key}")
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, exe)
        exe.chmod(0o755)
        check_arch(exe, key)
        shutil.rmtree(package.parent, ignore_errors=True)
        tmp.unlink(missing_ok=True)


def fetch_ffprobe() -> None:
    for key, (pkg, name) in FFPROBE_PKGS.items():
        target = DEST / key / name
        if target.exists():
            print(f"  [skip] ffprobe for {key} already present")
            continue
        url = _latest_tarball(pkg)
        tmp = ROOT / ".vendor-tmp" / f"ffprobe-{key}.tgz"
        print(f"  [get ] {pkg} <- {url}")
        _download(url, tmp)
        package = _extract(tmp, ROOT / ".vendor-tmp" / f"ffprobe-{key}")
        src = package / name
        if not src.exists():
            raise SystemExit(f"ffprobe binary missing in package for {key}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        target.chmod(0o755)
        check_arch(target, key)
        shutil.rmtree(package.parent, ignore_errors=True)
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
