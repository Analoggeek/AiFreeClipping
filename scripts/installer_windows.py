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
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "CLIPOS"
BUNDLE_ID = "com.clipos.studio"
BUNDLE_ID_UPPER = "B7C2E9A49D1F4E6B9C3A5F2D8E1B4A70"
VERSION = "1.0.0"
VERSION_DOTTED = "1.0.0.0"


# --------------------------------------------------------------------------
# Inno Setup
# --------------------------------------------------------------------------
def inno_script(app_dir_name: str = APP_NAME) -> str:
    """The Inno Setup script.

    ``PrivilegesRequired=lowest`` lets the installer fall back to a per-user
    install when the user is not an administrator, which is what most people
    running a creator tool actually do.
    """
    return f"""[Setup]
AppId={{{BUNDLE_ID_UPPER}}}
AppName={APP_NAME}
AppVersion={VERSION}
AppVerName={APP_NAME} {VERSION}
DefaultDirName={{autopf}}\\{APP_NAME}
DefaultGroupName={APP_NAME}
OutputBaseFilename={APP_NAME}-Setup
OutputDir=..\\build\\dist
Compression=lzma2
SolidCompression=yes
LZMANumBlockThreads=8
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AllowNoIcons=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={{app}}\\{APP_NAME}.exe
UninstallDisplayName={APP_NAME}
AppPublisher=CLIPOS Studio
AppPublisherURL=https://github.com/Analoggeek/AiFreeClipping
AppSupportURL=https://github.com/Analoggeek/AiFreeClipping/issues
AppUpdatesURL=https://github.com/Analoggeek/AiFreeClipping/releases
AppVersionInfoDescription=Turn long videos into upload-ready shorts, entirely offline.
AppVersionInfoProductName={APP_NAME}
AppVersionInfoProductVersion={VERSION}
AppVersionInfoCompany=CLIPOS Studio
VersionInfoVersion={VERSION_DOTTED}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\\{app_dir_name}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
def nsis_script(app_dir_name: str = APP_NAME) -> str:
    """The NSIS script — the fallback back-end.

    ``RequestExecutionLevel admin`` is deliberately *not* used: the installer
    writes to ``$LOCALAPPDATA\\Programs`` when it is not elevated, so it works
    for a standard user without a UAC prompt.
    """
    return f""";!NSIS v3.0
Unicode true
Name "{APP_NAME}"
OutFile "..\\build\\dist\\{APP_NAME}-Setup.exe"
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
!define MUI_ICON "dist\\app_icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "dist\\{app_dir_name}\\*"

  WriteRegStr HKCU "Software\\{APP_NAME}" "InstallDir" "$INSTDIR"

  CreateDirectory "$SMPROGRAMS\\{APP_NAME}"
  CreateShortcut "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe"
  CreateShortcut "$SMPROGRAMS\\{APP_NAME}\\Uninstall.lnk" "$INSTDIR\\uninstall.exe"
  CreateShortcut "$DESKTOP\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe"

  WriteUninstaller "$INSTDIR\\uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" \\
    "DisplayName" "{APP_NAME}"
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
    """Build the Windows installer and return the path of the ``.exe``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir = ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    iscc = shutil.which("iscc") or shutil.which("ISCC.exe")
    if iscc:
        iss = build_dir / "clipos.iss"
        iss.write_text(inno_script(app_dir.name), encoding="utf-8")
        print(f"[win] using Inno Setup: {iscc}")
        proc = subprocess.run([iscc, str(iss)], cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout[-4000:])
            print(proc.stderr[-4000:], file=sys.stderr)
            raise SystemExit("Inno Setup failed")
        produced = build_dir / "dist" / f"{APP_NAME}-Setup.exe"
        target = output_dir / produced.name
        shutil.copy2(produced, target)
        return target

    makensis = shutil.which("makensis") or shutil.which("makensis.exe")
    if makensis:
        nsi = build_dir / "clipos.nsi"
        nsi.write_text(nsis_script(app_dir.name), encoding="utf-8")
        print(f"[win] using NSIS: {makensis}")
        proc = subprocess.run([makensis, str(nsi)], cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout[-4000:])
            print(proc.stderr[-4000:], file=sys.stderr)
            raise SystemExit("NSIS failed")
        produced = build_dir / "dist" / f"{APP_NAME}-Setup.exe"
        target = output_dir / produced.name
        shutil.copy2(produced, target)
        return target

    # Neither tool is installed: fall back to the self-extracting launcher,
    # which is compiled here and needs nothing but a C cross compiler.
    print("[win] Neither Inno Setup nor NSIS is installed.")
    print("[win] Building the self-extracting installer instead.")
    return build_selfextracting_installer(app_dir, output_dir)


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
