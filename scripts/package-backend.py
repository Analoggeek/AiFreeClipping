#!/usr/bin/env python3
"""Bundle the Python AI engine (incl. ffmpeg) into backend/runtime/<platform>-<arch>/.

Run once per target platform on a matching OS runner (see .github/workflows/release.yml).
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "backend" / "runtime"


def detect() -> tuple[str, str]:
    system = platform.system().lower()
    plat = {"windows": "windows", "darwin": "macos", "linux": "linux"}.get(system, system)
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    return plat, arch


def ffmpeg_candidates() -> list[Path]:
    found = []
    override = os.getenv("FFMPEG_BINARY")
    if override and Path(override).exists():
        found.append(Path(override))
    which = shutil.which("ffmpeg")
    if which:
        found.append(Path(which))
    try:
        import imageio_ffmpeg  # type: ignore

        found.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:
        pass
    return found


def build(plat: str, arch: str, skip_pyinstaller: bool = False) -> Path:
    target = RUNTIME / f"{plat}-{arch}"
    target.mkdir(parents=True, exist_ok=True)
    if not skip_pyinstaller:
        try:
            import PyInstaller  # noqa: F401  # type: ignore
        except ImportError:
            raise SystemExit("PyInstaller missing. Run: pip install -r backend/requirements.txt")
        work = ROOT / "backend" / "build" / f"{plat}-{arch}"
        work.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--name", "ai-clipper-backend",
            "--distpath", str(target),
            "--workpath", str(work),
            "--specpath", str(work),
            "--paths", str(ROOT / "backend"),
            "--add-data", f"{ROOT / 'backend' / 'app' / 'assets' / 'comfy_sdxl.json'}{os.pathsep}app/assets",
            "--add-data", f"{ROOT / 'brand' / 'icon.png'}{os.pathsep}brand",
            "--hidden-import", "uvicorn.logging",
            "--hidden-import", "uvicorn.loops.auto",
            "--hidden-import", "uvicorn.protocols.http.auto",
            "--hidden-import", "yt_dlp",
            "--hidden-import", "faster_whisper",
            "--hidden-import", "cv2",
            "--exclude-module", "torch",
            "--exclude-module", "torchvision",
            "--exclude-module", "ultralytics",
            "--exclude-module", "supervision",
            str(ROOT / "backend" / "entrypoint.py"),
        ]
        print("Bundling Python engine:", " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, cwd=ROOT)
    else:
        print("Skipping PyInstaller (--skip-pyinstaller); installer will need an external Python runtime.")

    for candidate in ffmpeg_candidates():
        if not candidate.exists():
            continue
        name = "ffmpeg.exe" if plat == "windows" else "ffmpeg"
        destination = target / name
        if candidate.resolve() != destination.resolve():
            shutil.copy2(candidate, destination)
            print(f"Bundled ffmpeg: {destination}", flush=True)
        break
    else:
        print("WARNING: ffmpeg binary not found. Install imageio-ffmpeg or put ffmpeg on PATH.", file=sys.stderr)
    (target / "README.txt").write_text(
        "AI Clipper Pro local engine bundle. Do not modify.\n"
        f"Built for {plat}-{arch}.\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default=None)
    parser.add_argument("--arch", default=None)
    parser.add_argument("--skip-pyinstaller", action="store_true")
    args = parser.parse_args()
    default_plat, default_arch = detect()
    target = build(args.platform or default_plat, args.arch or default_arch, args.skip_pyinstaller)
    print(f"Engine bundle ready: {target}")


if __name__ == "__main__":
    main()
