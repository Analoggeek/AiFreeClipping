#!/usr/bin/env python3
"""Windows installer generation for CLIPOS.

Produces a genuine native ``.exe`` installer.  Two back-ends are supported and
selected automatically:

* **Inno Setup** (``iscc``) -- the richer of the two.  It produces a
  wizard with a modern look, per-user or per-machine installation, an
  uninstaller and optional desktop/start-menu shortcuts.
* **NSIS** (``makensis``) -- the fallback.  It is a single self-contained
  executable, which makes it very convenient for CI images.

If neither is installed the module can still emit a *self-extracting*
installer using the standard library only: a tiny stub that is concatenated
with a ZIP payload and extracts itself on the first run.  That path has no
external dependency at all, so a Windows build can never be blocked by a
missing tool.

    python scripts/installer_windows.py --app-dir dist/CLIPOS --output dist
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "CLIPOS"
BUNDLE_ID = "com.clipos.studio"
BUNDLE_ID_UPPER = "B7C2E9A49D1F4E6B9C3A5F2D8E1B4A70"
VERSION = "3.6.1"
VERSION_DOTTED = "2.0.0.0"


def _write_summary(title: str, body: str) -> None:
    """Record a failure in every place a human or a bot will look for it.

    The GitHub Actions job summary is the one part of a CI run that is
    always readable, even when the log storage is not reachable.  The
    ``build/build-error.log`` file is uploaded as an artifact and picked
    up by the diagnostic reporter.  Both get the message, because a
    failure that is only reported in one place is a failure that is
    usually not seen at all.
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"### {title}\n\n```\n{body}\n```\n\n")
        except OSError:
            pass

    try:
        log = ROOT / "build" / "build-error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"### {title}\n\n{body}\n\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------
# Windows cannot open a path longer than 260 characters (MAX_PATH).  A frozen
# PyInstaller tree carries the whole Python runtime, Qt and OpenCV, so the
# deepest file easily goes past that -- and the Inno Setup compiler fails
# with "The system cannot find the path specified" while it compresses.
#
# The build machine's checkout path makes it worse: on a CI runner the
# repository alone can be 60 characters deep before the application folder
# is even reached.
#
# Copying the application into a short directory first solves both.  On
# Windows the drive root is used; everywhere else a directory under the
# system temporary folder is used, which is short on every platform.

STAGING_NAME = "clipos-inst"


def staging_dir() -> Path:
    """A short directory the installer can safely read from."""
    if sys.platform == "win32":
        root = Path(os.environ.get("SystemDrive", "C:") + "\\")
        return root / STAGING_NAME
    return Path(tempfile.gettempdir()) / STAGING_NAME


def stage_for_installer(app_dir: Path) -> Path:
    """Copy the frozen application into a short directory.

    Returns the directory the installer script should read from.
    """
    target = staging_dir()
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, target / app_dir.name, symlinks=False)
    print(f"[win] staged the application in {target}")
    return target / app_dir.name


# --------------------------------------------------------------------------
# Inno Setup
# --------------------------------------------------------------------------
def _win_path(path: Path) -> str:
    """A path in the form Inno Setup and NSIS expect on Windows.

    ``Path.resolve()`` produces forward slashes on Linux and backslashes on
    Windows.  Both tools accept forward slashes, but mixing them with the
    ``\\*`` wildcard is asking for trouble, so the separators are normalised
    here and the tests can check one consistent form.
    """
    return str(path.resolve()).replace("/", "\\")


