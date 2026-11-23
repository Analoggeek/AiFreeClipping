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
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The packages CLIPOS actually needs, in a deliberate order.
CORE = [
    'google-api-python-client>=2.150,<3',
    'google-auth-oauthlib>=1.2,<2',
    'keyring>=25,<26',
    "yt-dlp>=2025.1.15",
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
BUILD = ["pyinstaller>=6.6", "pytest>=8,<10"]

# ziglang carries an LLVM toolchain with a Windows target, so a native .exe
# installer can be cross-compiled from any host.  It is only needed to build
# the installer, never to run the application.
ZIG = "ziglang>=0.11"


def run(cmd: list[str], what: str) -> None:
    """Run a command, retrying it a few times.

    The download of the packages is the flakiest part of the build: the
    network on a build machine drops connections regularly, and a build
    that fails after half an hour of PyInstaller work is a build that has
    to be thrown away.  Retrying the download costs a minute and saves
    the whole run.
    """
    print(f"\n=== {what} ===")
    print(f"$ {' '.join(cmd)}", flush=True)

    is_pip = "pip" in " ".join(cmd)
    attempts = 3 if is_pip else 1
    last = 0
    log_path = ROOT / "build" / "pip-install.log" if is_pip else None
    for attempt in range(1, attempts + 1):
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8", errors="replace") as log:
                log.write(f"\n$ {' '.join(cmd)}\n")
                log.flush()
                result = subprocess.run(cmd, stdout=log,
                                        stderr=subprocess.STDOUT)
        else:
            result = subprocess.run(cmd)
        if result.returncode == 0:
            return
        last = result.returncode
        if attempt < attempts:
            print(f"### {what} failed with exit code {last}; "
                  f"trying again ({attempt}/{attempts - 1})", flush=True)
            time.sleep(15)
    if is_pip:
        # Keep what pip said: it names the package and the reason, which
        # is exactly what is needed to fix it.
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
        except OSError:
            pass
        _write_failure(f"{what} failed with exit code {last}\n"
                       f"$ {' '.join(cmd)}\n\n{tail}")
    raise SystemExit(f"{what} failed with exit code {last}")


def python_command(*args: str) -> list[str]:
    """Keep subprocesses in the current Mach-O slice of universal Python.

    On Apple Silicon a Rosetta parent does not guarantee that a newly exec'd
    universal interpreter stays x86_64. Without arch, pip can install ARM wheels
    into the otherwise isolated Intel venv.
    """
    prefix = ["arch", "-" + platform.machine()] if sys.platform == "darwin" else []
    return [*prefix, sys.executable, *args]


def pip(*args: str) -> list[str]:
    # Recent cryptography releases ship ARM-only macOS wheels. A source build
    # launched by pip under Rosetta can still have Rust target the ARM host.
    # Resolve the newest compatible wheel instead of silently compiling one.
    if sys.platform == "darwin" and args and args[0] == "install":
        args = (args[0], "--only-binary=cryptography", *args[1:])
    return python_command("-m", "pip", *args)


def installed(name: str) -> bool:
    result = subprocess.run(
        pip("show", name),
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
                    help="kept for compatibility; the OpenCV version is "
                         "always pinned")
    args = ap.parse_args()

    try:
        return _install(args)
    except SystemExit as exc:
        # A failed dependency install has to be readable afterwards: the
        # CI logs are not always reachable, so the reason is written next
        # to the build where the diagnostic reporter picks it up.
        _write_failure(str(exc))
        raise


def _write_failure(reason: str) -> None:
    try:
        path = Path(__file__).resolve().parents[1] / "build" / "build-error.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"### Installing the dependencies failed\n\n{reason}\n\n")
    except OSError:
        pass


def _install_zig() -> bool:
    """Install the C compiler used by the self-extracting installer.

    The wheel is large and the download is the slowest part of the
    dependency install, so a failure here is reported but does not stop
    the build: on Windows the installer is produced by Inno Setup, and
    the compiler is only the fallback.
    """
    if installed("ziglang"):
        print("=== the C compiler is already installed ===")
        return True
    try:
        run(pip("install", ZIG), "installing the C compiler")
    except SystemExit as exc:
        print(f"### the C compiler could not be installed: {exc}")
        return False
    return True


def _install(args) -> int:
    run(pip("install", "--upgrade", "pip"), "upgrading pip")

    # OpenCV is pinned and installed on its own, before anything that
    # depends on it.  scenedetect pulls in the GUI build of OpenCV 5,
    # which removed CascadeClassifier and cannot be imported without
    # libGL, so the version has to be set before the rest.
    run(pip("install", HEADLESS_OPENCV), "pinning the OpenCV version")

    packages = list(CORE)
    if args.build:
        packages += BUILD
    run(pip("install", *packages), "installing the core packages")

    if args.build:
        # The self-extracting Windows installer needs a C compiler.  On
        # Windows itself Inno Setup is used instead, so the compiler is
        # only a fallback -- and the wheel is over a hundred megabytes,
        # so a failure here must not stop the build.
        if not _install_zig():
            print("### the C compiler fallback is not available; "
                  "the build will rely on Inno Setup")

    # scenedetect pulls in the GUI build of OpenCV, which removed
    # CascadeClassifier.  It has to go whatever else is done, and then
    # the pinned build is put back so the files it overwrote are restored.
    for name in FORBIDDEN:
        uninstall(name)
    run(pip("install", "--force-reinstall", "--no-deps", HEADLESS_OPENCV),
        "installing the pinned build of OpenCV")

    print("\n=== verifying ===")
    check = subprocess.run(
        python_command("-c",
         "import cv2, numpy, PySide6; "
         "print('opencv', cv2.__version__); "
         "print('cascade  ', 'ok' if hasattr(cv2, 'CascadeClassifier') else 'MISSING'); "
         "print('numpy   ', numpy.__version__); "
         "print('pyside6 ', PySide6.__version__)"),
        capture_output=True, text=True,
    )
    print(check.stdout.strip())
    if check.returncode != 0:
        print(check.stderr.strip(), file=sys.stderr)
        # The import error is the whole point of the check, so it is kept
        # where it can be read afterwards.
        _write_failure("the dependencies did not import cleanly\n\n"
                       + check.stdout.strip() + "\n\n" + check.stderr.strip())
        raise SystemExit("the dependencies did not import cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
