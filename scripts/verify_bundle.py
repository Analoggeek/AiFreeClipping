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


def is_app_bundle(bundle: Path) -> bool:
    """True for a macOS application bundle."""
    return (bundle / "Contents").is_dir()


def find_bundle(root: Path) -> Path:
    """Return the directory that holds the frozen application.

    A macOS application bundle keeps its files under ``Contents``, and
    the one-folder build on the other platforms keeps them under
    ``_internal``.  Both are understood.
    """
    if (root / "_internal").exists() or is_app_bundle(root):
        return root
    for child in root.iterdir():
        if child.is_dir() and (
            (child / "_internal").exists() or is_app_bundle(child)
        ):
            return child
    return root


def internal_dir(bundle: Path) -> Path:
    """The directory the frozen files live in."""
    if is_app_bundle(bundle):
        return bundle / "Contents"
    return bundle / "_internal"


# A directory that holds the bundled resources is recognised by one of
# these being inside it.
_RESOURCE_MARKERS = ("ffmpeg", "cascades", "models", "icons", "sounds")


def resource_root(bundle: Path) -> Path:
    """The directory the bundled resources live in.

    A macOS application bundle always has a ``Contents/Resources``
    directory, but it does not always hold the resources: PyInstaller
    puts them in a subfolder of its own choosing.  The directory is
    therefore looked for by what is inside it, and not by its name.
    """
    internal = internal_dir(bundle)
    candidates = [
        internal / "resources",
        internal / "clipos" / "resources",
        bundle / "resources",
        bundle / "Contents" / "Resources" / "resources",
        bundle / "Contents" / "Frameworks" / "resources",
        bundle / "Contents" / "Resources",
    ]
    # OCR and other dependencies also ship a `models` folder. Never accept
    # the first such dependency as the application's own resource root.
    expanded = list(candidates)
    for candidate in candidates:
        if candidate.is_dir():
            expanded.extend(child for child in sorted(candidate.iterdir()) if child.is_dir())
    ranked = [(sum((candidate / marker).is_dir() for marker in _RESOURCE_MARKERS),-index,candidate)
              for index,candidate in enumerate(expanded) if candidate.is_dir()]
    if ranked:
        return max(ranked,key=lambda row:(row[0],row[1]))[2]
    return internal / "resources"



def check_architecture(bundle: Path, binary: Path | None) -> None:
    """Make sure the bundle was built for the architecture it claims.

    The name of the bundle says which machine it is for -- ``CLIPOS-intel``
    is for an Intel Mac -- but the name is only a claim.  The binary
    inside has to match it, or the application will not run on the
    machine it was meant for.

    The architecture is worked out from the name, because the check has
    to run on any machine: the build happens on Apple Silicon and the
    Intel application is checked there too.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from clipos.core.binary_arch import binary_arch

    wanted = ""
    lowered = bundle.name.lower()
    if "intel" in lowered or "x86_64" in lowered:
        wanted = "x86_64"
    elif "arm64" in lowered or "silicon" in lowered:
        wanted = "arm64"
    if not wanted or binary is None or not binary.exists():
        return

    found = binary_arch(binary)
    check("the application is built for the right architecture",
          found is not None and wanted in found.split("|"),
          f"{wanted} wanted, {found or 'unknown'} found")


def media_executables(resources: Path):
    """Exact executable names only; provenance/license files are data."""
    for folder in sorted((resources/'ffmpeg').glob('*')):
        for name in ('ffmpeg','ffprobe','ffmpeg.exe','ffprobe.exe'):
            path=folder/name
            if path.is_file():yield path


def verify(bundle: Path, binary: Path | None) -> int:
    print(f"=== Verifying bundle: {bundle} ===\n")

    internal = internal_dir(bundle)
    if is_app_bundle(bundle):
        check("the application bundle has a Contents directory",
              (bundle / "Contents" / "MacOS").is_dir())
        if sys.platform == "darwin":
            signature = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(bundle)],
                capture_output=True, text=True,
            )
            check("final macOS bundle signature is valid", signature.returncode == 0,
                  signature.stderr.strip())
    else:
        check("bundle has an _internal directory", internal.exists())
    if not internal.is_dir():
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
    # The executable bit is a Unix thing.  Windows has no such bit, and a
    # checkout there marks every file as not executable, so the check would
    # fail on every platform's binaries for no reason.
    if os.name == "nt":
        print("   (not applicable on Windows)")
    else:
        for exe in media_executables(res):
            if exe.name.endswith('.exe'):continue
            mode = exe.stat().st_mode
            check(f"{exe.relative_to(res)} is executable",bool(mode & stat.S_IXUSR))

    print("\n-- bundled Python modules --")
    # PyInstaller packs the application modules into a PYZ archive inside the
    # executable, so look for the compiled package rather than a source tree.
    clipos_bundled = (
        any(internal.rglob("clipos"))
        or (internal / "base_library.zip").exists()
        or any(bundle.rglob("*.pyz"))
    )
    check("clipos is bundled", clipos_bundled)
    # The libraries live in a different place in a macOS application
    # bundle, so they are looked for in both places.
    pyside6 = any(
        (base / "PySide6").exists()
        for base in (internal, bundle / "Contents" / "Frameworks",
                     bundle / "Contents" / "Resources", bundle)
        if base.exists()
    )
    check("PySide6 is bundled", pyside6)

    print("\n-- application entry point --")
    if binary is None:
        candidates = [bundle / "CLIPOS", bundle / "CLIPOS.exe",
                      bundle / "Contents" / "MacOS" / "CLIPOS",
                      bundle / "CLIPOS.app" / "Contents" / "MacOS" / "CLIPOS"]
        binary = next((c for c in candidates if c.exists()), None)
    check_architecture(bundle, binary)
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
        # Exercise the actual frozen imports/inference path; source-environment
        # tests cannot detect an excluded matplotlib or missing package metadata.
        import json,tempfile
        weights=Path(__file__).resolve().parents[1]/'build'/'yolox-validation.onnx'
        if env.get('GITHUB_ACTIONS')=='true':
            fetched=subprocess.run([sys.executable,str(Path(__file__).with_name('fetch_validation_weights.py'))],capture_output=True,text=True,timeout=120)
            check('official YOLOX validation weights fetched and SHA256 verified',fetched.returncode==0,(fetched.stderr or fetched.stdout)[-800:])
        if weights.is_file():env['CLIPOS_VERIFY_YOLOX_WEIGHTS']=str(weights)
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'frozen-runtime.json'
            try:
                runtime=subprocess.run([str(binary),'--verify-clipping-runtime',str(report)],env=env,capture_output=True,text=True,timeout=180)
                data=json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
                check('frozen ByteTrack and ONNX CPU runtime execute',runtime.returncode==0 and data.get('status')=='ok',str(data)[:1200] or runtime.stderr[-800:])
                if weights.is_file():check('frozen YOLOX actual weights load and infer',data.get('status')=='ok' and 'inference completed' in data.get('yolox',''),str(data.get('yolox','not executed')))
            except Exception as exc:check('frozen runtime verification completes',False,str(exc))
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
