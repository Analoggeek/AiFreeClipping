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
import hashlib
import gzip
import os
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

# The Intel macOS npm artifact used FFmpeg 4.x/x264 from 2018, matching
# the reported CoreText/first-frame SIGSEGV. Refresh this release target with
# a pinned, architecture-checked upstream artifact; never silently reuse it.
INTEL_FFMPEG = {
    'release':'b6.0',
    'license_sha256':'cb48bf09a11f5fb576cddb0431c8f5ed0a60157a9ec942adffc13907cbe083f2',
    'readme_sha256':'ff37cc192ed96c54fe9a80182e11b24fc2378bd37a4ef99e2b80aa8cb48c120a',
    'archive_sha256':'a12354fce7eb62361473bbe10d53a1893695babd35869ec8e92e5dfea8d0440b',
}


def fetch_intel_ffmpeg():
    target=DEST/'darwin-x64'/'ffmpeg'
    manifest=target.parent/'ffmpeg-provenance.json'
    if target.exists() and manifest.exists():
        data=json.loads(manifest.read_text())
        metadata_ok=all((target.parent/name).is_file() and hashlib.sha256((target.parent/name).read_bytes()).hexdigest()==INTEL_FFMPEG[key] for name,key in (('darwin-x64.LICENSE','license_sha256'),('darwin-x64.README','readme_sha256')))
        if metadata_ok and data.get('archive_sha256')==INTEL_FFMPEG['archive_sha256'] and data.get('binary_sha256')==hashlib.sha256(target.read_bytes()).hexdigest():
            check_arch(target,'darwin-x64')
            print('  [skip] verified pinned Intel FFmpeg '+INTEL_FFMPEG['release'])
            return
    base='https://github.com/eugeneware/ffmpeg-static/releases/download/'+INTEL_FFMPEG['release']+'/'
    temporary=ROOT/'.vendor-tmp'/'intel-modern.gz'
    _download(base+'ffmpeg-darwin-x64.gz',temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=INTEL_FFMPEG['archive_sha256']:
        raise RuntimeError('Intel FFmpeg archive checksum mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    candidate=target.with_name('.ffmpeg-new')
    try:
        with gzip.open(temporary,'rb') as source,candidate.open('wb') as output:
            shutil.copyfileobj(source,output)
        candidate.chmod(0o755)
        check_arch(candidate,'darwin-x64')
        # Keep upstream provenance/licenses with the shipped binary.
        for name in ('darwin-x64.LICENSE','darwin-x64.README'):
            _download(base+name,target.parent/name)
            expected=INTEL_FFMPEG['license_sha256' if name.endswith('.LICENSE') else 'readme_sha256']
            if hashlib.sha256((target.parent/name).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Intel FFmpeg license/provenance checksum mismatch')
        data={**INTEL_FFMPEG,'url':base+'ffmpeg-darwin-x64.gz',
              'binary_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
        os.replace(candidate,target)
        manifest.write_text(json.dumps(data,indent=2))
    finally:
        candidate.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


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
        if key=='darwin-x64':
            fetch_intel_ffmpeg()
            continue
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
