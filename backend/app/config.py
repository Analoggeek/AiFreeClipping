"""Paths, environment configuration and runtime capability detection."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

APP_NAME = "AI Clipper Pro"
DEFAULT_MODEL = "gemma2:7b"


def app_home() -> Path:
    custom = os.getenv("AIFREECLIP_HOME")
    path = Path(custom).expanduser() if custom else Path.home() / ".AiFreeClipping"
    path.mkdir(parents=True, exist_ok=True)
    for folder in ("downloads", "projects", "clips", "assets", "cache", "exports", "logs", "models"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    return path


HOME = app_home()
DB_PATH = HOME / "db.sqlite3"
SECRET_PATH = HOME / ".api_token"
DOWNLOADS = HOME / "downloads"
PROJECTS = HOME / "projects"
CLIPS = HOME / "clips"
ASSETS = HOME / "assets"
CACHE = HOME / "cache"
EXPORTS = HOME / "exports"


def _bundled(name: str) -> str | None:
    """Look for binaries shipped next to the PyInstaller executable."""
    roots = [Path(getattr(os.sys, "_MEIPASS", "")) if getattr(os.sys, "_MEIPASS", "") else None,
             Path(os.sys.executable).parent]
    suffix = ".exe" if os.name == "nt" else ""
    for root in roots:
        if root and (root / f"{name}{suffix}").exists():
            return str(root / f"{name}{suffix}")
    return None


def ffmpeg_binary() -> str:
    """Resolve ffmpeg from env, bundle, PATH, or the imageio-ffmpeg wheel."""
    configured = os.getenv("FFMPEG_BINARY")
    if configured and Path(configured).exists():
        return configured
    bundled = _bundled("ffmpeg")
    if bundled:
        return bundled
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ffprobe_binary() -> str:
    configured = os.getenv("FFPROBE_BINARY")
    if configured and Path(configured).exists():
        return configured
    bundled = _bundled("ffprobe")
    if bundled:
        return bundled
    on_path = shutil.which("ffprobe")
    if on_path:
        return on_path
    ffmpeg = ffmpeg_binary()
    candidate = Path(ffmpeg).with_name("ffprobe")
    return str(candidate) if candidate.exists() else ffmpeg


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def ollama_host() -> str:
    return env("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def capabilities() -> dict[str, Any]:
    """Report what is available on this machine without importing heavy optional deps."""
    result: dict[str, Any] = {
        "ffmpeg": _tool_version(ffmpeg_binary(), "-version"),
        "ffprobe": _tool_version(ffprobe_binary(), "-version"),
        "python": os.sys.version.split()[0],
        "ollamaHost": ollama_host(),
        "ollamaModel": env("OLLAMA_MODEL", DEFAULT_MODEL),
        "whisperModel": env("WHISPER_MODEL", "small"),
        "paths": {
            "home": str(HOME),
            "downloads": str(DOWNLOADS),
            "projects": str(PROJECTS),
            "exports": str(EXPORTS),
        },
    }
    for module, key in (
        ("yt_dlp", "ytDlp"),
        ("faster_whisper", "fasterWhisper"),
        ("cv2", "opencv"),
        ("ultralytics", "ultralytics"),
        ("supervision", "supervision"),
        ("piper", "piper"),
        ("google.genai", "geminiSdk"),
    ):
        try:
            __import__(module)
            result[key] = True
        except Exception:
            result[key] = False
    result["gpu"] = _gpu_info()
    return result


def _tool_version(binary: str, flag: str) -> str | None:
    try:
        out = subprocess.run([binary, flag], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.splitlines()[0][:120]
    except Exception:
        pass
    return None


def _gpu_info() -> dict[str, Any]:
    info: dict[str, Any] = {"cuda": False, "metal": False, "note": "CPU fallback available"}
    try:
        import torch  # type: ignore

        info["cuda"] = bool(torch.cuda.is_available())
        info["metal"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception:
        import platform

        info["metal"] = platform.system() == "Darwin"
    return info
