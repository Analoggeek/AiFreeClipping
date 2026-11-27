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
    info: dict[str, Any] = {
        "cuda": False, "metal": False, "note": "CPU fallback available", "name": "CPU",
        "vram_total_gb": None,
    }
    try:
        nvidia = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4,
        )
        if nvidia.returncode == 0 and nvidia.stdout.strip():
            info["cuda"] = True
            devices: list[tuple[float, str]] = []
            for line in nvidia.stdout.splitlines():
                parts = line.rsplit(",", 1)
                name = parts[0].strip()
                memory = parts[1].strip().split() if len(parts) > 1 else []
                try:
                    total = float(memory[0])
                    unit = memory[1].lower() if len(memory) > 1 else "mib"
                    vram_gb = total / (1024 if unit.startswith("m") else 1)
                    devices.append((vram_gb, name))
                except (ValueError, IndexError):
                    devices.append((0.0, name))
            if devices:
                best_vram, info["name"] = max(devices)
                info["vram_total_gb"] = round(best_vram, 1) if best_vram else None
            info["note"] = "NVIDIA GPU available for NVENC / Whisper CUDA"
    except Exception:
        pass
    try:
        import torch  # type: ignore

        cuda_available = bool(torch.cuda.is_available())
        info["cuda"] = info["cuda"] or cuda_available
        if cuda_available and info["vram_total_gb"] is None:
            try:
                properties = torch.cuda.get_device_properties(0)
                info["vram_total_gb"] = round(float(properties.total_memory) / (1024 ** 3), 1)
                info["name"] = str(getattr(properties, "name", info["name"]))
                info["note"] = "NVIDIA GPU available for NVENC / Whisper CUDA"
            except Exception:
                pass
        info["metal"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    except Exception:
        import platform

        info["metal"] = platform.system() == "Darwin"
    if info["metal"] and not info["cuda"]:
        info["name"] = "Apple Silicon / Metal"
        info["note"] = "Metal available for VideoToolbox encoding"
    return info


_usage_cache: dict[str, Any] = {"at": 0.0, "value": 0.0}


def _folder_size(paths) -> int:
    import time

    if time.time() - _usage_cache["at"] < 30:
        return int(_usage_cache["value"] * 1024 ** 3)
    total = 0
    for folder in paths:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    _usage_cache.update(at=time.time(), value=total / 1024 ** 3)
    return total


def hardware_info() -> dict[str, Any]:
    """Live hardware usage snapshot for the app's performance HUD."""
    import platform
    import time

    info: dict[str, Any] = {
        "cpu_count": os.cpu_count() or 4,
        "platform": platform.system(),
        "gpu": _gpu_info(),
        "workers": max(1, min(8, int(env("RENDER_WORKERS") or min(4, os.cpu_count() or 4)))),
        "encoder": env("AIFREECLIP_ENCODER", "auto"),
    }
    try:
        used = _folder_size([DOWNLOADS, CACHE, EXPORTS, CLIPS, ASSETS, PROJECTS])
        info["app_usage_gb"] = round(used / 1024 ** 3, 2)
    except Exception:
        info["app_usage_gb"] = 0.0
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        info.update({
            "cpu_percent": round(float(psutil.cpu_percent(interval=0.15)), 1),
            "ram_percent": round(float(memory.percent), 1),
            "ram_used_gb": round(memory.used / (1024 ** 3), 2),
            "ram_total_gb": round(memory.total / (1024 ** 3), 2),
            "disk_free_gb": round(psutil.disk_usage(str(HOME)).free / (1024 ** 3), 1),
        })
    except Exception:
        info.update({
            "cpu_percent": None, "ram_percent": None, "ram_used_gb": None,
            "ram_total_gb": None, "disk_free_gb": None,
        })
    return info
