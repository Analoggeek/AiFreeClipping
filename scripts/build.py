#!/usr/bin/env python3
"""Build CLIPOS installers for macOS, Windows and Linux.

    python scripts/build.py windows
    python scripts/build.py macos
    python scripts/build.py linux
    python scripts/build.py macos --target-arch arm64

The script:

  1. makes sure the native FFmpeg/FFprobe binaries are vendored,
  2. runs the end-to-end test so a broken build never ships,
  3. freezes the application with PyInstaller,
  4. wraps the result in an installer (.exe / .dmg / AppImage).
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

APP_NAME = "CLIPOS"
BUNDLE_ID = "com.clipos.studio"
VERSION = "1.0.0"


def run(cmd: list[str], **kwargs) -> None:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, **kwargs)
    if result.returncode != 0:
        raise SystemExit(f"command failed with exit code {result.returncode}: {cmd}")


def venv_python() -> str:
    py = ROOT / ".venv" / "bin" / "python"
    if py.exists():
        return str(py)
    win = ROOT / ".venv" / "Scripts" / "python.exe"
    if win.exists():
        return str(win)
    return sys.executable


def ensure_ffmpeg() -> None:
    """Vendor the native binaries if they are missing."""
    base = ROOT / "resources" / "ffmpeg"
    if base.exists() and any(base.iterdir()):
        print("[build] native binaries already vendored")
        return
    print("[build] vendoring native FFmpeg binaries ...")
    run([venv_python(), str(ROOT / "scripts" / "vendor_ffmpeg.py")])


def ensure_cascades() -> None:
    cas = ROOT / "resources" / "cascades"
    if cas.exists() and any(cas.glob("*.xml")):
        print("[build] cascades already vendored")
        return
    print("[build] vendoring face cascades ...")
    run([venv_python(), str(ROOT / "scripts" / "vendor_cascades.py")])


def ensure_models() -> None:
    models = ROOT / "resources" / "models"
    if models.exists() and any(models.glob("*.onnx")):
        print("[build] face models already vendored")
        return
    print("[build] face models missing -- run scripts/vendor_models.py")
    print("        (the app still works with the Haar cascade fallback)")


def run_tests() -> None:
    print("[build] running the end-to-end test ...")
    run([venv_python(), str(ROOT / "scripts" / "e2e_test.py")])


def _shared_library_candidates(soname: str, libdir: str) -> list[Path]:
    """Every place the dynamic loader would look for the shared library."""
    candidates: list[Path] = []
    if libdir:
        candidates.append(Path(libdir) / soname)
    # The loader searches LD_LIBRARY_PATH before the system directories, so a
    # library placed there is perfectly usable.
    for entry in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep):
        if entry.strip():
            candidates.append(Path(entry.strip()) / soname)
    if sys.platform == "darwin":
        candidates.append(Path(sys.prefix) / "lib" / soname)
        candidates.append(Path("/usr/local/lib") / soname)
        candidates.append(Path("/opt/homebrew/lib") / soname)
    return candidates


def check_python_runtime() -> None:
    """Fail early with a clear message if PyInstaller cannot run here.

    On Debian/Ubuntu the system Python is built without an installed
    ``libpython3.x.so``, which PyInstaller's bootloader needs.  The fix is to
    install the ``libpython3.x`` package (requires root) or to build against a
    Python that ships the shared library (python.org builds, conda, Homebrew).
    """
    import sysconfig

    libdir = sysconfig.get_config_var("LIBDIR") or ""
    soname = sysconfig.get_config_var("INSTSONAME") or ""
    if not soname:
        return
    for candidate in _shared_library_candidates(soname, libdir):
        if candidate.exists():
            return
    if sysconfig.get_config_var("Py_ENABLE_SHARED"):
        raise SystemExit(
            f"\nPyInstaller needs the Python shared library ({soname}), which is "
            f"not installed in {libdir}.\n"
            f"  Debian/Ubuntu:  sudo apt install {soname.split('.')[0]}.{soname.split('.')[1]}\n"
            f"  Fedora/RHEL:    sudo dnf install python3-libs\n"
            f"  macOS:          use the python.org installer or Homebrew Python\n"
            f"  Or build inside a conda environment, which always ships it.\n"
            f"  Or point LD_LIBRARY_PATH at a directory that contains {soname}.\n"
        )


def pyinstaller_args(target: str) -> list[str]:
    sep = ";" if target == "windows" else ":"
    # The source path may be absolute, but the destination must be relative to
    # the bundle root so the files land in the right place inside the app.
    bundles = [
        ("resources/ffmpeg", "resources/ffmpeg"),
        ("resources/cascades", "resources/cascades"),
        ("resources/models", "resources/models"),
        ("resources/icons", "resources/icons"),
        ("resources/sounds", "resources/sounds"),
    ]
    args = [
        venv_python(), "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", APP_NAME,
        "--osx-bundle-identifier", BUNDLE_ID,
    ]
    for src, dest in bundles:
        args += ["--add-data", f"{ROOT / src}{sep}{dest}"]
    args += [
        "--hidden-import", "clipos",
        "--collect-submodules", "clipos",
        "--collect-all", "faster_whisper",
        "--collect-all", "cv2",
        "--collect-all", "onnxruntime",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pytest",
        "--exclude-module", "IPython",
    ]
    icon = ROOT / "resources" / "icons" / (
        "app_icon.ico" if target == "windows" else "app_icon.icns"
    )
    if icon.exists():
        args += ["--icon", str(icon)]
    args.append(str(ROOT / "clipos" / "__main__.py"))
    return args


def build_windows() -> Path:
    print("[build] freezing for Windows ...")
    run(pyinstaller_args("windows"))

    app_dir = DIST / APP_NAME
    if not app_dir.exists():
        raise SystemExit(f"PyInstaller did not produce {app_dir}")

    # The installer back-end lives in its own module so it can be tested and
    # reused without running the whole PyInstaller pipeline.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from installer_windows import build_windows_installer

    try:
        target = build_windows_installer(app_dir, DIST)
    except SystemExit as exc:
        print(f"[build] WARNING: {exc}")
        print("[build] Falling back to a portable zip.")
        import zipfile

        zip_path = DIST / f"{APP_NAME}-{VERSION}-portable-win.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in app_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, Path(APP_NAME) / p.relative_to(app_dir))
        print(f"[build] portable build: {zip_path}")
        return zip_path

    print(f"[build] installer: {target}")
    return target


def build_macos(target_arch: str = "") -> Path:
    print("[build] freezing for macOS ...")
    args = pyinstaller_args("macos")
    if target_arch:
        env = dict(os.environ, ARCHFLAGS=f"-arch {target_arch}")
        print(f"[build] targeting {target_arch}")
        run(args, env=env)
    else:
        run(args)

    app = DIST / f"{APP_NAME}.app"
    if not app.exists():
        raise SystemExit(f"PyInstaller did not produce {app}")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from installer_macos import build_dmg, polish_app_bundle

    polish_app_bundle(app)

    dmg = build_dmg(app, DIST)
    print(f"[build] disk image: {dmg}")
    return dmg


def verify_bundle(target: str) -> None:
    """Smoke-test the frozen bundle before it is handed to anyone."""
    script = Path(__file__).resolve().parent / "verify_bundle.py"
    if not script.exists():
        return
    print("[build] verifying the frozen bundle ...")
    rc = subprocess.run(
        [venv_python(), str(script), str(DIST)], cwd=ROOT
    ).returncode
    if rc != 0:
        raise SystemExit("The frozen bundle did not pass verification.")


def build_linux() -> Path:
    print("[build] freezing for Linux ...")
    run(pyinstaller_args("linux"))
    app_dir = DIST / APP_NAME
    if not app_dir.exists():
        raise SystemExit(f"PyInstaller did not produce {app_dir}")

    import zipfile

    zip_path = DIST / f"{APP_NAME}-{VERSION}-linux-x86_64.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in app_dir.rglob("*"):
            if p.is_file():
                zf.write(p, Path(APP_NAME) / p.relative_to(app_dir))
    print(f"[build] portable build: {zip_path}")

    # A native package installs the app into the system, adds a launcher to
    # the application menu and supports a clean uninstall.
    installers: list[Path] = [zip_path]
    try:
        from linux_installer import build_deb, build_rpm
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from linux_installer import build_deb, build_rpm

    if shutil.which("dpkg-deb"):
        try:
            installers.append(build_deb(app_dir, VERSION, DIST))
        except SystemExit as exc:
            print(f"[build] WARNING: {exc}")
    if shutil.which("rpmbuild"):
        try:
            installers.append(build_rpm(app_dir, VERSION, DIST))
        except SystemExit as exc:
            print(f"[build] WARNING: {exc}")

    for path in installers:
        print(f"[build] installer: {path}")
    return installers[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build CLIPOS installers")
    ap.add_argument("target", choices=["windows", "macos", "linux"])
    ap.add_argument("--target-arch", default="", help="e.g. arm64 for a universal macOS build")
    ap.add_argument("--skip-tests", action="store_true", help="skip the end-to-end test")
    ap.add_argument("--skip-vendor", action="store_true", help="skip fetching native binaries")
    args = ap.parse_args()

    if args.target == "windows" and platform.system() != "Windows":
        print("[build] WARNING: building a Windows installer on a non-Windows host.")
        print("        PyInstaller cannot cross-compile -- run this on Windows.")

    if args.target == "macos" and platform.system() != "Darwin":
        print("[build] WARNING: building a macOS app on a non-macOS host.")
        print("        PyInstaller cannot cross-compile -- run this on macOS.")

    DIST.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)

    if not args.skip_vendor:
        ensure_ffmpeg()
        ensure_cascades()
        ensure_models()
    if not args.skip_tests:
        run_tests()
    check_python_runtime()

    if args.target == "windows":
        out = build_windows()
    elif args.target == "macos":
        out = build_macos(args.target_arch)
    else:
        out = build_linux()

    verify_bundle(args.target)

    print("\n" + "=" * 60)
    print(f"  Build complete: {out}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
