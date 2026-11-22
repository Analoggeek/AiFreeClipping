#!/usr/bin/env python3
"""Install the CLIPOS dependencies correctly.

``pip install -r requirements.txt`` alone is not enough, because two of the
transitive dependencies fight over the same files:

* **scenedetect** requires ``opencv-python`` — the *GUI* build.  Importing
  it on a headless machine fails with
  ``ImportError: libGL.so.1: cannot open shared object file``, and the
  current release (5.x) has also removed ``cv2.CascadeClassifier``, which
  CLIPOS uses for face detection.
* **faster-whisper** and **scenedetect** pull in a lot of large wheels that
  make a cold install slow.

This script installs the pinned set and then repairs the OpenCV situation:
it removes the GUI build and reinstalls the headless one, which is the only
version that works on a build machine without a display.

    python scripts/install_deps.py

It is safe to run more than once and it never needs root.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The packages CLIPOS actually needs, in a deliberate order.
CORE = [
    "PySide6>=6.6,<6.9",
    "numpy>=1.24",
    "pillow>=10.0",
    "requests>=2.31",
    "huggingface-hub>=0.23",
    "faster-whisper>=1.0,<2",
    "onnxruntime>=1.16",
    "scenedetect>=0.6.3",
]

# Installed last, and with --force-reinstall, so it wins over the GUI build
# that scenedetect drags in.
HEADLESS_OPENCV = "opencv-python-headless>=4.8,<5"

# Packages that must never be present: they overwrite the headless OpenCV
# with a GUI build that cannot be imported without libGL.
FORBIDDEN = ["opencv-python"]

# Build-time extras.
BUILD = ["pyinstaller>=6.6"]


def run(cmd: list[str], what: str) -> None:
    print(f"\n=== {what} ===")
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"{what} failed with exit code {result.returncode}")


def pip(*args: str) -> list[str]:
    return [sys.executable, "-m", "pip", *args]


def installed(name: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", name],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def uninstall(name: str) -> None:
    if not installed(name):
        return
    print(f"\n=== removing {name} ===")
    subprocess.run(pip("uninstall", "-y", name))


def main() -> int:
    ap = argparse.ArgumentParser(description="Install the CLIPOS dependencies")
    ap.add_argument("--build", action="store_true",
                    help="also install the packaging tools")
    ap.add_argument("--no-opencv", action="store_true",
                    help="skip the OpenCV repair (Windows and macOS only)")
    args = ap.parse_args()

    run(pip("install", "--upgrade", "pip"), "upgrading pip")

    packages = list(CORE)
    if args.build:
        packages += BUILD
    run(pip("install", *packages), "installing the core packages")

    if not args.no_opencv:
        # scenedetect pulled in the GUI build of OpenCV.  Remove it, then
        # reinstall the headless build so the files it overwrote are restored.
        for name in FORBIDDEN:
            uninstall(name)
        run(pip("install", "--force-reinstall", "--no-deps", HEADLESS_OPENCV),
            "installing the headless build of OpenCV")
    else:
        # Windows and macOS have libGL, so the GUI build works there — but
        # OpenCV 5 still removed CascadeClassifier, so pin the version.
        run(pip("install", "--force-reinstall", "--no-deps", HEADLESS_OPENCV),
            "pinning the OpenCV version")

    print("\n=== verifying ===")
    check = subprocess.run(
        [sys.executable, "-c",
         "import cv2, numpy, PySide6; "
         "print('opencv', cv2.__version__); "
         "print('cascade  ', 'ok' if hasattr(cv2, 'CascadeClassifier') else 'MISSING'); "
         "print('numpy   ', numpy.__version__); "
         "print('pyside6 ', PySide6.__version__)"],
        capture_output=True, text=True,
    )
    print(check.stdout.strip())
    if check.returncode != 0:
        print(check.stderr.strip(), file=sys.stderr)
        raise SystemExit("the dependencies did not import cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
