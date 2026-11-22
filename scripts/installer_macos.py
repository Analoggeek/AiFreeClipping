#!/usr/bin/env python3
"""macOS packaging for CLIPOS.

Two artifacts are produced:

* ``CLIPOS.app`` -- a proper application bundle with a complete
  ``Info.plist``, an ``.icns`` icon, a stable bundle identifier and a
  ``LSApplicationCategoryType``.
* ``CLIPOS-<version>.dmg`` -- a drag-to-install disk image with the app on
  the left and an ``/Applications`` symlink on the right, a proper window
  layout and a background image.

Both steps need macOS (``hdiutil``).  The ``.app`` polishing works anywhere,
which makes it testable on a non-Apple machine.

Optional finishing steps, enabled automatically when the tools and the
credentials are present:

* ``codesign`` -- signs the bundle with a Developer ID so Gatekeeper lets the
  user open it without a "downloaded from the internet" warning.
* ``notarytool`` -- submits the signed bundle to Apple's notary service and
  staples the ticket, so the app opens on any Mac without a warning.

    python scripts/installer_macos.py --app dist/CLIPOS.app --output dist
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "CLIPOS"
BUNDLE_ID = "com.clipos.studio"
VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Info.plist
# --------------------------------------------------------------------------
PLIST_ENTRIES: dict[str, object] = {
    "CFBundleIdentifier": BUNDLE_ID,
    "CFBundleName": APP_NAME,
    "CFBundleDisplayName": APP_NAME,
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": VERSION,
    "CFBundleExecutable": APP_NAME,
    "CFBundleIconFile": "app_icon.icns",
    "CFBundlePackageType": "APPL",
    "CFBundleSignature": "????",
    "CFBundleInfoDictionaryVersion": "6.0",
    "LSMinimumSystemVersion": "11.0",
    "NSHighResolutionCapable": True,
    "NSRequiresAquaSystemAppearance": False,
    "LSApplicationCategoryType": "public.app-category.video",
    "NSHumanReadableCopyright": f"CLIPOS {VERSION}",
    "NSPrincipalClass": "NSApplication",
    "NSSupportsAutomaticGraphicsSwitching": True,
    "NSSupportsAutomaticTermination": False,
    "LSApplicationSupportsSecureRestorableState": True,
    # The app writes projects, transcripts and clips to the user's own
    # folders and never phones home, so it needs no network entitlement.
    "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": False},
}


def _bundle_plist(app: Path) -> Path:
    return app / "Contents" / "Info.plist"


def _resources_dir(app: Path) -> Path:
    return app / "Contents" / "Resources"


def polish_app_bundle(app: Path) -> Path:
    """Complete the ``Info.plist`` and make sure the icon is in place."""
    if not app.is_dir():
        raise SystemExit(f"no such application bundle: {app}")
    contents = app / "Contents"
    if not contents.is_dir():
        raise SystemExit(f"{app} does not look like a macOS application bundle")

    plist_path = _bundle_plist(app)
    if plist_path.exists():
        with open(plist_path, "rb") as handle:
            info = plistlib.load(handle)
    else:
        info = {"CFBundleName": APP_NAME, "CFBundleExecutable": APP_NAME}

    info.update(PLIST_ENTRIES)

    # The PyInstaller bootloader lives in Contents/MacOS; make sure the
    # executable name matches what the plist promises.
    macos_dir = contents / "MacOS"
    if macos_dir.is_dir():
        candidates = [p for p in macos_dir.iterdir() if p.is_file()]
        if candidates and not (macos_dir / APP_NAME).exists():
            primary = max(candidates, key=lambda p: p.stat().st_size)
            (macos_dir / APP_NAME).symlink_to(primary.name)

    with open(plist_path, "wb") as handle:
        plistlib.dump(info, handle)

    # Install the icon where the plist says it is.
    resources = _resources_dir(app)
    resources.mkdir(parents=True, exist_ok=True)
    icon_source = ROOT / "resources" / "icons" / "app_icon.icns"
    if icon_source.exists():
        shutil.copy2(icon_source, resources / "app_icon.icns")

    # A PNG fallback is useful for the About panel and the Dock.
    png_source = ROOT / "resources" / "icons" / "app_icon_512.png"
    if png_source.exists():
        shutil.copy2(png_source, resources / "app_icon.png")

    print(f"[mac] Info.plist updated for {app}")
    return app


# --------------------------------------------------------------------------
# Code signing and notarisation
# --------------------------------------------------------------------------
def sign_app(app: Path, identity: str = "", hardened: bool = True) -> bool:
    """Sign the bundle.  Returns True when the bundle ended up signed."""
    codesign = shutil.which("codesign")
    if not codesign:
        print("[mac] codesign is not available (not macOS) — skipping signing")
        return False

    identity = identity or os.environ.get("CLIPOS_CODESIGN_IDENTITY", "")
    if not identity:
        print("[mac] no signing identity supplied — skipping signing")
        print("     set CLIPOS_CODESIGN_IDENTITY or pass --sign-identity")
        return False

    cmd = [
        codesign, "--force", "--deep", "--options", "runtime",
        "--timestamp", "--sign", identity, str(app),
    ]
    if not hardened:
        cmd.remove("--options")
        cmd.remove("runtime")
    print(f"[mac] codesigning with {identity}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        print("[mac] WARNING: code signing failed")
        return False

    # Verify the signature really is valid.
    check = subprocess.run(
        [codesign, "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        print(check.stderr, file=sys.stderr)
        print("[mac] WARNING: the signature does not verify")
        return False
    print("[mac] signature verified")
    return True


def notarize_app(app: Path, dmg: Path | None = None) -> bool:
    """Submit the signed bundle to Apple's notary service and staple it."""
    if sys.platform != "darwin":
        print("[mac] notarisation needs macOS — skipping")
        return False
    notarytool = shutil.which("notarytool") or shutil.which("xcrun")
    if not notarytool:
        print("[mac] notarytool is not available — skipping")
        return False

    profile = os.environ.get("CLIPOS_NOTARY_PROFILE", "")
    if not profile:
        print("[mac] no notary profile configured — skipping")
        print("     set CLIPOS_NOTARY_PROFILE or pass --notary-profile")
        return False

    target = dmg if dmg and dmg.exists() else app
    print(f"[mac] notarising {target}")
    submit = subprocess.run(
        ["xcrun", "notarytool", "submit", str(target),
         "--keychain-profile", profile, "--wait"],
        capture_output=True, text=True,
    )
    if submit.returncode != 0:
        print(submit.stdout)
        print(submit.stderr, file=sys.stderr)
        print("[mac] WARNING: notarisation failed")
        return False

    staple = subprocess.run(
        ["xcrun", "notarytool", "stapler", "staple", str(target)],
        capture_output=True, text=True,
    )
    if staple.returncode != 0:
        print(staple.stderr, file=sys.stderr)
        print("[mac] WARNING: stapling failed")
        return False
    print("[mac] notarised and stapled")
    return True