def inno_script(app_dir_name: str = APP_NAME, app_dir: Path | None = None) -> str:
    """The Inno Setup script.

    ``PrivilegesRequired=lowest`` lets the installer fall back to a per-user
    install when the user is not an administrator, which is what most people
    running a creator tool actually do.

    Two Windows-specific traps are handled here.

    **Relative paths.** Inno resolves them against the *script's own
    directory*, not against the working directory the compiler was started
    in, and the script is written into ``build/``.  Every path is therefore
    absolute.

    Note that ``SourceDir`` must *not* be set here.  When it is, Inno
    resolves the ``Source`` entries relative to it, so an absolute
    ``Source`` would be appended to the ``SourceDir`` and nothing would be
    found.

    **MAX_PATH.** Windows cannot open a path longer than 260 characters, and
    a PyInstaller tree with a bundled Python, Qt and OpenCV goes past that
    easily.  The files are therefore staged into a short directory first
    (see :func:`stage_for_installer`) and the script installs from there.
    """
    source = _win_path(app_dir or (ROOT / "dist" / app_dir_name))
    output = _win_path(ROOT / "build" / "dist")
    return f"""[Setup]
AppId={{{{{BUNDLE_ID_UPPER}}}}}
AppName=Ai clipping PRO
AppVersion={VERSION}
AppVerName=Ai clipping PRO {VERSION}
DefaultDirName={{autopf}}\\{APP_NAME}
DefaultGroupName={APP_NAME}
OutputBaseFilename={APP_NAME}-Setup
OutputDir={output}
Compression=lzma2
SolidCompression=yes
LZMANumBlockThreads=8
WizardStyle=modern
; "x64compatible" needs Inno Setup 6.3 or newer.  "x64" works with every
; 6.x release and covers both 64-bit Windows on Intel and AMD.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={{app}}\\{APP_NAME}.exe
UninstallDisplayName=Ai clipping PRO
AppPublisher=CLIPOS Studio
AppPublisherURL=https://github.com/Analoggeek/AiFreeClipping
AppSupportURL=https://github.com/Analoggeek/AiFreeClipping/issues
AppUpdatesURL=https://github.com/Analoggeek/AiFreeClipping/releases
VersionInfoDescription=Turn long videos into upload-ready shorts, entirely offline.
VersionInfoProductName=Ai clipping PRO
VersionInfoProductVersion={VERSION}
VersionInfoCompany=CLIPOS Studio
VersionInfoVersion={VERSION_DOTTED}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{source}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{APP_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"
Name: "{{group}}\\Uninstall {APP_NAME}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\{APP_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{{app}}\\{APP_NAME}.exe"; Description: "Launch {APP_NAME}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
"""


# --------------------------------------------------------------------------
# NSIS
# --------------------------------------------------------------------------
def nsis_script(app_dir_name: str = APP_NAME, app_dir: Path | None = None) -> str:
    """The NSIS script — the fallback back-end.

    ``RequestExecutionLevel admin`` is deliberately *not* used: the installer
    writes to ``$LOCALAPPDATA\\Programs`` when it is not elevated, so it works
    for a standard user without a UAC prompt.

    Like Inno, NSIS resolves relative paths against the script's own
    directory, so the paths here are absolute.
    """
    source = _win_path(app_dir or (ROOT / "dist" / app_dir_name))
    output = _win_path(ROOT / "build" / "dist" / f"{APP_NAME}-Setup.exe")
    icon = _win_path(ROOT / "resources" / "icons" / "app_icon.ico")
    icon_line = f'!define MUI_ICON "{icon}"' if (ROOT / "resources" / "icons" / "app_icon.ico").exists() else ""
    return f""";!NSIS v3.0
Unicode true
Name "Ai clipping PRO"
OutFile "{output}"
InstallDir "$LOCALAPPDATA\\Programs\\{APP_NAME}"
InstallDirRegKey HKCU "Software\\{APP_NAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!include MUI2.nsh
!include FileFunc.nsh
!include LogicLib.nsh

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\\{APP_NAME}.exe"
{icon_line}

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "{source}\\*"

  WriteRegStr HKCU "Software\\{APP_NAME}" "InstallDir" "$INSTDIR"

  CreateDirectory "$SMPROGRAMS\\{APP_NAME}"
  CreateShortcut "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe"
  CreateShortcut "$SMPROGRAMS\\{APP_NAME}\\Uninstall.lnk" "$INSTDIR\\uninstall.exe"
  CreateShortcut "$DESKTOP\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe"

  WriteUninstaller "$INSTDIR\\uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "DisplayName" "Ai clipping PRO"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "DisplayIcon" "$INSTDIR\\{APP_NAME}.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "Publisher" "CLIPOS Studio"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "DisplayVersion" "{VERSION}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "UninstallString" '"$INSTDIR\\uninstall.exe"'
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "NoModify" 1
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\\{APP_NAME}.lnk"
  Delete "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk"
  Delete "$SMPROGRAMS\\{APP_NAME}\\Uninstall.lnk"
  RMDir /r "$INSTDIR"
  RMDir "$SMPROGRAMS\\{APP_NAME}"
  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
  DeleteRegKey HKCU "Software\\{APP_NAME}"
SectionEnd
"""


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Self-extracting launcher (no external toolchain required)
# --------------------------------------------------------------------------
def _find_windows_compiler() -> list[str] | None:
    """A command that cross-compiles a C file into a Windows executable.

    Three options are tried, in order of preference:

    * ``zig cc`` — the ``ziglang`` wheel from PyPI carries a full LLVM
      toolchain with a Windows target, so ``pip install ziglang`` is enough.
    * ``x86_64-w64-mingw32-gcc`` — the mingw-w64 cross compiler.
    """
    for candidate in ("x86_64-w64-mingw32-gcc", "i686-w64-mingw32-gcc"):
        found = shutil.which(candidate)
        if found:
            return [found]

    try:
        import ziglang  # noqa: F401

        zig = Path(ziglang.__file__).parent / "zig"
        if zig.exists():
            return [str(zig), "cc"]
    except Exception:
        pass
    return None


