"""Local/cloud AI catalogue, one-click downloads, readiness checks.

Every local model exposes a real download URL and downloads into the app data
folder. Cloud entries expose a direct 'Get API key' link instead.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from ..config import CACHE, HOME, env, ollama_host
from ..db import db
from .llm import tags

OLLAMA_INSTALLER = "https://ollama.com/download"
OLLAMA_VERSION = "v0.40.18"
HF = "https://huggingface.co"
YOLOX_ONNX = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
PIPER_VOICE = (
    f"{HF}/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"
    "en_US-lessac-medium.onnx?download=true"
)
SDXL_CHECKPOINT = (
    f"{HF}/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/"
    "sd_xl_base_1.0.safetensors?download=true"
)

CATALOG: list[dict[str, Any]] = [
    {
        "id": "gemma2:7b", "kind": "LLM", "name": "Gemma 2 7B", "provider": "Ollama",
        "size": "5.4 GB", "use": "Hook titles, hashtags, clip reranking", "recommended": True,
        "downloadUrl": "https://ollama.com/library/gemma2", "docsUrl": "https://docs.ollama.com",
        "providerUrl": OLLAMA_INSTALLER, "autoInstall": True,
    },
    {
        "id": "gemma3:4b", "kind": "LLM", "name": "Gemma 3 4B", "provider": "Ollama",
        "size": "3.3 GB", "use": "Fastest local LLM for low-power machines",
        "downloadUrl": "https://ollama.com/library/gemma3", "docsUrl": "https://docs.ollama.com",
        "providerUrl": OLLAMA_INSTALLER, "autoInstall": True,
    },
    {
        "id": "gemma3:12b", "kind": "LLM", "name": "Gemma 3 12B", "provider": "Ollama",
        "size": "8.1 GB", "use": "Highest quality metadata for powerful GPUs",
        "downloadUrl": "https://ollama.com/library/gemma3", "docsUrl": "https://docs.ollama.com",
        "providerUrl": OLLAMA_INSTALLER, "autoInstall": True,
    },
    {
        "id": "whisper-small", "kind": "ASR", "name": "Whisper Small", "provider": "faster-whisper",
        "size": "0.5 GB", "use": "Word-timed captions (balanced)", "recommended": True,
        "downloadUrl": f"{HF}/Systran/faster-whisper-small", "docsUrl": f"{HF}/Systran/faster-whisper-small",
        "autoInstall": True,
    },
    {
        "id": "whisper-medium", "kind": "ASR", "name": "Whisper Medium", "provider": "faster-whisper",
        "size": "1.5 GB", "use": "Better accuracy for Hindi / multilingual",
        "downloadUrl": f"{HF}/Systran/faster-whisper-medium", "docsUrl": f"{HF}/Systran/faster-whisper-medium",
        "autoInstall": True,
    },
    {
        "id": "whisper-large-v3", "kind": "ASR", "name": "Whisper Large v3", "provider": "faster-whisper",
        "size": "3.0 GB", "use": "Best accuracy, needs more RAM/VRAM",
        "downloadUrl": f"{HF}/Systran/faster-whisper-large-v3", "docsUrl": f"{HF}/Systran/faster-whisper-large-v3",
        "autoInstall": True,
    },
    {
        "id": "yolox-nano", "kind": "Vision", "name": "YOLOX Nano + ByteTrack", "provider": "yolox-onnx",
        "size": "4 MB", "use": "Player / gameplay tracking — works in the packaged app", "recommended": True,
        "downloadUrl": YOLOX_ONNX, "docsUrl": "https://github.com/Megvii-BaseDetection/YOLOX",
        "file": "yolox_nano.onnx", "autoInstall": True,
    },
    {
        "id": "yolo11n", "kind": "Vision", "name": "YOLO11 Nano + ByteTrack", "provider": "ultralytics",
        "size": "12 MB", "use": "Higher-accuracy detector for source installs with ultralytics",
        "downloadUrl": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
        "docsUrl": "https://docs.ultralytics.com/models/yolo11/", "file": "yolo11n.pt",
        "setupNote": "Needs ultralytics in a source install; packaged builds use YOLOX ONNX.",
        "autoInstall": True,
    },
    {
        "id": "piper-en_US-lessac-medium", "kind": "TTS", "name": "Piper Lessac (EN)", "provider": "piper",
        "size": "60 MB", "use": "Offline voice-overs and narration",
        "downloadUrl": PIPER_VOICE, "docsUrl": "https://github.com/rhasspy/piper",
        "file": "en_US-lessac-medium.onnx", "autoInstall": True,
    },
    {
        "id": "sdxl-1.0", "kind": "Image", "name": "SDXL 1.0 (ComfyUI)", "provider": "comfyui",
        "size": "6.9 GB", "use": "100% local stickers/thumbnails via ComfyUI",
        "downloadUrl": SDXL_CHECKPOINT, "docsUrl": "https://github.com/comfyanonymous/ComfyUI",
        "providerUrl": "https://github.com/comfyanonymous/ComfyUI/releases", "autoInstall": False,
        "setupNote": "Download the checkpoint and place it in ~/.AiFreeClipping/models/checkpoints.",
    },
    {
        "id": "nano-banana", "kind": "Cloud", "name": "Nano Banana (Gemini image)", "provider": "Google Gemini",
        "size": "API", "use": "High-quality online sticker / thumbnail generation", "needsApi": True,
        "downloadUrl": "https://aistudio.google.com/app/apikey",
        "apiUrl": "https://aistudio.google.com/app/apikey",
        "docsUrl": "https://ai.google.dev/gemini-api/docs/image-generation", "autoInstall": False,
    },
    {
        "id": "youtube-api", "kind": "Cloud", "name": "YouTube Data API", "provider": "Google Cloud",
        "size": "API", "use": "Direct OAuth upload from the Publish page", "needsApi": True,
        "apiUrl": "https://console.cloud.google.com/apis/credentials",
        "docsUrl": "https://developers.google.com/youtube/v3/guides/uploading_a_video", "autoInstall": False,
    },
    {
        "id": "pexels-api", "kind": "Cloud", "name": "Pexels API", "provider": "Pexels",
        "size": "API", "use": "Copyright-friendly stock footage search in the editor", "needsApi": True,
        "apiUrl": "https://www.pexels.com/api/", "docsUrl": "https://www.pexels.com/api/documentation/",
        "autoInstall": False,
    },
    {
        "id": "pixabay-api", "kind": "Cloud", "name": "Pixabay API", "provider": "Pixabay",
        "size": "API", "use": "Stock images, video and audio with license metadata", "needsApi": True,
        "apiUrl": "https://pixabay.com/api/docs/", "docsUrl": "https://pixabay.com/api/docs/",
        "autoInstall": False,
    },
]

API_ENV = {
    "nano-banana": "GEMINI_API_KEY",
    "youtube-api": "YOUTUBE_CLIENT_SECRET",
    "pexels-api": "PEXELS_API_KEY",
    "pixabay-api": "PIXABAY_API_KEY",
}
API_SETTINGS = {
    "nano-banana": "gemini_api_key",
    "youtube-api": "youtube_client_secret",
    "pexels-api": "pexels_api_key",
    "pixabay-api": "pixabay_api_key",
}


def _installed_ids() -> set[str]:
    try:
        return set(json.loads(db.get_setting("installed_models", "[]") or "[]"))
    except (TypeError, ValueError):
        return set()


def _activate(model: dict[str, Any]) -> None:
    """Persist and immediately activate a model after a successful install."""
    ids = _installed_ids()
    ids.add(model["id"])
    db.set_setting("installed_models", json.dumps(sorted(ids)))
    activation = {
        "LLM": {"active_llm": model["id"], "OLLAMA_MODEL": model["id"]},
        "ASR": {"whisper_model": model["id"].replace("whisper-", "")},
        "Vision": {"vision_engine": "yolox" if model["provider"] == "yolox-onnx" else "ultralytics"},
        "TTS": {"tts_voice": model["id"].replace("piper-", "")},
        "Image": {"image_provider": "comfyui"},
    }.get(model["kind"], {})
    for key, value in activation.items():
        db.set_setting(key, value)
        os.environ[key] = value


def _ollama_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{ollama_host()}/api/tags", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _ollama_binary() -> Path | None:
    for candidate in (
        CACHE / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama"),
        Path(shutil.which("ollama") or "") if shutil.which("ollama") else None,
    ):
        if candidate and candidate.exists():
            return candidate
    return None


def _safe_extract(archive: tarfile.TarFile | zipfile.ZipFile, root: Path, members: Any) -> None:
    root = root.resolve()
    for member in members:
        name = getattr(member, "filename", getattr(member, "name", ""))
        destination = (root / name).resolve()
        if not str(destination).startswith(str(root)):
            continue
        if getattr(member, "is_dir", lambda: False)():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(archive, zipfile.ZipFile):
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
        else:
            source = archive.extractfile(member)
            if source:
                with source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)


def _ensure_ollama(progress: Callable[[float, str], None]) -> None:
    """Download and start the local Ollama runtime with no user action required."""
    if _ollama_alive():
        return
    binary = _ollama_binary()
    if not binary:
        system = platform.system().lower()
        machine = platform.machine().lower()
        root = CACHE / "ollama"
        root.mkdir(parents=True, exist_ok=True)
        base = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}"
        if system == "darwin":
            url, archive_name = f"{base}/ollama-darwin.tgz", "ollama.tgz"
        elif system == "windows":
            arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
            url, archive_name = f"{base}/ollama-windows-{arch}.zip", "ollama.zip"
        else:
            arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
            url = f"{base}/ollama-linux-{arch}.tar.zst"
            archive_name = "ollama.tar.zst"
            if not shutil.which("zstd"):
                # Older builds ship a plain gzip archive; no extra tool required.
                url = f"https://github.com/ollama/ollama/releases/download/v0.5.7/ollama-linux-{arch}.tgz"
                archive_name = "ollama.tgz"
        downloaded = root / archive_name
        progress(8, "Downloading the local Ollama runtime…")
        _download(url, downloaded, lambda pct, msg: progress(8 + pct * 0.5, msg), "Ollama runtime")
        progress(62, "Installing the local Ollama runtime…")
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(downloaded) as archive:
                _safe_extract(archive, root, archive.infolist())
        elif archive_name.endswith(".tar.zst"):
            plain = downloaded.with_suffix(".tar")
            subprocess.run(["zstd", "-dc", str(downloaded), "-o", str(plain)], check=True)
            with tarfile.open(plain) as archive:
                _safe_extract(archive, root, archive.getmembers())
            plain.unlink(missing_ok=True)
        else:
            with tarfile.open(downloaded, "r:gz") as archive:
                _safe_extract(archive, root, archive.getmembers())
        downloaded.unlink(missing_ok=True)
        candidates = sorted(root.rglob("ollama.exe" if os.name == "nt" else "ollama"))
        binary = next((item for item in candidates if item.is_file()), None)
        if binary is None:
            raise RuntimeError("The Ollama runtime downloaded but its executable was not found.")
        db.set_setting("ollama_binary", str(binary))
    if os.name != "nt":
        try:
            binary.chmod(0o755)
        except OSError:
            pass
        # Downloaded binaries carry quarantine metadata on macOS.
        if platform.system() == "Darwin":
            subprocess.run(["xattr", "-c", str(binary)], capture_output=True, check=False)
    if not _ollama_alive():
        progress(72, "Starting the local Ollama service…")
        log_path = CACHE / "ollama.log"
        with log_path.open("ab") as log:
            subprocess.Popen(
                [str(binary), "serve"], stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, cwd=str(binary.parent),
            )
        for _ in range(60):
            if _ollama_alive():
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Ollama did not start. Check {log_path} for details.")


def _path(model: dict[str, Any]) -> Path | None:
    name = model.get("file")
    if not name:
        return None
    folder = {
        "yolox-onnx": CACHE / "yolo", "ultralytics": CACHE / "yolo", "piper": CACHE / "piper",
    }.get(model["provider"])
    return folder / name if folder else None


def _whisper_dir(model_id: str) -> Path:
    return Path(env("HF_HOME", str(CACHE / "huggingface"))).expanduser() / model_id


async def status() -> list[dict[str, Any]]:
    installed_llm = {item["name"] for item in await tags()}
    persisted = _installed_ids()
    checkpoint_dir = Path(env("COMFY_CHECKPOINTS", str(HOME / "models" / "checkpoints")))
    result = []
    for model in CATALOG:
        installed = model["id"] in persisted
        if model["provider"] == "Ollama":
            installed = installed or any(model["id"].split(":")[0] in name for name in installed_llm)
        elif model["provider"] == "faster-whisper":
            short = model["id"].replace("whisper-", "models--Systran--faster-whisper-")
            folder = _whisper_dir(model["id"])
            installed = installed or (
                folder.exists()
                or (folder.parent / short).exists()
                or (folder.parent / "hub" / short).exists()
            )
        elif model.get("file") and _path(model):
            target = _path(model)
            installed = installed or bool(target and target.exists())
        elif model["provider"] == "comfyui":
            installed = installed or bool(list(checkpoint_dir.glob("*.safetensors"))) if checkpoint_dir.exists() else installed
        elif model.get("needsApi"):
            installed = installed or bool(
                env(API_ENV.get(model["id"], ""))
                or db.get_setting(API_SETTINGS.get(model["id"], ""))
            )
        result.append({**model, "installed": installed})
    return result


def _ollama_pull(model_id: str, progress: Callable[[float, str], None]) -> None:
    request = urllib.request.Request(
        f"{ollama_host()}/api/pull",
        data=json.dumps({"name": model_id, "stream": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        for raw in response:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if item.get("total") and item.get("completed"):
                progress(min(95, item["completed"] / item["total"] * 100), f"Pulling {model_id}…")
            elif item.get("status"):
                progress(5, str(item["status"])[:120])


def _download(url: str, target: Path, progress: Callable[[float, str], None], label: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Clipper-Pro/5.1"})
    with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if total:
                progress(min(95, done / total * 100), f"Downloading {label}…")
    shutil.move(str(temp), str(target))


async def install(model_id: str, progress: Callable[[float, str], None]) -> dict[str, Any]:
    model = next((item for item in CATALOG if item["id"] == model_id), None)
    if not model:
        raise RuntimeError(f"Unknown model id: {model_id}")
    if model.get("needsApi"):
        raise RuntimeError(f"Open {model['apiUrl']} to create your API key, then paste it into Settings.")

    def work():
        progress(5, f"Preparing {model['name']}…")
        if model["provider"] == "Ollama":
            _ensure_ollama(progress)
            _ollama_pull(model_id, lambda pct, msg: progress(max(76, pct * 0.24), msg))
        elif model["provider"] == "faster-whisper":
            try:
                from huggingface_hub import snapshot_download  # type: ignore

                repo = f"Systran/faster-whisper-{model_id.replace('whisper-', '')}"
                destination = _whisper_dir(model_id)
                destination.mkdir(parents=True, exist_ok=True)
                snapshot_download(repo_id=repo, local_dir=str(destination))
            except ImportError as exc:
                raise RuntimeError(
                    "huggingface-hub is required to download Whisper weights. It is included in the packaged app."
                ) from exc
        elif _path(model):
            destination = _path(model)
            assert destination is not None
            if not destination.exists():
                _download(str(model["downloadUrl"]), destination, progress, model["name"])
            if model["provider"] == "piper":
                config_url = str(model["downloadUrl"]).split("?")[0] + ".json"
                config = destination.with_name(destination.name.replace(".onnx", ".json"))
                if not config.exists():
                    try:
                        _download(config_url, config, progress, "voice config")
                    except Exception:
                        pass
        elif model["provider"] == "comfyui":
            destination = Path(env("COMFY_CHECKPOINTS", str(HOME / "models" / "checkpoints")))
            destination.mkdir(parents=True, exist_ok=True)
            checkpoint = destination / "sd_xl_base_1.0.safetensors"
            if not checkpoint.exists():
                _download(str(model["downloadUrl"]), checkpoint, progress, model["name"])
        else:
            raise RuntimeError(f"Use the download link for {model['name']} to complete setup.")
        _activate(model)
        progress(100, "Installed, activated and saved")
        return {"model_id": model_id, "installed": True, "activated": True}

    return await asyncio.to_thread(work)


async def install_recommended(progress: Callable[[float, str], None]) -> dict[str, Any]:
    """One-click setup for the models the whole offline pipeline needs."""
    installed = await status()
    pending = [item for item in installed if item.get("recommended") and item.get("autoInstall") and not item["installed"]]
    done: list[str] = []
    for index, item in enumerate(pending):
        offset = index / max(len(pending), 1) * 100
        span = 100 / max(len(pending), 1)

        def scoped(pct: float, message: str, item=item, offset=offset, span=span) -> None:
            progress(min(99, offset + pct / 100 * span), f"{item['name']}: {message}")

        await install(item["id"], scoped)
        done.append(item["id"])
    progress(100, "Recommended models are installed and active")
    return {"installed": done, "count": len(done)}


async def uninstall(model_id: str) -> dict[str, Any]:
    model = next((item for item in CATALOG if item["id"] == model_id), None)
    if not model:
        raise RuntimeError(f"Unknown model id: {model_id}")
    if model["provider"] == "Ollama":
        request = urllib.request.Request(
            f"{ollama_host()}/api/delete",
            data=json.dumps({"name": model_id}).encode(),
            method="DELETE",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30):
            pass
    elif _path(model):
        path = _path(model)
        assert path is not None
        if path.exists():
            path.unlink()
    else:
        raise RuntimeError("Remove this model's files from the Models folder in your data directory.")
    remaining = _installed_ids()
    remaining.discard(model_id)
    db.set_setting("installed_models", json.dumps(sorted(remaining)))
    return {"model_id": model_id, "installed": False}
