"""Build native Linux installers for CLIPOS.

Two artefacts are produced:

* a ``.deb`` package for Debian and Ubuntu, and
* a ``.rpm`` package for Fedora, RHEL and openSUSE.

Both install the frozen application into ``/opt/CLIPOS`` and add a launcher
to ``/usr/share/applications`` so the app appears in the system menu and can
be started by double-clicking, plus an icon in ``/usr/share/icons``.

Nothing is downloaded at install time and nothing is fetched at run time: the
package carries the application, the bundled FFmpeg binaries, the face
detection models and the sound effects, so the application is fully offline
straight after installation.

The ``.deb`` is built with ``dpkg-deb`` and the ``.rpm`` with ``rpmbuild``;
both are standard tools on their respective distributions.
"""
from __future__ import annotations

import gzip
import shutil
import subprocess
import textwrap
from pathlib import Path

APP_NAME = "CLIPOS"
BUNDLE_ID = "com.clipos.studio"
VENDOR = "CLIPOS"
MAINTAINER = "CLIPOS <support@clipos.local>"
DESCRIPTION = (
    "AI Automatic Video Clipping Studio. Turn long videos into upload-ready "
    "shorts for YouTube Shorts, Instagram Reels and TikTok. Runs entirely on "
    "your own machine."
)
HOMEPAGE = "https://github.com/Analoggeek/AiFreeClipping"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(str(c) for c in cmd)
    print(f"  $ {printable}")
    result = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True,
                            text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"command failed ({result.returncode}): {cmd}\n"
            f"{result.stdout}\n{result.stderr}"
        )


def _desktop_entry() -> str:
    return textwrap.dedent(
        f"""\
        [Desktop Entry]
        Type=Application
        Name=Ai clipping PRO
        GenericName=Video Clipping Studio
        Comment=Turn long videos into upload-ready shorts, entirely offline
        Exec=/opt/{APP_NAME}/{APP_NAME} %f
        Icon={APP_NAME}
        Terminal=false
        Categories=AudioVideo;Video;AudioVideoEditing;Graphics;
        Keywords=video;clip;shorts;reels;tiktok;youtube;ai;editing;
        StartupWMClass={APP_NAME}
        StartupNotify=true
        MimeType=video/mp4;video/quicktime;video/x-matroska;video/x-msvideo;video/webm;video/x-m4v;
        """
    )


def _stage(app_dir: Path, staging: Path) -> None:
    """Lay the application out the way a native package expects it."""
    opt = staging / "opt" / APP_NAME
    opt.mkdir(parents=True, exist_ok=True)

    print(f"  copying {app_dir} -> {opt}")
    for item in app_dir.iterdir():
        target = opt / item.name
        if item.is_dir():
            shutil.copytree(item, target, symlinks=True)
        else:
            shutil.copy2(item, target)

    # The launcher must be executable for the menu entry to work.
    launcher = opt / APP_NAME
    if launcher.exists():
        launcher.chmod(0o755)

    apps = staging / "usr" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / f"{APP_NAME}.desktop").write_text(_desktop_entry(), encoding="utf-8")

    icons = staging / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
    icons.mkdir(parents=True, exist_ok=True)
    source_icon = Path(__file__).resolve().parents[1] / "resources" / "icons" / "app_icon_512.png"
    if source_icon.exists():
        shutil.copy2(source_icon, icons / f"{APP_NAME}.png")
    else:
        fallback = (Path(__file__).resolve().parents[1] / "resources" / "icons"
                    / "app_icon.png")
        if fallback.exists():
            shutil.copy2(fallback, icons / f"{APP_NAME}.png")

    # Icons for the other sizes make the app look right in every launcher.
    for size in (256, 128, 64, 48, 32, 16):
        target_dir = (staging / "usr" / "share" / "icons" / "hicolor"
                      / f"{size}x{size}" / "apps")
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_icon.exists():
            shutil.copy2(source_icon, target_dir / f"{APP_NAME}.png")

    meta = staging / "usr" / "share" / "applications" / f"{APP_NAME}.desktop"
    meta.chmod(0o644)