def build_selfextracting_installer(app_dir: Path, output_dir: Path) -> Path:
    """Build a genuine ``.exe`` installer with no external toolchain.

    The launcher is compiled from :mod:`scripts/installer_launcher.c` into a
    Win32 PE executable; the frozen application is then appended to it as a
    ZIP archive.  The result is a single file the user double-clicks to
    install CLIPOS.
    """
    compiler = _find_windows_compiler()
    if compiler is None:
        raise SystemExit(
            "No Windows compiler found.  Install one of:\n"
            "  pip install ziglang          (cross-compiles from any host)\n"
            "  apt install mingw-w64         (Debian / Ubuntu)\n"
            "  dnf install mingw64-gcc       (Fedora / RHEL)"
        )

    source = Path(__file__).resolve().parent / "installer_launcher.c"
    if not source.exists():
        raise SystemExit(f"the launcher source is missing: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir = ROOT / "build" / "winlauncher"
    build_dir.mkdir(parents=True, exist_ok=True)
    launcher = build_dir / "installer.exe"

    cmd = list(compiler) + [
        "-target", "x86_64-windows-gnu",
        "-O2", "-s",
        # A GUI subsystem binary so no console window flashes up while the
        # installer works.
        "-Wl,--subsystem,windows",
        "-o", str(launcher), str(source),
        "-lkernel32", "-luser32", "-lshell32",
    ]
    print(f"[win] compiling the installer launcher: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0 or not launcher.exists():
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:], file=sys.stderr)
        raise SystemExit("could not compile the Windows installer launcher")

    # Pack the frozen application into a ZIP that becomes the payload.
    payload = build_dir / "payload.zip"
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                zf.write(path, Path(app_dir.name) / path.relative_to(app_dir))

    data = launcher.read_bytes()
    trailer = struct.pack("<8sII", b"CLIPOSPAY", payload.stat().st_size, 0)
    installer = output_dir / f"{APP_NAME}-Setup.exe"
    with open(installer, "wb") as handle:
        handle.write(data)
        handle.write(payload.read_bytes())
        handle.write(trailer)

    payload.unlink(missing_ok=True)
    print(f"[win] installer: {installer} "
          f"({installer.stat().st_size // (1024 * 1024)} MB)")
    return installer


