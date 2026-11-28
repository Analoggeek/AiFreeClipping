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
import stat
import subprocess
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from ..config import CACHE, HOME, env, hardware_info, ollama_host
from ..db import db
from .llm import tags
from .net import configure_ca_bundle, urlopen as https_open

configure_ca_bundle()

OLLAMA_INSTALLER = "https://ollama.com/download"
OLLAMA_VERSION = "v0.40.19"
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
        "size": "5.4 GB", "use": "Clip titles and local reranking", "recommended": True,
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
        "size": "0.5 GB", "use": "Transcript-aware clip scoring (balanced)", "recommended": True,
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
        "setupNote": "Install SDXL here or select a checkpoint you already downloaded. For ComfyUI, set its checkpoints folder below.",
    },
    {
        "id": "nano-banana", "kind": "Cloud", "name": "Nano Banana (Gemini image)", "provider": "Google Gemini",
        "size": "API", "use": "High-quality online sticker / thumbnail generation", "needsApi": True,
        "downloadUrl": "https://aistudio.google.com/app/apikey",
        "apiUrl": "https://aistudio.google.com/app/apikey",
        "docsUrl": "https://ai.google.dev/gemini-api/docs/image-generation", "autoInstall": False,
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
    "pexels-api": "PEXELS_API_KEY",
    "pixabay-api": "PIXABAY_API_KEY",
}
API_SETTINGS = {
    "nano-banana": "gemini_api_key",
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
        "LLM": {"active_llm": model["id"], "ollama_model": model["id"], "OLLAMA_MODEL": model["id"]},
        "ASR": {
            "whisper_model": model["id"].replace("whisper-", ""),
            "WHISPER_MODEL_PATH": str(_whisper_dir(model["id"])),
        },
        "Vision": {"vision_engine": "yolox" if model["provider"] == "yolox-onnx" else "ultralytics"},
        "TTS": {"tts_voice": model["id"].replace("piper-", "")},
        "Image": {"image_provider": "comfyui"},
    }.get(model["kind"], {})
    for key, value in activation.items():
        db.set_setting(key, value)
        os.environ[key] = value


