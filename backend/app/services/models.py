"""Local model catalogue, installation and readiness checks (offline after first download)."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..config import CACHE, HOME, env, ollama_host
from .llm import tags

CATALOG: list[dict[str, Any]] = [
    {"id": "gemma2:7b", "kind": "LLM", "name": "Gemma 2 7B", "provider": "Ollama", "size": "5.4 GB", "use": "Hook titles, hashtags, clip reranking", "recommended": True},
    {"id": "gemma3:4b", "kind": "LLM", "name": "Gemma 3 4B", "provider": "Ollama", "size": "3.3 GB", "use": "Fastest local LLM for low-power machines"},
    {"id": "gemma3:12b", "kind": "LLM", "name": "Gemma 3 12B", "provider": "Ollama", "size": "8.1 GB", "use": "Highest quality metadata for powerful GPUs"},
    {"id": "whisper-small", "kind": "ASR", "name": "Whisper Small", "provider": "faster-whisper", "size": "0.5 GB", "use": "Word-timed captions (balanced)", "recommended": True},
    {"id": "whisper-medium", "kind": "ASR", "name": "Whisper Medium", "provider": "faster-whisper", "size": "1.5 GB", "use": "Better accuracy for Hindi / multilingual"},
    {"id": "whisper-large-v3", "kind": "ASR", "name": "Whisper Large v3", "provider": "faster-whisper", "size": "3.0 GB", "use": "Best accuracy, needs more RAM/VRAM"},
    {"id": "yolo11n", "kind": "Vision", "name": "YOLO11 Nano + ByteTrack", "provider": "ultralytics", "size": "12 MB", "use": "Player / gameplay region activity tracking", "recommended": True},
    {"id": "yolox-nano", "kind": "Vision", "name": "YOLOX Nano + ByteTrack", "provider": "ultralytics", "size": "17 MB", "use": "YOLOX weights for player detection"},
    {"id": "piper-en_US-lessac-medium", "kind": "TTS", "name": "Piper Lessac (EN)", "provider": "piper", "size": "60 MB", "use": "Offline voice-overs and narration"},
    {"id": "sdxl-1.0", "kind": "Image", "name": "SDXL 1.0 (ComfyUI)", "provider": "comfyui", "size": "6.9 GB", "use": "100% local stickers/thumbnails via ComfyUI"},
]


async def status() -> list[dict[str, Any]]:
    installed_llm = {item["name"] for item in await tags()}
    hf_cache = Path(env("HF_HOME", str(HOME / "cache" / "huggingface"))).expanduser()
    yolo_dir = Path(env("YOLO_WEIGHTS_DIR", str(CACHE / "yolo")))
    piper_dir = CACHE / "piper"
    result = []
    for model in CATALOG:
        installed = False
        if model["provider"] == "Ollama":
            installed = any(model["id"].split(":")[0] in name for name in installed_llm)
        elif model["provider"] == "faster-whisper":
            short = model["id"].replace("whisper-", "models--Systran--faster-whisper-")
            installed = (hf_cache / short).exists() or (hf_cache / "hub" / short).exists()
        elif model["provider"] == "ultralytics":
            installed = (yolo_dir / (model["id"] + ".pt")).exists()
        elif model["provider"] == "piper":
            installed = (piper_dir / (model["id"].replace("piper-", "") + ".onnx")).exists()
        elif model["provider"] == "comfyui":
            checkpoint_dir = Path(env("COMFY_CHECKPOINTS", str(HOME / "models" / "checkpoints")))
            installed = bool(list(checkpoint_dir.glob("*.safetensors"))) if checkpoint_dir.exists() else False
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


async def install(model_id: str, progress: Callable[[float, str], None]) -> dict[str, Any]:
    model = next((item for item in CATALOG if item["id"] == model_id), None)
    if not model:
        raise RuntimeError(f"Unknown model id: {model_id}")

    def work():
        progress(5, f"Preparing {model['name']}…")
        if model["provider"] == "Ollama":
            _ollama_pull(model_id, progress)
        elif model["provider"] == "faster-whisper":
            try:
                from huggingface_hub import snapshot_download  # type: ignore

                repo = f"Systran/faster-whisper-{model_id.replace('whisper-', '')}"
                snapshot_download(repo_id=repo, local_dir=CACHE / "huggingface" / repo.split("/")[-1])
            except ImportError as exc:
                raise RuntimeError("Install huggingface-hub to download Whisper weights: pip install huggingface-hub") from exc
        elif model["provider"] == "ultralytics":
            try:
                from ultralytics import YOLO  # type: ignore

                target = CACHE / "yolo"
                target.mkdir(parents=True, exist_ok=True)
                YOLO(model_id + ".pt").save(str(target / (model_id + ".pt")))
            except ImportError as exc:
                raise RuntimeError("Install ultralytics to download vision weights: pip install ultralytics") from exc
        elif model["provider"] == "piper":
            try:
                from piper.download import get_voices  # type: ignore

                voices = get_voices(str(CACHE / "piper"))
                voices[model_id.replace("piper-", "")].download(str(CACHE / "piper"))
            except ImportError as exc:
                raise RuntimeError("Install piper-tts to download voices: pip install piper-tts") from exc
        else:
            raise RuntimeError(
                "Download an SDXL .safetensors checkpoint into ~/.AiFreeClipping/models/checkpoints "
                "and start ComfyUI to use local image generation."
            )
        progress(100, "Installed")
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
    else:
        raise RuntimeError("Local weight files can be removed from the Models folder in your data directory.")
    return {"model_id": model_id, "installed": False}
