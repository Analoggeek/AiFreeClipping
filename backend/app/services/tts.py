"""Optional offline narration with Piper (CPU ONNX voices)."""
from __future__ import annotations

from pathlib import Path

from ..config import CACHE, env

DEFAULT_VOICE = "en_US-lessac-medium"


async def synthesize(text: str, voice: str | None = None, out: Path | None = None) -> str:
    try:
        from piper import PiperVoice  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Piper TTS is not installed. Install with `pip install piper-tts` and download a voice from the Models page."
        ) from exc
    from piper.download import get_voices  # type: ignore

    from ..db import db

    voice_id = voice or env("PIPER_VOICE") or db.get_setting("tts_voice", DEFAULT_VOICE) or DEFAULT_VOICE
    models_root = Path(db.get_setting("models_folder", "") or CACHE).expanduser()
    models_dir = models_root / "piper"
    # Older installs kept Piper voices directly in the default cache directory.
    legacy_dir = CACHE / "piper"
    onnx = models_dir / f"{voice_id}.onnx"
    if not onnx.exists() and (legacy_dir / f"{voice_id}.onnx").exists():
        models_dir, onnx = legacy_dir, legacy_dir / f"{voice_id}.onnx"
    models_dir.mkdir(parents=True, exist_ok=True)
    if not onnx.exists():
        available = get_voices(str(models_dir))
        if voice_id not in available:
            raise RuntimeError(f"Piper voice {voice_id} is not available. Choose another voice.")
        available[voice_id].download(str(models_dir))
    target = out or CACHE / "tts" / f"voice_{abs(hash(text)) % 10**10}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    model = PiperVoice.load(str(onnx))
    with target.open("wb") as handle:
        model.synthesize_wav(text, handle)
    return str(target)
