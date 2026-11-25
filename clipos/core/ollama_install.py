"""Consented official OS installer lifecycle, separate from model-weight pulls.

Never disables OS security, elevates silently or installs pip into a frozen app.
Downloaded bytes are pinned to GitHub's official release SHA256 metadata.
"""

import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import time
import zipfile

from .config import PATHS
from .local_ai import LocalOllama
from .verified_download import download, DownloadCancelled

VERSION = "v0.40.18"
ASSETS = {
    "Windows": (
        "OllamaSetup.exe",
        1953587080,
        "ad2bb47aa969b21cf8dd81b2d9f9a6d5030270ed242ef55087118c37c510acc2",
    ),
    "Darwin": (
        "Ollama-darwin.zip",
        231986751,
        "1d990f4a8a76985c9defaa9a6ddd007556d117fd8ed586d7e9cbf25a6e9a4a23",
    ),
}


def find_binary():
    candidates = [shutil.which("ollama")]
    if platform.system() == "Windows":
        for base in (
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("PROGRAMFILES", ""),
        ):
            if base:
                candidates.extend(
                    [
                        str(Path(base) / "Programs" / "Ollama" / "ollama.exe"),
                        str(Path(base) / "Ollama" / "ollama.exe"),
                    ]
                )
    elif platform.system() == "Darwin":
        candidates.extend(
            [
                str(Path.home() / "Applications/Ollama.app/Contents/Resources/ollama"),
                "/Applications/Ollama.app/Contents/Resources/ollama",
                "/usr/local/bin/ollama",
                "/opt/homebrew/bin/ollama",
            ]
        )
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


def api_status():
    result = LocalOllama(timeout=2).request("/api/version")
    if not isinstance(result.get("version"), str) or not result["version"]:
        raise RuntimeError("Ollama API did not report a valid version")
    return result


def start_service(*, cancelled=None):
    try:
        return api_status()
    except Exception:
        pass
    binary = find_binary()
    if binary is None:
        raise RuntimeError(
            "Ollama executable not found. Use Install Ollama from AI Models."
        )
    PATHS.logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    # Bind only to loopback. Respect the installed runtime's default model store;
    # never relocate an existing model collection without explicit migration.
    with (PATHS.logs / "ollama-service.log").open("ab") as log:
        options = {
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": log,
            "env": env,
        }
        if platform.system() == "Windows":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            options["start_new_session"] = True
        child = subprocess.Popen([str(binary), "serve"], **options)
    for _ in range(60):
        if cancelled and cancelled():
            raise DownloadCancelled(
                "Stopped waiting for runtime startup; no existing Ollama service was killed"
            )
        try:
            return api_status()
        except Exception:
            pass
        if child.poll() is not None:
            raise RuntimeError(
                "Ollama exited before its API became ready; inspect ollama-service.log"
            )
        time.sleep(0.5)
    raise RuntimeError(
        "Ollama startup timed out. Inspect local logs and retry Start / verify."
    )


def install(*, consent=False, progress=None, cancelled=None):
    if not consent:
        raise PermissionError("Explicit OS installation confirmation is required")
    try:
        return api_status()  # already serving: do not install a duplicate
    except Exception:
        pass
    if find_binary() is not None:
        return start_service(cancelled=cancelled)
    system = platform.system()
    arch = platform.machine().lower()
    if system not in ASSETS:
        raise RuntimeError(
            "Guided official installation supports Windows and macOS only; existing local runtimes can still be used"
        )
    if arch not in ("amd64", "x86_64", "arm64", "aarch64"):
        raise RuntimeError(f"Unsupported CPU architecture: {arch}")
    if system == "Windows" and arch not in ("amd64", "x86_64"):
        raise RuntimeError(
            "This pinned Windows installer is x64. A verified ARM64 installer is required; refusing an architecture guess."
        )
    name, size, digest = ASSETS[system]
    PATHS.cache.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(PATHS.cache).free < size * 3 + 512 * 1024**2:
        raise RuntimeError(
            "Insufficient disk space for installer download and extraction"
        )
    asset = download(
        f"https://github.com/ollama/ollama/releases/download/{VERSION}/{name}",
        PATHS.cache / "installers" / name,
        digest,
        size,
        progress=progress,
        cancelled=cancelled,
    )
    if cancelled and cancelled():
        raise DownloadCancelled(
            "Installer verified but not executed because installation was cancelled"
        )
    if system == "Windows":
        # Authenticode AND the pinned official SHA protect the executable. OS
        # installer remains interactive: no hidden elevation or silent flags.
        command = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            '$s=Get-AuthenticodeSignature -LiteralPath $env:CLIPOS_OLLAMA_INSTALLER; $s | Select-Object Status,StatusMessage,@{Name="Signer";Expression={$_.SignerCertificate.Subject}} | ConvertTo-Json -Compress; if($s.Status -ne "Valid"){exit 1}',
        ]
        signature = subprocess.run(
            command,
            env={**os.environ, "CLIPOS_OLLAMA_INSTALLER": str(asset)},
            capture_output=True,
            text=True,
            timeout=60,
        )
        if signature.returncode:
            raise RuntimeError(
                "Windows blocked Ollama installer: Authenticode verification failed. "
                "The installer was not executed. "
                + (
                    signature.stdout.strip()
                    or signature.stderr.strip()
                    or "No signature diagnostics supplied"
                )
            )
        process = subprocess.Popen([str(asset)])
        while process.poll() is None:
            if cancelled and cancelled():
                raise DownloadCancelled(
                    "Stopped waiting; the visible OS installer may still be open"
                )
            time.sleep(0.5)
        if process.returncode:
            raise RuntimeError(
                f"Ollama OS installer returned {process.returncode}; permission may have been denied"
            )
    else:
        # Validate archive paths before native extraction (preserves signed app
        # symlinks/permissions). Never extract an untrusted escape path.
        with zipfile.ZipFile(asset) as archive:
            for entry in archive.infolist():
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise RuntimeError("Unsafe official installer archive path")
        temporary = PATHS.cache / "ollama-unpack"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        subprocess.run(
            ["ditto", "-x", "-k", str(asset), str(temporary)], check=True, timeout=180
        )
        apps = list(temporary.glob("**/Ollama.app"))
        if len(apps) != 1:
            raise RuntimeError("Official archive has an unexpected app layout")
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(apps[0])],
            check=True,
            capture_output=True,
            timeout=60,
        )
        subprocess.run(
            ["spctl", "--assess", "--type", "execute", str(apps[0])],
            check=True,
            capture_output=True,
            timeout=60,
        )
        target = Path.home() / "Applications" / "Ollama.app"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RuntimeError(
                "Ollama app appeared during install; refusing to overwrite an existing installation"
            )
        shutil.move(str(apps[0]), str(target))
        shutil.rmtree(temporary)
    if find_binary() is None:
        raise RuntimeError(
            "Installer finished but executable verification failed; application has not marked Ollama installed"
        )
    return start_service(cancelled=cancelled)