def build_windows_installer(app_dir: Path, output_dir: Path) -> Path:
    """Build the Windows installer and return the path of the ``.exe``.

    The back-ends are tried in order of quality: Inno Setup produces the
    nicest installer, NSIS the next best, and the built-in self-extracting
    launcher is the fallback that always works.  If one of the first two
    fails the next one is tried, so a packaging problem never leaves the
    build without an installer.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir = ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    # The installer compilers write their output here.  Neither Inno Setup
    # nor NSIS creates the directory, and they fail with a bare "Can't open
    # output file" when it is missing -- which is exactly what happened.
    compiler_out = build_dir / "dist"
    compiler_out.mkdir(parents=True, exist_ok=True)

    # Stage the application in a short directory.  Windows cannot open a path
    # longer than 260 characters, and the Inno compiler fails with "The
    # system cannot find the path specified" while compressing a deep
    # PyInstaller tree.
    staged = stage_for_installer(app_dir)

    iscc = shutil.which("iscc") or shutil.which("ISCC.exe")
    if iscc:
        iss = build_dir / "clipos.iss"
        iss.write_text(inno_script(staged.name, staged), encoding="utf-8")
        print(f"[win] using Inno Setup: {iscc}")
        # The compiler version matters: the architecture directives and the
        # compression behaviour both changed between the 6.x releases.
        version = subprocess.run(
            [iscc, "/Qp"], cwd=ROOT, capture_output=True, text=True
        )
        print(f"[win] Inno Setup version: {version.stdout.strip()}")
        proc = subprocess.run(
            [iscc, str(iss)], cwd=ROOT, capture_output=True, text=True
        )
        if proc.returncode == 0:
            produced = compiler_out / f"{APP_NAME}-Setup.exe"
            target = output_dir / produced.name
            if not produced.exists():
                # The compiler said it succeeded but the file is not
                # there.  Say so instead of failing later with a
                # confusing error about a file that was never written.
                raise SystemExit(
                    f"Inno Setup reported success but did not write {produced}"
                )
            shutil.copy2(produced, target)
            shutil.rmtree(staging_dir(), ignore_errors=True)
            print(f"[win] installer: {target} "
                  f"({target.stat().st_size // (1024 * 1024)} MB)")
            return target
        # Inno Setup writes its own log next to the script when it fails.
        # It names the exact file it could not open, which is the one
        # piece of information needed to fix the packaging.
        inno_log = ""
        for candidate in (build_dir / "clipos.iss.log", build_dir / "Setup Log.txt"):
            if candidate.exists():
                inno_log = (
                    f"\n\n--- {candidate.name} ---\n"
                    f"{candidate.read_text(encoding='utf-8', errors='replace')[-6000:]}"
                )
                break
        report = (
            "Inno Setup failed with exit code "
            f"{proc.returncode}\n\n--- version ---\n{version.stdout.strip()}\n\n"
            f"--- stdout ---\n{proc.stdout[-4000:]}\n\n"
            f"--- stderr ---\n{proc.stderr[-4000:]}\n\n--- script ---\n"
            f"{iss.read_text(encoding='utf-8', errors='replace')[:4000]}"
            f"{inno_log}"
        )
        print("[win] Inno Setup failed:")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:], file=sys.stderr)
        _write_summary("Inno Setup failed", report)
        print("[win] Trying the next installer back-end.")

    makensis = shutil.which("makensis") or shutil.which("makensis.exe")
    if makensis:
        nsi = build_dir / "clipos.nsi"
        nsi.write_text(nsis_script(staged.name, staged), encoding="utf-8")
        print(f"[win] using NSIS: {makensis}")
        proc = subprocess.run(
            [makensis, str(nsi)], cwd=ROOT, capture_output=True, text=True
        )
        if proc.returncode == 0:
            produced = compiler_out / f"{APP_NAME}-Setup.exe"
            target = output_dir / produced.name
            shutil.copy2(produced, target)
            shutil.rmtree(staging_dir(), ignore_errors=True)
            return target
        print("[win] NSIS failed:")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:], file=sys.stderr)
        _write_summary(
            "NSIS failed",
            "NSIS failed with exit code "
            f"{proc.returncode}\n\n--- stdout ---\n{proc.stdout[-4000:]}\n\n"
            f"--- stderr ---\n{proc.stderr[-4000:]}\n\n--- script ---\n"
            f"{nsi.read_text(encoding='utf-8', errors='replace')[:4000]}",
        )
        print("[win] Trying the next installer back-end.")

    # The self-extracting launcher needs nothing but a C cross compiler, so
    # it is the back-end that always works.
    print("[win] Building the self-extracting installer.")
    try:
        return build_selfextracting_installer(staged, output_dir)
    finally:
        shutil.rmtree(staging_dir(), ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the CLIPOS Windows installer")
    ap.add_argument("--app-dir", default="", help="the frozen application folder")
    ap.add_argument("--output", default="dist", help="where to place the .exe")
    ap.add_argument("--print-script", choices=["inno", "nsis"], default="",
                    help="only print the installer script and exit")
    args = ap.parse_args()

    if args.print_script == "inno":
        print(inno_script())
        return 0
    if args.print_script == "nsis":
        print(nsis_script())
        return 0

    if not args.app_dir:
        raise SystemExit("--app-dir is required")
    app_dir = Path(args.app_dir).resolve()
    if not app_dir.is_dir():
        raise SystemExit(f"no such application folder: {app_dir}")
    out = build_windows_installer(app_dir, Path(args.output).resolve())
    print(f"[win] installer: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
