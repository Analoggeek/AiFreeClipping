"""Local/cloud AI catalogue, one-click downloads, readiness checks.

Every local model exposes a real download URL and downloads into the app data
folder. Cloud entries expose a direct 'Get API key' link instead.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..config import CACHE, HOME, env, ollama_host
from .llm import tags

OLLAMA_INSTALLER = "https://ollama.com/download"
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


def _path(model: dict[str, Any]) -> Path | None:
    name = model.get("file")
    if not name:
        return None
    folder = {
        "yolox-onnx": CACHE / "yolo", "ultralytics": CACHE / "yolo", "piper": CACHE / "piper",
    }.get(model["provider"])
    return folder / name if folder else None


async def status() -> list[dict[str, Any]]:
    installed_llm = {item["name"] for item in await tags()}
    hf_cache = Path(env("HF_HOME", str(HOME / "cache" / "huggingface"))).expanduser()
    checkpoint_dir = Path(env("COMFY_CHECKPOINTS", str(HOME / "models" / "checkpoints")))
    result = []
    for model in CATALOG:
        installed = False
        if model["provider"] == "Ollama":
            installed = any(model["id"].split(":")[0] in name for name in installed_llm)
        elif model["provider"] == "faster-whisper":
            short = model["id"].replace("whisper-", "models--Systran--faster-whisper-")
            installed = (
                (hf_cache / short).exists()
                or (hf_cache / "hub" / short).exists()
                or (hf_cache / model["id"]).exists()
            )
        elif model.get("file") and _path(model):
            installed = bool(_path(model).exists())
        elif model["provider"] == "comfyui":
            installed = bool(list(checkpoint_dir.glob("*.safetensors"))) if checkpoint_dir.exists() else False
        elif model.get("needsApi"):
            installed = bool(env(API_ENV.get(model["id"], "")))
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
            try:
                _ollama_pull(model_id, progress)
            except Exception as exc:
                raise RuntimeError(
                    f"Ollama is not reachable. Install it from {OLLAMA_INSTALLER}, start it, then try again. ({exc})"
                ) from exc
        elif model["provider"] == "faster-whisper":
            try:
                from huggingface_hub import snapshot_download  # type: ignore

                repo = f"Systran/faster-whisper-{model_id.replace('whisper-', '')}"
                snapshot_download(repo_id=repo, local_dir=CACHE / "huggingface" / repo.split("/")[-1])
            except ImportError as exc:
                raise RuntimeError("Install huggingface-hub to download Whisper weights.") from exc
        elif _path(model):
            destination = _path(model)
            assert destination is not None
            if not destination.exists():
                _download(str(model["downloadUrl"]), destination, progress, model["name"])
            if model["provider"] == "piper":
                config = Path(str(model["downloadUrl"]).split("?")[0] + ".json")
                if not config.exists():
                    try:
                        _download(str(config), config, progress, "voice config")
                    except Exception:
                        pass
        elif model["provider"] == "comfyui":
            raise RuntimeError(
                f"Download the SDXL checkpoint from {model['downloadUrl']} and save it to "
                f"{HOME / 'models' / 'checkpoints'}. ComfyUI can then use it locally."
            )
        else:
            raise RuntimeError(f"Use the download link for {model['name']} to complete setup.")
        progress(100, "Installed — ready to use offline")
        return {"model_id": model_id, "installed": True}

    return await asyncio.to_thread(work)


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
    return {"model_id": model_id, "installed": False}