def build_deb(app_dir: Path, version: str, out_dir: Path) -> Path:
    """Build a Debian/Ubuntu package."""
    if not shutil.which("dpkg-deb"):
        raise SystemExit(
            "dpkg-deb was not found.  Install the dpkg package "
            "(Debian/Ubuntu: sudo apt install dpkg) and try again."
        )

    staging = out_dir / f"deb-staging-{APP_NAME}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    print("[linux] staging the application ...")
    _stage(app_dir, staging)

    control = staging / "DEBIAN"
    control.mkdir(parents=True, exist_ok=True)
    # Built line by line: a multi-line Description would defeat the common
    # prefix calculation that textwrap.dedent relies on.
    control_lines = [
        f"Package: {APP_NAME.lower()}",
        f"Version: {version}",
        "Section: video",
        "Priority: optional",
        "Architecture: amd64",
        f"Installed-Size: {int(_dir_size(staging) / 1024)}",
        f"Maintainer: {MAINTAINER}",
        f"Homepage: {HOMEPAGE}",
        f"Description: {DESCRIPTION}",
    ]
    (control / "control").write_text(
        "\n".join(control_lines) + "\n", encoding="utf-8"
    )

    # The installer removes the files it owns, so uninstalling is clean.
    (control / "postinst").write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            set -e
            if [ -f /usr/share/icons/hicolor/512x512/apps/{APP_NAME}.png ]; then
                if command -v gtk-update-icon-cache >/dev/null 2>&1; then
                    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
                fi
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    (control / "prerm").write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            set -e
            if command -v update-desktop-database >/dev/null 2>&1; then
                update-desktop-database -q /usr/share/applications || true
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    (control / "postrm").write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            set -e
            if [ "$1" = "remove" ]; then
                if command -v gtk-update-icon-cache >/dev/null 2>&1; then
                    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
                fi
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    for script in ("postinst", "prerm", "postrm"):
        (control / script).chmod(0o755)

    out_path = out_dir / f"{APP_NAME}_{version}_amd64.deb"
    if out_path.exists():
        out_path.unlink()
    print(f"[linux] building {out_path.name} ...")
    _run(["dpkg-deb", "--build", "--root-owner-group", str(staging), str(out_path)])
    _run(["dpkg-deb", "--info", str(out_path)])
    shutil.rmtree(staging, ignore_errors=True)
    return out_path


def build_rpm(app_dir: Path, version: str, out_dir: Path) -> Path:
    """Build an RPM package for Fedora/RHEL/openSUSE."""
    if not shutil.which("rpmbuild"):
        raise SystemExit(
            "rpmbuild was not found.  Install the rpm-build package "
            "(Fedora/RHEL: sudo dnf install rpm-build) and try again."
        )

    buildroot = out_dir / "rpm-build"
    shutil.rmtree(buildroot, ignore_errors=True)
    buildroot.mkdir(parents=True)

    print("[linux] staging the application ...")
    staging = buildroot / "staging"
    _stage(app_dir, staging)

    spec = buildroot / f"{APP_NAME}.spec"
    spec.write_text(
        textwrap.dedent(
            f"""\
            %define _bin /opt/{APP_NAME}
            Name: {APP_NAME}
            Version: {version}
            Release: 1
            Summary: AI Automatic Video Clipping Studio
            License: Proprietary
            URL: {HOMEPAGE}

            %description
            {DESCRIPTION}

            %files
            /opt/{APP_NAME}
            /usr/share/applications/{APP_NAME}.desktop
            /usr/share/icons/hicolor/*/apps/{APP_NAME}.png

            %post
            if command -v gtk-update-icon-cache >/dev/null 2>&1; then
                gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
            fi

            %postun
            if [ "$1" = "0" ]; then
                if command -v gtk-update-icon-cache >/dev/null 2>&1; then
                    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
                fi
            fi
            """
        ),
        encoding="utf-8",
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[linux] building the RPM ...")
    _run([
        "rpmbuild", "-bb", "--build-in-place",
        "--define", f"_topdir {buildroot}",
        "--define", f"_rpmdir {out_dir}",
        str(spec),
    ])
    produced = sorted(out_dir.glob(f"{APP_NAME}-*.x86_64.rpm"))
    if not produced:
        raise SystemExit("rpmbuild did not produce a package")
    print(f"[linux] built {produced[-1].name}")
    return produced[-1]


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
