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
import struct
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

# The architecture each platform key has to end up with.
EXPECTED_ARCH = {
    "linux-x64": "x86_64",
    "linux-ia32": "i386",
    "darwin-x64": "x86_64",
    "darwin-arm64": "arm64",
    "win32-x64": "x86_64",
    "win32-ia32": "i386",
}


# --------------------------------------------------------------------------------------
# Architecture checks
# --------------------------------------------------------------------------------------
_MACH_CPU_TYPES = {
    7: "i386",
    0x01000007: "x86_64",
    12: "arm",
    0x0100000C: "arm64",
}


def _macho_arch(path: Path) -> str | None:
    """The architecture of a Mach-O file, or None if it is not a Mach-O."""
    try:
        data = path.read_bytes()[:64]
    except OSError:
        return None
    if len(data) < 8:
        return None
    little = struct.unpack("<I", data[:4])[0]
    big = struct.unpack(">I", data[:4])[0]
    magic = little if little in (0xFEEDFACE, 0xFEEDFACF) else big
    if magic in (0xFEEDFACE, 0xFEEDFACF):
        cpu, = struct.unpack("<i", data[4:8])
        return _MACH_CPU_TYPES.get(cpu, f"cpu{cpu}")
    if magic in (0xCAFEBABE, 0xBEBAFECA):
        count = struct.unpack(">I", data[4:8])[0]
        found = []
        for index in range(count):
            offset = 8 + index * 20
            cpu, = struct.unpack(">i", data[offset:offset + 4])
            found.append(_MACH_CPU_TYPES.get(cpu, f"cpu{cpu}"))
        # A fat binary holds several architectures; it satisfies any of them.
        return "|".join(found)
    return None


def _elf_arch(path: Path) -> str | None:
    """The architecture of an ELF file, or None if it is not an ELF."""
    try:
        data = path.read_bytes()[:20]
    except OSError:
        return None
    if len(data) < 20 or data[:4] != b"\x7fELF":
        return None
    is_64 = data[4] == 2
    little = data[5] == 1
    order = "<" if little else ">"
    machine, = struct.unpack(order + "H", data[18:20])
    names = {3: "i386", 62: "x86_64", 40: "arm", 183: "arm64"}
    return names.get(machine, f"machine{machine}")


def _pe_arch(path: Path) -> str | None:
    """The architecture of a Windows executable, or None."""
    try:
        data = path.read_bytes()[:1024]
    except OSError:
        return None
    if data[:2] != b"MZ":
        return None
    offset = struct.unpack("<I", data[0x3C:0x40])[0]
    if offset + 6 > len(data) or data[offset:offset + 2] != b"PE":
        return None
    machine, = struct.unpack("<H", data[offset + 4:offset + 6])
    return {0x014C: "i386", 0x8664: "x86_64", 0xAA64: "arm64"}.get(
        machine, f"machine{machine}"
    )


def binary_arch(path: Path) -> str | None:
    """The architecture of a binary, whichever format it is in."""
    for probe in (_macho_arch, _elf_arch, _pe_arch):
        found = probe(path)
        if found:
            return found
    return None


def check_arch(path: Path, key: str) -> None:
    """Make sure a binary really is the architecture it is filed under.

    A mismatch is not a warning: an Intel binary in the Apple Silicon
    folder runs under Rosetta, or not at all, and nothing in the
    application says why.
    """
    expected = EXPECTED_ARCH.get(key)
    if not expected:
        return
    found = binary_arch(path)
    if found is None:
        # The architecture could not be read.  That is not proof of a
        # problem, so the file is kept.
        print(f"  [warn] the architecture of {path.name} could not be read")
        return
    if expected in found.split("|"):
        print(f"  [ok  ] {path.name} is {found}")
        return
    raise SystemExit(
        f"{path} is a {found} binary but it is filed as {expected}. "
        f"The package it came from is wrong; refusing to ship it."
    )


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
