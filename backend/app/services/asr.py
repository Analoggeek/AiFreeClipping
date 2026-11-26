"""Local speech-to-text with faster-whisper (word-level timestamps for karaoke captions)."""
from __future__ import annotations

import asyncio
import os
from typing import Any

from ..config import env

_MODELS: dict[tuple, Any] = {}


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
    size = model or env("WHISPER_MODEL", "small")
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
