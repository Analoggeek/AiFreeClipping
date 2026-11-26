"""Procedural, royalty-free sound effects generated locally (no sample downloads)."""
from __future__ import annotations

import math
import random
import wave
from pathlib import Path

from ..config import CACHE

FOLDER = CACHE / "sfx"
NAMES = ("whoosh", "pop", "riser", "impact", "click", "sparkle")


def _render(name: str, seconds: float, rate: int = 44100) -> list[float]:
    count = int(seconds * rate)
    samples: list[float] = []
    rng = random.Random(1337 + NAMES.index(name) if name in NAMES else 1337)
    smooth = 0.0
    for i in range(count):
        t = i / rate
        progress = i / max(count - 1, 1)
        noise = rng.uniform(-1, 1)
        smooth = smooth * 0.86 + noise * 0.14
        if name == "whoosh":
            envelope = math.sin(math.pi * progress) ** 1.5
            value = smooth * envelope * (0.6 + 0.4 * math.sin(2 * math.pi * (200 + 900 * progress) * t))
        elif name == "pop":
            freq = 700 - 500 * progress
            value = math.sin(2 * math.pi * freq * t) * math.exp(-9 * progress)
        elif name == "riser":
            freq = 180 + 1200 * progress
            value = (math.sin(2 * math.pi * freq * t) * 0.5 + smooth * 0.25) * progress
        elif name == "impact":
            value = (math.sin(2 * math.pi * (90 - 50 * progress) * t) * 0.7 + smooth * 0.5) * math.exp(-4 * progress)
        elif name == "click":
            value = smooth * math.exp(-40 * progress)
        elif name == "sparkle":
            value = sum(
                math.sin(2 * math.pi * (900 + k * 720) * t) * math.exp(-14 * ((progress - 0.12 * k) ** 2))
                for k in range(4)
            ) / 4
        else:
            value = 0.0
        samples.append(max(-1.0, min(1.0, value * 0.85)))
    return samples


def sfx_path(name: str) -> Path:
    """Return (and create if needed) a WAV file for a named sound effect."""
    if name not in NAMES:
        raise ValueError(f"Unknown sound effect: {name}. Choose from {', '.join(NAMES)}")
    FOLDER.mkdir(parents=True, exist_ok=True)
    target = FOLDER / f"{name}.wav"
    if not target.exists():
        duration = 0.7 if name in ("whoosh", "riser") else 0.35
        samples = _render(name, duration)
        with wave.open(str(target), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(44100)
            handle.writeframes(b"".join(int(s * 32767).to_bytes(2, "little", signed=True) for s in samples))
    return target


def list_sfx() -> list[str]:
    return list(NAMES)
