#!/usr/bin/env python3
"""Generate the bundled sound effects used by the renderer.

Produces three short, royalty-free WAV files in ``resources/sounds/``:

    whoosh.wav   A filtered noise sweep -- used for transitions and punch-ins
    pop.wav      A short click with a pitched body -- used for cut accents
    impact.wav   A low sine thump with a noise transient -- used for openers

Everything is synthesised from scratch, so there are no licensing questions.
"""
from __future__ import annotations

import math
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "resources" / "sounds"
SR = 44100


def _fade(data: np.ndarray, in_s: float = 0.005, out_s: float = 0.05) -> np.ndarray:
    """Apply a short fade-in and a longer fade-out so nothing clicks."""
    n_in = min(len(data), int(in_s * SR))
    n_out = min(len(data), int(out_s * SR))
    if n_in > 1:
        data[:n_in] *= np.linspace(0.0, 1.0, n_in)
    if n_out > 1:
        data[-n_out:] *= np.linspace(1.0, 0.0, n_out)
    return data


def make_whoosh(duration: float = 0.55) -> np.ndarray:
    """Band-passed noise whose centre frequency sweeps upward."""
    n = int(SR * duration)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)

    # White noise, then a swept one-pole band-pass.
    noise = rng.standard_normal(n).astype(np.float32)
    centre = 400 + 2600 * (t / duration) ** 1.4
    band = np.zeros(n, dtype=np.float32)
    state = 0.0
    for i in range(n):
        alpha = min(0.9, 2 * math.pi * centre[i] / SR)
        state += alpha * (noise[i] - state)
        band[i] = state
    band /= max(1e-6, float(np.max(np.abs(band))))

    # Amplitude envelope: swell then fall.
    env = np.sin(np.pi * (t / duration)) ** 1.6
    return _fade(band * env * 0.85)


def make_pop(duration: float = 0.16) -> np.ndarray:
    """A short click: a fast pitch drop plus a noise transient."""
    n = int(SR * duration)
    t = np.arange(n) / SR
    rng = np.random.default_rng(11)

    freq = 900 * np.exp(-t * 28) + 180
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR).astype(np.float32)
    body *= np.exp(-t * 22)

    transient = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 90) * 0.45
    data = body * 0.7 + transient
    data /= max(1e-6, float(np.max(np.abs(data))))
    return _fade(data, 0.001, 0.04)


def make_impact(duration: float = 0.7) -> np.ndarray:
    """A low thump with a short noise attack."""
    n = int(SR * duration)
    t = np.arange(n) / SR
    rng = np.random.default_rng(13)

    pitch = 120 * np.exp(-t * 5.5) + 42
    body = np.sin(2 * np.pi * np.cumsum(pitch) / SR).astype(np.float32)
    body *= np.exp(-t * 4.2)

    attack = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 34) * 0.35
    data = body * 0.85 + attack
    data /= max(1e-6, float(np.max(np.abs(data))))
    return _fade(data, 0.002, 0.12)


def write_wav(path: Path, data: np.ndarray) -> Path:
    pcm = np.int16(np.clip(data, -1.0, 1.0) * 32767)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write_wav(OUT / "whoosh.wav", make_whoosh())
    write_wav(OUT / "pop.wav", make_pop())
    write_wav(OUT / "impact.wav", make_impact())
    for p in sorted(OUT.glob("*.wav")):
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
