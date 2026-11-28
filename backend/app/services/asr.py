"""Local speech-to-text with faster-whisper (word-level timestamps for karaoke captions)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from ..config import CACHE, env

_MODELS: dict[tuple, Any] = {}


def _resolve_whisper_model(model: str | None = None) -> str:
    """Resolve installed local weights only; caption inference must not fetch a model."""
    from ..db import db

    selected_setting = model or env("WHISPER_MODEL") or db.get_setting("whisper_model", "")
    selected = selected_setting or "small"
    selected_path = Path(selected).expanduser()
    if selected_path.is_dir() and (selected_path / "model.bin").is_file():
        return str(selected_path)
    selected = selected.removeprefix("whisper-")

    models_root = Path(db.get_setting("models_folder", "") or CACHE).expanduser()
    hf_root = Path(env("HF_HOME", str(models_root / "huggingface"))).expanduser()
    installed_path = hf_root / f"whisper-{selected}"
    if installed_path.is_dir() and (installed_path / "model.bin").is_file():
        return str(installed_path)

    repo_cache = f"models--Systran--faster-whisper-{selected}"
    for cache_root in (hf_root, hf_root / "hub"):
        snapshots = cache_root / repo_cache / "snapshots"
        if snapshots.is_dir():
            candidates = sorted(snapshots.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
            for candidate in candidates:
                if candidate.is_dir() and (candidate / "model.bin").is_file():
                    return str(candidate)

    configured = env("WHISPER_MODEL_PATH") or db.get_setting("WHISPER_MODEL_PATH", "")
    configured_path = Path(configured).expanduser() if configured else None
    if configured_path and configured_path.is_dir() and (configured_path / "model.bin").is_file():
        configured_model = configured_path.name.removeprefix("whisper-")
        if not selected_setting or configured_model == selected:
            return str(configured_path)
    raise RuntimeError(
        f"Whisper {selected} is not installed locally. Install a Whisper model from the Models page; "
        "caption transcription runs on-device and does not download models while working."
    )


def _load(size: str, device: str, compute: str):
    key = (size, device, compute)
    if key not in _MODELS:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper, or install the Whisper model from the Models page."
            ) from exc
        _MODELS[key] = WhisperModel(size, device=device, compute_type=compute)
    return _MODELS[key]


async def transcribe(
    path: str,
    model: str | None = None,
    language: str | None = None,
    word_timestamps: bool = True,
    on_progress=None,
) -> dict[str, Any]:
    # Resolve activation from the persisted settings database as well as env,
    # so a downloaded model remains selected after relaunching the desktop app.
    size = _resolve_whisper_model(model)
    device = "cpu"
    compute = "int8"
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            device, compute = "cuda", "float16"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device, compute = "mps", "float16"
    except Exception:
        pass
    if env("WHISPER_DEVICE"):
        device = env("WHISPER_DEVICE")
    if env("WHISPER_COMPUTE"):
        compute = env("WHISPER_COMPUTE")
    if on_progress:
        on_progress(5, f"Loading Whisper {size} on {device}…")
    whisper = await asyncio.to_thread(_load, size, device, compute)
    if on_progress:
        on_progress(25, "Transcribing audio…")

    def work():
        segments, info = whisper.transcribe(
            path,
            language=language,
            word_timestamps=word_timestamps,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            beam_size=5,
        )
        result_segments = []
        for segment in segments:
            words = []
            for word in segment.words or []:
                words.append(
                    {
                        "word": word.word,
                        "start": round(float(word.start), 3),
                        "end": round(float(word.end), 3),
                        "probability": round(float(word.probability), 3),
                    }
                )
            result_segments.append(
                {
                    "start": round(float(segment.start), 3),
                    "end": round(float(segment.end), 3),
                    "text": segment.text.strip(),
                    "words": words,
                }
            )
        return result_segments, info

    segments, info = await asyncio.to_thread(work)
    if on_progress:
        on_progress(90, "Transcript ready")
    return {
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "duration": float(info.duration or 0),
        "model": size,
        "segments": segments,
        "text": " ".join(s["text"] for s in segments),
    }
