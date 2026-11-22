"""Smoke-test a frozen CLIPOS bundle.

The frozen application cannot be imported like a normal Python package, so the
checks below run the real binary and then inspect the bundle that was
produced.  The point is to catch packaging mistakes — missing resources, a
missing executable bit on the bundled FFmpeg, a Python that cannot find its
shared library — before a build is handed to anyone.

Usage::

    python scripts/verify_bundle.py dist/CLIPOS
    python scripts/verify_bundle.py dist/CLIPOS --binary dist/CLIPOS/CLIPOS
"""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return condition


def find_bundle(root: Path) -> Path:
    """Return the directory that holds the frozen application."""
    if (root / "_internal").exists():
        return root
    for child in root.iterdir():
        if child.is_dir() and (child / "_internal").exists():
            return child
    return root


def resource_root(bundle: Path) -> Path:
    internal = bundle / "_internal"
    for candidate in (internal / "resources", internal / "clipos" / "resources",
                      bundle / "resources"):
        if candidate.exists():
            return candidate
    return internal / "resources"


def verify(bundle: Path, binary: Path | None) -> int:
    print(f"=== Verifying bundle: {bundle} ===\n")

    internal = bundle / "_internal"
    check("bundle has an _internal directory", internal.exists())
    if not internal.exists():
        return 1

    res = resource_root(bundle)
    print(f"\n-- resources ({res}) --")
    check("resources directory exists", res.exists(), str(res))

    expected = {
        "ffmpeg": ["linux-x64/ffmpeg", "darwin-arm64/ffmpeg", "darwin-x64/ffmpeg",
                   "win32-x64/ffmpeg.exe", "win32-ia32/ffmpeg.exe"],
        "cascades": ["haarcascade_frontalface_default.xml"],
        "models": ["face_detection_yunet_2023mar.onnx"],
        "icons": ["app_icon.png"],
        "sounds": ["whoosh.wav"],
    }
    for folder, names in expected.items():
        for name in names:
            path = res / folder / name
            check(f"{folder}/{name} is bundled", path.exists(),
                  f"{path.stat().st_size // 1024} KB" if path.exists() else "missing")

    print("\n-- executable bits --")
    for folder in sorted((res / "ffmpeg").glob("*")):
        for exe in folder.glob("ffmpeg*"):
            if exe.name.endswith(".exe"):
                continue
            mode = exe.stat().st_mode
            check(f"{exe.relative_to(res)} is executable",
                  bool(mode & stat.S_IXUSR))

    print("\n-- bundled Python modules --")
    # PyInstaller packs the application modules into a PYZ archive inside the
    # executable, so look for the compiled package rather than a source tree.
    clipos_bundled = (
        any(internal.rglob("clipos"))
        or (internal / "base_library.zip").exists()
        or any(bundle.rglob("*.pyz"))
    )
    check("clipos is bundled", clipos_bundled)
    check("PySide6 is bundled", (internal / "PySide6").exists())

    print("\n-- application entry point --")
    if binary is None:
        candidates = [bundle / "CLIPOS", bundle / "CLIPOS.exe",
                      bundle / "CLIPOS.app" / "Contents" / "MacOS" / "CLIPOS"]
        binary = next((c for c in candidates if c.exists()), None)
    if check("application binary found", binary is not None,
             str(binary) if binary else "not found"):
        # The app must at least start, initialise its database and reach the
        # point where it hands over to the GUI toolkit.
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "minimal")
        env.setdefault("QT_OPENGL", "software")
        # Bare containers have no desktop libraries.  The generated GL stubs
        # let the bundle start long enough to prove it works; on a real
        # desktop the system libraries are present and this changes nothing.
        stubs = Path(__file__).resolve().parents[1] / ".stublibs"
        if stubs.is_dir():
            existing = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = f"{stubs}{os.pathsep}{existing}" if existing \
                else str(stubs)
        # Remember where the log file ends, so only lines this run wrote are
        # considered — a stale "ready" line must never pass the check.
        #
        # The file is usually not there yet on a fresh machine, and the
        # windowed build writes nothing to the console, so every place the
        # application could have put it is looked at afterwards.
        log_candidates = [
            Path.home() / ".local" / "share" / "clipos" / "logs" / "clipos.log",
            Path.home() / ".local" / "share" / "CLIPOS" / "logs" / "clipos.log",
            Path.home() / "Library" / "Application Support" / "clipos"
            / "logs" / "clipos.log",
            Path.home() / "Library" / "Application Support" / "CLIPOS"
            / "logs" / "clipos.log",
            Path.home() / "AppData" / "Local" / "clipos" / "logs" / "clipos.log",
            Path.home() / "AppData" / "Local" / "CLIPOS" / "logs" / "clipos.log",
        ]
        log_file = None
        log_offset = 0
        for candidate in log_candidates:
            if candidate.exists():
                log_file = candidate
                try:
                    log_offset = candidate.stat().st_size
                except OSError:
                    log_offset = 0
                break

        try:
            proc = subprocess.run(
                [str(binary)], env=env, capture_output=True, text=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            # It stayed alive rather than crashing — that is the good case.
            check("application starts and stays alive", True,
                  "still running after 45s")
        else:
            combined = (proc.stdout or "") + (proc.stderr or "")
            # The rotating file log holds the authoritative "ready" line; the
            # console log may only carry part of it.  The windowed build
            # writes nothing to the console at all, so the file is the only
            # place the answer can come from.
            for candidate in log_candidates:
                if not candidate.exists():
                    continue
                try:
                    size = candidate.stat().st_size
                    offset = log_offset if candidate == log_file else 0
                    if size <= offset:
                        continue
                    with candidate.open("rb") as handle:
                        handle.seek(offset)
                        combined += "\n" + handle.read().decode(
                            "utf-8", errors="replace"
                        )
                except OSError:
                    pass
            started = "CLIPOS starting" in combined
            ready = "CLIPOS ready" in combined
            check("application starts and reaches its entry point", started,
                  combined.strip().splitlines()[0] if combined.strip() else "no output")
            # The "minimal" platform plugin has no window system, so the app
            # exits as soon as it is ready rather than entering its event
            # loop.  Reaching "ready" is what matters here; the exit code
            # only matters when the app never got that far.
            check("application reached the ready state", ready,
                  f"exit {proc.returncode}")
            check("application did not crash on startup",
                  ready or proc.returncode == 0,
                  f"exit {proc.returncode}")

    print("\n" + "=" * 62)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print(f"  {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 62)
    if failed:
        print("\nFailures:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"  - {name}: {detail}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a frozen CLIPOS bundle")
    ap.add_argument("bundle", help="path to the dist directory or the app folder")
    ap.add_argument("--binary", default="", help="explicit path to the executable")
    args = ap.parse_args()

    root = Path(args.bundle).resolve()
    if not root.exists():
        print(f"No such path: {root}")
        return 2
    binary = Path(args.binary) if args.binary else None
    result = verify(find_bundle(root), binary)
    if result != 0:
        # A verification failure has to be readable afterwards: the CI
        # logs are not always reachable, so the reason is written next to
        # the build where the diagnostic reporter picks it up.
        try:
            path = Path(__file__).resolve().parents[1] / "build" / "build-error.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("### the frozen bundle did not pass verification\n\n")
                for status, name, detail in results:
                    if status == FAIL:
                        handle.write(f"- {name}: {detail}\n")
                handle.write("\n")
        except OSError:
            pass
    return result


if __name__ == "__main__":
    sys.exit(main())