def _ollama_alive() -> bool:
    try:
        with https_open(f"{ollama_host()}/api/tags", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _ollama_binary() -> Path | None:
    executable = "ollama.exe" if os.name == "nt" else "ollama"
    configured = db.get_setting("ollama_binary", "")
    candidates = [
        Path(configured).expanduser() if configured else None,
        _models_root() / "ollama" / executable,
        CACHE / "ollama" / executable,
        Path(shutil.which("ollama") or "") if shutil.which("ollama") else None,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def _safe_extract(archive: tarfile.TarFile | zipfile.ZipFile, root: Path, members: Any) -> None:
    root = root.resolve()
    for member in members:
        name = getattr(member, "filename", getattr(member, "name", ""))
        destination = (root / name).resolve()
        try:
            destination.relative_to(root)
        except ValueError:
            continue
        if getattr(member, "is_dir", lambda: False)():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if isinstance(archive, zipfile.ZipFile):
            mode = (member.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                continue
        elif not member.isfile():
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


def _ollama_archive(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """Select an official archive published for the running OS and architecture."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    base = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}"
    if system == "darwin":
        return f"{base}/ollama-darwin.tgz", "ollama.tgz"
    if machine in {"arm64", "aarch64"}:
        arch = "arm64"
    elif machine in {"x86_64", "amd64", "x64"}:
        arch = "amd64"
    else:
        raise RuntimeError(f"Automatic Ollama runtime installation is not supported on {machine}.")
    if system == "windows":
        return f"{base}/ollama-windows-{arch}.zip", "ollama.zip"
    if system == "linux":
        return f"{base}/ollama-linux-{arch}.tar.zst", "ollama.tar.zst"
    raise RuntimeError(f"Automatic Ollama runtime installation is not supported on {system}.")


def _extract_zstd_tar(downloaded: Path, root: Path) -> None:
    """Stream-extract Ollama's Linux tar.zst without writing a second multi-GB tar."""
    try:
        import zstandard  # type: ignore
    except ImportError:
        zstd = shutil.which("zstd")
        if not zstd:
            raise RuntimeError(
                "Cannot unpack the Ollama Linux runtime: zstandard support is missing. "
                "Install the app's runtime update or add the zstd command to PATH, then retry."
            )
        command = [zstd, "-d", "-c", str(downloaded)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if process.stdout is None:
            process.terminate()
            process.wait()
            raise RuntimeError("Cannot read the decompressed Ollama archive stream.")
        try:
            with process.stdout:
                with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                    _safe_extract(archive, root, archive)
            if process.wait() != 0:
                raise RuntimeError("The zstd command could not decompress the Ollama runtime archive.")
        except Exception:
            if process.poll() is None:
                process.terminate()
            process.wait()
            raise
        return

    with downloaded.open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as decompressed:
            with tarfile.open(fileobj=decompressed, mode="r|") as archive:
                _safe_extract(archive, root, archive)


def _ensure_ollama(progress: Callable[[float, str], None]) -> None:
    """Download and start the local Ollama runtime with no user action required."""
    if _ollama_alive():
        return
    binary = _ollama_binary()
    if not binary:
        root = _models_root() / "ollama"
        root.mkdir(parents=True, exist_ok=True)
        url, archive_name = _ollama_archive()
        downloaded = root / archive_name
        progress(8, "Downloading the local Ollama runtime…")
        _download(url, downloaded, lambda pct, msg: progress(8 + pct * 0.5, msg), "Ollama runtime")
        progress(62, "Installing the local Ollama runtime…")
        try:
            if archive_name.endswith(".zip"):
                with zipfile.ZipFile(downloaded) as archive:
                    _safe_extract(archive, root, archive.infolist())
            elif archive_name.endswith(".tar.zst"):
                _extract_zstd_tar(downloaded, root)
            else:
                with tarfile.open(downloaded, "r:gz") as archive:
                    _safe_extract(archive, root, archive.getmembers())
        finally:
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
        log_path = _models_root() / "ollama.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep downloaded weights inside the user's chosen models folder.
        env_vars = {**os.environ, "OLLAMA_MODELS": str(_models_root() / "ollama-models")}
        with log_path.open("ab") as log:
            subprocess.Popen(
                [str(binary), "serve"], stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, cwd=str(binary.parent), env=env_vars,
            )
        for _ in range(60):
            if _ollama_alive():
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Ollama did not start. Check {log_path} for details.")


def _models_root() -> Path:
    configured = db.get_setting("models_folder", "")
    return Path(configured).expanduser() if configured else CACHE


def _comfy_checkpoints_dir() -> Path:
    configured = db.get_setting("comfy_checkpoint_folder", "")
    return Path(configured).expanduser() if configured else Path(
        env("COMFY_CHECKPOINTS", str(_models_root() / "checkpoints"))
    ).expanduser()


def configure_comfy_checkpoint(path: str) -> dict[str, Any]:
    """Register an existing SDXL checkpoint in the folder ComfyUI searches.

    A hard link or symlink avoids duplicating multi-gigabyte weights where the
    OS permits it; copying is the final cross-volume/Windows fallback.
    """
    source = Path(path).expanduser()
    if not source.is_file() or source.suffix.lower() not in {".safetensors", ".ckpt"}:
        raise RuntimeError("Choose an existing .safetensors or .ckpt checkpoint file.")
    if source.stat().st_size == 0:
        raise RuntimeError("The selected checkpoint file is empty.")
    source = source.resolve()
    folder = _comfy_checkpoints_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    if target.resolve(strict=False) != source:
        if target.exists() or target.is_symlink():
            try:
                if not target.samefile(source):
                    raise RuntimeError(f"A different checkpoint named {source.name} already exists in {folder}.")
            except OSError as exc:
                raise RuntimeError(f"Cannot use the selected checkpoint: {exc}") from exc
        else:
            try:
                os.link(source, target)
            except OSError:
                try:
                    target.symlink_to(source)
                except OSError:
                    free = shutil.disk_usage(folder).free
                    if free < source.stat().st_size + 64 * 1024 * 1024:
                        raise RuntimeError(
                            "This drive cannot link to the selected checkpoint and does not have enough free space to copy it. "
                            "Choose the ComfyUI checkpoints folder or select a file on the same drive."
                        )
                    try:
                        shutil.copy2(source, target)
                    except OSError as exc:
                        target.unlink(missing_ok=True)
                        raise RuntimeError(f"Could not copy the checkpoint into {folder}: {exc}") from exc
    db.set_setting("comfy_checkpoint", target.name)
    db.set_setting("comfy_checkpoint_path", str(target))
    model = next(item for item in CATALOG if item["id"] == "sdxl-1.0")
    _activate(model)
    return {"filename": target.name, "path": str(target), "installed": True}


def _path(model: dict[str, Any]) -> Path | None:
    name = model.get("file")
    if not name:
        return None
    root = _models_root()
    folder = {
        "yolox-onnx": root / "yolo", "ultralytics": root / "yolo", "piper": root / "piper",
    }.get(model["provider"])
    return folder / name if folder else None


def _whisper_dir(model_id: str) -> Path:
    root = _models_root()
    return Path(env("HF_HOME", str(root / "huggingface"))).expanduser() / model_id


def recommended_models(hardware: dict[str, Any] | None = None) -> dict[str, str]:
    """Pick a balanced offline model set for available RAM and GPU memory."""
    snapshot = hardware or hardware_info()
    gpu = snapshot.get("gpu") or {}
    try:
        ram = float(snapshot.get("ram_total_gb") or 8)
    except (TypeError, ValueError):
        ram = 8.0
    try:
        vram = float(gpu.get("vram_total_gb") or snapshot.get("vram_total_gb") or 0)
    except (TypeError, ValueError):
        vram = 0.0
    metal = bool(gpu.get("metal"))
    cuda = bool(gpu.get("cuda"))

    if ram >= 32 and (metal or (cuda and vram >= 12)):
        llm_id, llm_reason = "gemma3:12b", "High-memory / accelerated system — best local writing quality."
    elif ram >= 16 and (metal or (cuda and vram >= 6) or ram >= 32):
        llm_id, llm_reason = "gemma2:7b", "Balanced quality and speed for this memory / accelerator tier."
    else:
        llm_id = "gemma3:4b"
        llm_reason = "Compact 4B model selected to keep inference responsive on limited hardware."

    asr_id = "whisper-medium" if ram >= 16 else "whisper-small"
    asr_reason = (
        "Extra multilingual accuracy; this system has enough memory for Medium."
        if asr_id == "whisper-medium"
        else "Low-memory profile: Small keeps transcription lighter while preserving word timing."
    )
    return {
        asr_id: asr_reason,
        "yolox-nano": "Tiny ONNX detector; fast player tracking with a 4 MB download.",
        llm_id: llm_reason,
    }


async def status() -> list[dict[str, Any]]:
    installed_llm = {item["name"] for item in await tags()}
    persisted = _installed_ids()
    recommendations = recommended_models(hardware_info())
    checkpoint_dir = _comfy_checkpoints_dir()
    configured_checkpoint = db.get_setting("comfy_checkpoint", "sd_xl_base_1.0.safetensors")
    configured_path = Path(db.get_setting("comfy_checkpoint_path", "")).expanduser()
    result = []
    for model in CATALOG:
        installed = model["id"] in persisted
        if model["provider"] == "Ollama":
            selected = str(model["id"])
            installed = installed or any(
                name == selected or name.startswith(f"{selected}:")
                for name in installed_llm
            )
        elif model["provider"] == "faster-whisper":
            short = model["id"].replace("whisper-", "models--Systran--faster-whisper-")
            folder = _whisper_dir(model["id"])
            installed = installed or (
                folder.is_dir() and (folder / "model.bin").is_file()
                or (folder.parent / short / "snapshots").exists()
                or (folder.parent / "hub" / short / "snapshots").exists()
            )
        elif model.get("file") and _path(model):
            target = _path(model)
            installed = installed or bool(target and target.exists())
        elif model["provider"] == "comfyui":
            selected_exists = configured_path.is_file() if str(configured_path) not in {"", "."} else False
            selected_exists = selected_exists or (checkpoint_dir / configured_checkpoint).is_file()
            installed = installed or selected_exists
        elif model.get("needsApi"):
            installed = installed or bool(
                env(API_ENV.get(model["id"], ""))
                or db.get_setting(API_SETTINGS.get(model["id"], ""))
            )
        result.append({
            **model,
            "installed": installed,
            "recommended": model["id"] in recommendations,
            "recommendedReason": recommendations.get(model["id"], ""),
        })
    return result


def _ollama_pull(model_id: str, progress: Callable[[float, str], None]) -> None:
    request = urllib.request.Request(
        f"{ollama_host()}/api/pull",
        data=json.dumps({"name": model_id, "stream": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with https_open(request, timeout=30) as response:
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
    with https_open(request, timeout=60) as response, temp.open("wb") as handle:
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


def _install_wh(model_id: str, progress: Callable[[float, str], None]) -> Path:
    """Download faster-whisper weights directly, without requiring huggingface_hub."""
    repo = f"Systran/faster-whisper-{model_id.replace('whisper-', '')}"
    destination = _whisper_dir(model_id)
    destination.mkdir(parents=True, exist_ok=True)
    files = ["config.json", "tokenizer.json", "model.bin"]
    for index, name in enumerate(files):
        target = destination / name
        if target.exists() and target.stat().st_size > 0:
            continue
        offset = index / len(files) * 100
        span = 100 / len(files)
        url = f"https://huggingface.co/{repo}/resolve/main/{name}?download=true"

        def scoped(pct: float, message: str, offset=offset, span=span, name=name) -> None:
            progress(offset + pct / 100 * span, f"{name}: {message}")

        _download(url, target, scoped, f"Whisper {name}")
    # Vocabulary is optional; faster-whisper accepts several formats.
    for vocab in ("vocabulary.txt", "vocabulary.json"):
        target = destination / vocab
        if target.exists():
            break
        try:
            _download(
                f"https://huggingface.co/{repo}/resolve/main/{vocab}?download=true",
                target, lambda pct, msg: None, f"Whisper {vocab}",
            )
            break
        except Exception:
            target.unlink(missing_ok=True)
    return destination


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
            except ImportError:
                _install_wh(model_id, progress)
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
            destination = _comfy_checkpoints_dir()
            destination.mkdir(parents=True, exist_ok=True)
            checkpoint = destination / "sd_xl_base_1.0.safetensors"
            if not checkpoint.exists():
                _download(str(model["downloadUrl"]), checkpoint, progress, model["name"])
            db.set_setting("comfy_checkpoint", checkpoint.name)
            db.set_setting("comfy_checkpoint_path", str(checkpoint))
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


async def auto_setup(progress: Callable[[float, str], None]) -> dict[str, Any]:
    """Install only the hardware-matched offline models, skipping ready weights."""
    hardware = hardware_info()
    profile = recommended_models(hardware)
    current = await status()
    target = [
        model["id"] for model in current
        if model.get("recommended") and model.get("autoInstall") and not model.get("installed")
    ]
    ram = float(hardware.get("ram_total_gb") or 8)
    progress(2, f"Detected {ram:.1f} GB RAM — preparing {len(target)} recommended model(s)…")
    installed: list[str] = []
    for index, model_id in enumerate(target):
        offset = index / max(len(target), 1) * 100
        span = 100 / max(len(target), 1)

        def scoped(pct: float, message: str, model_id=model_id, offset=offset, span=span) -> None:
            progress(min(99, offset + pct / 100 * span), f"{model_id}: {message}")

        await install(model_id, scoped)
        installed.append(model_id)
    db.set_setting("auto_setup_complete", "1")
    progress(100, "Your hardware-matched offline studio is ready")
    return {"installed": installed, "recommended": list(profile), "hardware": hardware}


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
        with https_open(request, timeout=30):
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
