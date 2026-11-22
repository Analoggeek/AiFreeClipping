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
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

APP_NAME = "CLIPOS"
BUNDLE_ID = "com.clipos.studio"
VERSION = "1.0.0"


def _write_summary(title: str, body: str) -> None:
    """Append a section to the GitHub Actions job summary.

    The summary is the one part of a CI run that is always readable, even
    when the log storage is not reachable, so it is where a build failure
    explains itself.
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"### {title}\n\n```\n{body}\n```\n\n")
    except OSError:
        pass


def run(cmd: list[str], **kwargs) -> None:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, **kwargs)
    if result.returncode != 0:
        # Write the failing command to a file and to the job summary, so a
        # CI job shows what went wrong instead of just the exit code.
        message = " ".join(str(c) for c in cmd) + f"\n\nexit code: {result.returncode}\n"
        try:
            BUILD.mkdir(parents=True, exist_ok=True)
            (BUILD / "build-error.log").write_text(message, encoding="utf-8")
        except OSError:
            pass
        _write_summary("Build failed", message)
        raise SystemExit(f"command failed with exit code {result.returncode}: {cmd}")


def _python_architecture(python: str) -> str:
    """The architecture of an interpreter, or an empty string."""
    try:
        import subprocess

        out = subprocess.run(
            [python, "-c", "import platform; print(platform.machine())"],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout.strip().lower()
    except Exception:
        return ""


def _has_pyinstaller(python: str) -> bool:
    """Whether an interpreter can run PyInstaller."""
    try:
        import subprocess

        out = subprocess.run(
            [python, "-c", "import PyInstaller; print('yes')"],
            capture_output=True, text=True, timeout=60,
        )
        return out.returncode == 0
    except Exception:
        return False


def find_python_for_arch(arch: str) -> str:
    """Find an interpreter for the given architecture.

    An Intel application needs an Intel Python: the extension modules
    have to be compiled for the machine the application is meant to run
    on.  On an Apple Silicon machine the interpreter that comes first on
    the path is usually the wrong one, so the interpreters are looked at
    until one reports the wanted architecture.
    """
    if not arch:
        return sys.executable

    wanted = "x86_64" if arch in ("x86_64", "intel") else "arm64"

    # The interpreter the caller asked for, if it is the right one.
    chosen = os.environ.get("CLIPOS_BUILD_PYTHON", "").strip()
    if chosen and Path(chosen).exists():
        found = _python_architecture(chosen)
        if not found or wanted in found:
            return chosen
        print(f"[build] {chosen} is {found}, not {wanted}; looking further")

    candidates: list[str] = []
    # The project's own environment, which is where the dependencies are
    # installed.
    for own in (ROOT / ".venv" / "bin" / "python",
                ROOT / ".venv" / "Scripts" / "python.exe"):
        if own.exists():
            candidates.append(str(own))
    # The interpreters the runner keeps in its tool cache.  These are the
    # ones the workflow installed, so they are the ones with the build
    # tools in them.
    for base in sorted(Path("/Users/runner/hostedtoolcache/Python").glob(
            "*/*/bin/python*"), reverse=True):
        if "python3" in base.name:
            candidates.append(str(base))
    # Everything on the path.
    for name in ("python3.11", "python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.append(sys.executable)

    # An interpreter that cannot build anything is no use, so the ones
    # that have PyInstaller in them are preferred.
    for candidate in candidates:
        try:
            if not Path(candidate).exists():
                continue
        except OSError:
            continue
        found = _python_architecture(candidate)
        if not found or wanted not in found:
            continue
        if not _has_pyinstaller(candidate):
            print(f"[build] {candidate} has no PyInstaller in it; skipping it")
            continue
        print(f"[build] using {candidate} for {wanted}")
        return candidate

    # Nothing with the right architecture has PyInstaller in it.  An
    # interpreter of the right architecture is still better than one of
    # the wrong one, because the build then fails with a clear message
    # about the architecture rather than a confusing one.
    for candidate in candidates:
        try:
            if not Path(candidate).exists():
                continue
        except OSError:
            continue
        found = _python_architecture(candidate)
        if found and wanted in found:
            print(f"[build] using {candidate} for {wanted}")
            return candidate

    print(
        f"[build] WARNING: no {wanted} interpreter was found; the build may "
        f"fail if the extension modules are for the wrong architecture"
    )
    return chosen or sys.executable


def venv_python() -> str:
    """The Python that does the freezing.

    CLIPOS_BUILD_PYTHON points at a different interpreter when one is
    needed -- an Intel build on an Apple Silicon machine needs an Intel
    Python, because the extension modules have to be compiled for the
    machine the application is meant to run on.
    """
    chosen = os.environ.get("CLIPOS_BUILD_PYTHON", "").strip()
    if chosen and Path(chosen).exists():
        return chosen
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

    Windows and macOS are exempt.  The Windows bootloader links against
    ``python3.dll``, which ships with the interpreter, and the macOS one
    builds against the framework.  Only the ELF build needs the shared
    object.
    """
    if sys.platform in ("win32", "darwin"):
        return

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