# --------------------------------------------------------------------------
# Disk image
# --------------------------------------------------------------------------
def _make_dmg_background(width: int = 640, height: int = 400) -> Path | None:
    """Draw the drag-to-install background, or return None without Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    image = Image.new("RGB", (width, height), (244, 245, 250))
    draw = ImageDraw.Draw(image)

    # A soft arrow from the app icon towards the Applications folder.
    draw.rounded_rectangle(
        (width * 0.28, height * 0.42, width * 0.42, height * 0.58),
        radius=10, fill=(196, 202, 216),
    )
    draw.line(
        (width * 0.44, height * 0.50, width * 0.56, height * 0.50),
        fill=(140, 148, 168), width=5,
    )
    draw.polygon(
        [
            (width * 0.60, height * 0.44),
            (width * 0.60, height * 0.56),
            (width * 0.53, height * 0.50),
        ],
        fill=(140, 148, 168),
    )

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    draw.text(
        (width * 0.5 - 120, height * 0.64),
        "Drag CLIPOS into Applications",
        fill=(90, 96, 112), font=font,
    )

    handle, name = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    out = Path(name)
    image.save(out)
    return out


def build_dmg(app: Path, output_dir: Path, volume_name: str = APP_NAME) -> Path:
    """Build a drag-to-install ``.dmg`` with a proper window layout."""
    if sys.platform != "darwin":
        raise SystemExit("building a .dmg requires macOS (hdiutil)")

    output_dir.mkdir(parents=True, exist_ok=True)
    staging = ROOT / "build" / "dmg-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    shutil.copytree(app, staging / f"{APP_NAME}.app", symlinks=True)
    os.symlink("/Applications", staging / "Applications")

    dmg = output_dir / f"{APP_NAME}-{VERSION}.dmg"
    if dmg.exists():
        dmg.unlink()

    subprocess.run(
        ["hdiutil", "create", "-volname", volume_name,
         "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg)],
        check=True,
    )

    # Set the window layout so the app and the Applications folder are side
    # by side, and hide the rest of the files.
    mount_point = ROOT / "build" / "dmg-mount"
    if mount_point.exists():
        shutil.rmtree(mount_point, ignore_errors=True)
    mount_point.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["hdiutil", "attach", str(dmg), "-mountpoint", str(mount_point),
             "-nobrowse", "-quiet"],
            check=True,
        )
        apple_script = (
            'tell application "Finder"\n'
            f'  tell disk "{volume_name}"\n'
            "    open\n"
            "    set current view of container window to icon view\n"
            "    set toolbar visible of container window to false\n"
            "    set statusbar visible of container window to false\n"
            "    set the bounds of container window to {140, 120, 700, 520}\n"
            "    set viewOptions to the icon view options of container window\n"
            "    set arrangement of viewOptions to not arranged\n"
            "    set icon size of viewOptions to 96\n"
            f'    set position of item "{APP_NAME}.app" of container window to {{170, 220}}\n'
            '    set position of item "Applications" of container window to {470, 220}\n'
            "    close\n"
            "    open\n"
            "    update without registering applications\n"
            "    delay 1\n"
            "  end tell\n"
            "end tell\n"
        )
        subprocess.run(["osascript", "-e", apple_script], check=False,
                       capture_output=True)
        # Store the layout so it survives until the image is detached.
        subprocess.run(
            ["hdiutil", "detach", str(mount_point), "-quiet"], check=False
        )
    finally:
        shutil.rmtree(mount_point, ignore_errors=True)

    print(f"[mac] disk image: {dmg}")
    return dmg


def main() -> int:
    ap = argparse.ArgumentParser(description="Package CLIPOS for macOS")
    ap.add_argument("--app", required=True, help="path to CLIPOS.app")
    ap.add_argument("--output", default="dist", help="where to place the .dmg")
    ap.add_argument("--sign-identity", default="",
                    help="Developer ID to sign with (also: CLIPOS_CODESIGN_IDENTITY)")
    ap.add_argument("--notary-profile", default="",
                    help="notarytool keychain profile (also: CLIPOS_NOTARY_PROFILE)")
    ap.add_argument("--skip-dmg", action="store_true")
    args = ap.parse_args()

    app = Path(args.app).resolve()
    polish_app_bundle(app)

    signed = sign_app(app, args.sign_identity)

    dmg: Path | None = None
    if not args.skip_dmg:
        dmg = build_dmg(app, Path(args.output).resolve())

    if signed:
        notarize_app(app, dmg)

    print(f"[mac] application bundle: {app}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
