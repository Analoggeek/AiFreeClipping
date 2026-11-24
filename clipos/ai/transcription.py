"""Offline speech-to-text using faster-whisper.

Models are downloaded once into the CLIPOS model directory and then work with no
network access.  If faster-whisper or its models are not installed, the module raises
``TranscriptionUnavailable`` and the pipeline falls back to an energy-only analysis
that still produces usable (but less precise) clip boundaries -- it never fabricates
transcript text.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..core.config import PATHS
from ..core.logging_setup import get_logger

log = get_logger(__name__)

WHISPER_SIZES = {
    "tiny": ("Systran/faster-whisper-tiny", "~75 MB"),
    "base": ("Systran/faster-whisper-base", "~145 MB"),
    "small": ("Systran/faster-whisper-small", "~480 MB"),
    "medium": ("Systran/faster-whisper-medium", "~1.5 GB"),
    "large-v3": ("Systran/faster-whisper-large-v3", "~3.1 GB"),
}

_download_lock = threading.Lock()


class TranscriptionUnavailable(RuntimeError):
    """Raised when no STT backend can be used."""


@dataclass
class Word:
    word: str
    start: float
    end: float
    probability: float = 1.0

    def to_dict(self) -> dict:
        return {"w": self.word, "s": round(self.start, 3), "e": round(self.end, 3),
                "p": round(self.probability, 3)}


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "words": [w.to_dict() for w in self.words],
            "no_speech_prob": round(self.no_speech_prob, 4),
        }


@dataclass
class Transcript:
    language: str = "en"
    duration: float = 0.0
    text: str = ""
    segments: list[Segment] = field(default_factory=list)
    model: str = ""

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def segments_as_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self.segments]

    def text_between(self, start: float, end: float) -> str:
        parts = [
            s.text.strip()
            for s in self.segments
            if s.end > start and s.start < end
        ]
        return " ".join(p for p in parts if p)

    def words_between(self, start: float, end: float) -> list[Word]:
        out: list[Word] = []
        for seg in self.segments:
            for w in seg.words:
                if w.end > start and w.start < end:
                    out.append(w)
        return out


def faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def local_model_path(size: str) -> Path | None:
    """Locate actual model files; partial downloads/cache metadata are not models."""
    repo, _ = WHISPER_SIZES.get(size, WHISPER_SIZES["base"])
    folder = "models--" + repo.replace("/", "--")
    roots = [PATHS.models / "whisper" / repo.replace("/", "--"),
             PATHS.models / "whisper" / folder,
             Path(os.environ.get("HF_HOME", str(PATHS.models / "huggingface"))) / "hub" / folder]
    required = ("model.bin", "config.json", "tokenizer.json")
    for root in roots:
        candidates = [root] + sorted((root / "snapshots").glob("*"))
        for candidate in candidates:
            if all((candidate / name).is_file() and (candidate / name).stat().st_size > 0 for name in required):
                return candidate
    return None


def model_installed(size: str) -> bool:
    return local_model_path(size) is not None


class _DownloadProgressBar:
    """A tqdm-compatible progress bar that reports real downloaded bytes.

    ``huggingface_hub`` uses ``tqdm`` for its downloads.  Substituting this
    class lets the UI show the true percentage rather than an indeterminate
    spinner, and it keeps the callback off the download thread's hot path.
    """

    # Set by ``download_whisper_model`` just before the download starts.
    # It is stored in a one-element list because a plain function assigned as a
    # class attribute becomes a bound method when read through ``self``.
    _callback_box: list = []

    def __init__(self, *args, **kwargs) -> None:
        self._cb = self._callback_box[0] if self._callback_box else None
        self._last = 0.0
        self._done = 0
        self.n = 0
        self.total = 0
        try:
            self.total = int(kwargs.get("total", 0) or 0)
        except Exception:
            self.total = 0

    def update(self, n: int = 1) -> None:
        self.n += n
        self._done += n
        if not self._cb:
            return
        pct = (self._done / self.total * 100.0) if self.total else 0.0
        if pct - self._last >= 1.0 or pct >= 99.5:
            self._last = pct
            mb = self._done / (1024 * 1024)
            total_mb = self.total / (1024 * 1024) if self.total else 0.0
            self._cb(min(99.0, pct), f"Downloading — {mb:.1f} of {total_mb:.1f} MB")

    def set_description(self, *args, **kwargs) -> None:
        return None

    def set_postfix(self, *args, **kwargs) -> None:
        return None

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def download_whisper_model(
    size: str = "base",
    progress_cb: Callable[[float, str], None] | None = None,
) -> bool:
    """Download a whisper model into the local CLIPOS model store."""
    repo, approx = WHISPER_SIZES.get(size, WHISPER_SIZES["base"])
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except Exception as exc:
        log.error("huggingface_hub unavailable: %s", exc)
        if progress_cb:
            progress_cb(0.0, "huggingface_hub is not installed")
        return False

    local_dir = PATHS.models / "whisper" / repo.replace("/", "--")
    local_dir.mkdir(parents=True, exist_ok=True)
    with _download_lock:
        try:
            if progress_cb:
                progress_cb(0.0, f"Connecting to {repo}...")
            _DownloadProgressBar._callback_box = [progress_cb] if progress_cb else []
            snapshot_download(
                repo_id=repo,
                local_dir=str(local_dir),
                allow_patterns=[
                    "*.json", "*.txt", "*.bin", "*.model", "*.pt", "*.safetensors",
                ],
                ignore_patterns=["*.h5", "*.msgpack", "*.onnx", "*.tflite"],
                tqdm_class=_DownloadProgressBar,
            )
            if not model_installed(size):
                raise RuntimeError("Download finished without complete speech model files")
            if progress_cb:
                progress_cb(100.0, f"{repo} ready")
            return True
        except Exception as exc:
            log.error("model download failed for %s: %s", repo, exc)
            if progress_cb:
                progress_cb(0.0, f"Download failed: {exc}")
            return False


def _resolve_device(prefer: str = "auto") -> tuple[str, str]:
    """Return (device, compute_type) for faster-whisper."""
    if prefer == "cpu":
        return "cpu", "int8"
    # CTranslate2 supports CUDA and CPU, not PyTorch's MPS device.
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def transcribe(
    audio_path: str | Path,
    model_size: str = "base",
    language: str | None = None,
    device: str = "auto",
    progress_cb: Callable[[float, str], None] | None = None,
    vad: bool = True,
    threads: int = 0,
) -> Transcript:
    """Transcribe an audio file offline. Raises TranscriptionUnavailable if not possible."""
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise TranscriptionUnavailable(f"Audio file not found: {audio_path}")
    if not faster_whisper_available():
        raise TranscriptionUnavailable(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        )

    from faster_whisper import WhisperModel  # type: ignore

    dev, ctype = _resolve_device(device)
    if progress_cb:
        progress_cb(5.0, f"Loading model '{model_size}' on {dev}")

    from ..core.hardware import suggest_worker_threads
    try:
        model = WhisperModel(
            str(local_model_path(model_size) or model_size), device=dev, compute_type=ctype,
            download_root=str(PATHS.models / "whisper"),
            local_files_only=True,
            cpu_threads=suggest_worker_threads(threads),
        )
    except Exception as exc:
        raise TranscriptionUnavailable(f"Could not load whisper model '{model_size}': {exc}") from exc

    if progress_cb:
        progress_cb(15.0, "Transcribing audio")

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language or None,
        vad_filter=vad,
        vad_parameters={"min_silence_duration_ms": 400},
        word_timestamps=True,
        beam_size=5,
        condition_on_previous_text=False,
    )

    segments: list[Segment] = []
    total = float(getattr(info, "duration", 0.0) or 0.0)
    for seg in segments_iter:
        words = [
            Word(
                word=(w.word or "").strip(),
                start=float(w.start),
                end=float(w.end),
                probability=float(getattr(w, "probability", 1.0) or 0.0),
            )
            for w in (seg.words or [])
        ]
        segments.append(
            Segment(
                start=float(seg.start),
                end=float(seg.end),
                text=(seg.text or "").strip(),
                words=words,
                no_speech_prob=float(getattr(seg, "no_speech_prob", 0.0) or 0.0),
                avg_logprob=float(getattr(seg, "avg_logprob", 0.0) or 0.0),
            )
        )
        if progress_cb and total > 0:
            pct = 15.0 + min(80.0, (seg.end / total) * 80.0)
            progress_cb(pct, f"Transcribing… {seg.end:.0f}s / {total:.0f}s")

    full_text = " ".join(s.text for s in segments if s.text).strip()
    return Transcript(
        language=getattr(info, "language", language or "en") or "en",
        duration=total or (segments[-1].end if segments else 0.0),
        text=full_text,
        segments=segments,
        model=model_size,
    )


def punctuation_and_casing(text: str) -> str:
    """Light post-processing of raw whisper text (whisper already punctuates)."""
    if not text:
        return ""
    out = " ".join(text.split())
    out = out.replace(" ,", ",").replace(" .", ".").replace(" !", "!").replace(" ?", "?")
    out = out.replace(" n't", "n't").replace(" 's", "'s").replace(" 'm", "'m")
    out = out.replace(" 're", "'re").replace(" 'll", "'ll").replace(" 've", "'ve")
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    if out and out[-1] not in ".!?":
        out += "."
    return out