def freeze(target: str, target_arch: str = "") -> None:
    """Run PyInstaller, keeping its output in a file for diagnosis.

    PyInstaller prints thousands of lines and the interesting part is
    usually near the end, so the whole log is kept next to the build.
    """
    BUILD.mkdir(parents=True, exist_ok=True)
    log_path = BUILD / "pyinstaller.log"
    if target_arch:
        python = find_python_for_arch(target_arch)
        os.environ["CLIPOS_BUILD_PYTHON"] = python
    args = pyinstaller_args(target, target_arch)
    print(f"\n$ {' '.join(args)}")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(args, cwd=ROOT, stdout=log,
                                stderr=subprocess.STDOUT)
    if result.returncode != 0:
        # Show the tail of the log, where the error is.
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")
            print("\n".join(tail.splitlines()[-60:]))
        except OSError:
            pass
        message = (
            " ".join(str(c) for c in args)
            + f"\n\nexit code: {result.returncode}\n\n"
            + "\n".join(tail.splitlines()[-60:])
        )
        try:
            (BUILD / "build-error.log").write_text(message, encoding="utf-8")
        except OSError:
            pass
        _write_summary("PyInstaller failed", message)
        raise SystemExit(
            f"PyInstaller failed with exit code {result.returncode}; "
            f"see {log_path}"
        )
    print(f"[build] PyInstaller finished; log at {log_path}")


def pyinstaller_args(target: str, target_arch: str = "") -> list[str]:
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
    if target_arch:
        # PyInstaller uses this to pick the bootloader and to check every
        # collected binary for the right architecture slice.  Without it
        # the bundle keeps the architecture of the machine that built it,
        # whatever ARCHFLAGS says.
        args += ["--target-architecture", target_arch]
    for src, dest in bundles:
        args += ["--add-data", f"{ROOT / src}{sep}{dest}"]
    args += [
        "--hidden-import", "clipos",
        "--collect-submodules", "clipos",
        "--collect-all", "faster_whisper",
        "--collect-all", "cv2",
        # onnxruntime ships its own DLLs and a large set of data files.
        # Collecting everything is not only slow, it also pulls in the
        # training tools, which are not needed at runtime and which some
        # PyInstaller versions fail to bundle on Windows.
        "--collect-binaries", "onnxruntime",
        "--collect-data", "onnxruntime",
        "--exclude-module", "onnxruntime.tools",
        "--exclude-module", "onnxruntime.transformers",
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
    freeze("windows")

    app_dir = DIST / APP_NAME
    if not app_dir.exists():
        raise SystemExit(f"PyInstaller did not produce {app_dir}")

    # The installer back-end lives in its own module so it can be tested and
    # reused without running the whole PyInstaller pipeline.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from installer_windows import build_windows_installer

    try:
        target = build_windows_installer(app_dir, DIST)
    except (SystemExit, Exception) as exc:
        # Any failure here has to be readable afterwards: the CI logs are
        # not always reachable, so the reason is written next to the
        # build where the diagnostic reporter picks it up.
        print(f"[build] WARNING: {exc}")
        print("[build] Falling back to a portable zip.")
        try:
            (BUILD / "build-error.log").write_text(
                f"building the Windows installer failed: {exc}\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
            )
        except OSError:
            pass
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
    """Build the macOS application and its disk image.

    ``target_arch`` is the architecture the application is built for:
    ``arm64``, ``x86_64`` or ``universal2``.  It is handed to PyInstaller,
    which then uses the right bootloader and checks every collected binary
    for the right slice -- without it the bundle silently keeps the
    architecture of the machine that built it.

    ARCHFLAGS is set as well, because it is what the compiler and the
    linker use to pick the right slice for the extension modules.
    """
    print("[build] freezing for macOS ...")
    if target_arch:
        print(f"[build] targeting {target_arch}")
        os.environ["ARCHFLAGS"] = f"-arch {target_arch}"
    freeze("macos", target_arch)

    app = DIST / f"{APP_NAME}.app"
    if not app.exists():
        raise SystemExit(f"PyInstaller did not produce {app}")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from installer_macos import build_dmg, polish_app_bundle

    polish_app_bundle(app)

    # The disk image carries the architecture in its name, so an Apple
    # Silicon build and an Intel build can live side by side.
    arch = {"x86_64": "intel", "arm64": "arm64"}.get(target_arch, "")
    dmg = build_dmg(app, DIST, arch=arch)
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
    freeze("linux")
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
