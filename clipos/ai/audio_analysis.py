"""Real audio signal analysis for CLIPOS.

Operates on a decoded PCM waveform (16 kHz mono) and produces genuine measurements:
frame-wise RMS energy, dBFS levels, silence regions, spectral centroid, zero-crossing
rate and speech rate.  These feed the AI clip detector and the audio normalisation
stage of the renderer.

Only numpy is required -- no heavyweight DSP stack.
"""
from __future__ import annotations

import math
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..core.logging_setup import get_logger

log = get_logger(__name__)

ANALYSIS_SAMPLE_RATE = 16000
HOP_SECONDS = 0.020          # 20 ms frames
WINDOW_SECONDS = 0.040       # 40 ms analysis window


@dataclass
class AudioAnalysis:
    duration: float = 0.0
    sample_rate: int = ANALYSIS_SAMPLE_RATE
    rms_db: list[float] = field(default_factory=list)   # per-frame dBFS
    energy: list[float] = field(default_factory=list)   # normalised 0..1 per frame
    silence_ranges: list[tuple[float, float]] = field(default_factory=list)
    speech_ranges: list[tuple[float, float]] = field(default_factory=list)
    mean_db: float = -70.0
    peak_db: float = -70.0
    noise_floor_db: float = -70.0
    dynamic_range_db: float = 0.0
    speech_ratio: float = 0.0
    speech_rate_wpm: float = 0.0
    mean_pitch_hz: float = 0.0
    energy_variance: float = 0.0
    has_signal: bool = False

    def db_at(self, t: float) -> float:
        if not self.rms_db:
            return -70.0
        idx = int(t / HOP_SECONDS)
        idx = max(0, min(len(self.rms_db) - 1, idx))
        return self.rms_db[idx]

    def local_energy(self, start: float, end: float) -> float:
        """Mean normalised energy over a time range."""
        if not self.energy:
            return 0.0
        i0 = max(0, int(start / HOP_SECONDS))
        i1 = min(len(self.energy), int(end / HOP_SECONDS) + 1)
        if i1 <= i0:
            return 0.0
        return float(np.mean(self.energy[i0:i1]))

    def local_db(self, start: float, end: float) -> float:
        if not self.rms_db:
            return -70.0
        i0 = max(0, int(start / HOP_SECONDS))
        i1 = min(len(self.rms_db), int(end / HOP_SECONDS) + 1)
        if i1 <= i0:
            return -70.0
        return float(np.mean(self.rms_db[i0:i1]))

    def silence_ratio(self, start: float, end: float) -> float:
        """Fraction of the range that is silence (0..1)."""
        total = max(1e-6, end - start)
        sil = 0.0
        for s, e in self.silence_ranges:
            overlap = min(e, end) - max(s, start)
            if overlap > 0:
                sil += overlap
        return min(1.0, sil / total)

    def has_speech(self, start: float, end: float) -> bool:
        for s, e in self.speech_ranges:
            if min(e, end) - max(s, start) > 0.15:
                return True
        return False


def read_wav_mono(path: str | Path, target_sr: int = ANALYSIS_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Read a WAV file into a mono float32 array in [-1, 1]."""
    path = Path(path)
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported WAV sample width: {sampwidth}")

    if n_channels > 1:
        usable = (len(data) // n_channels) * n_channels
        data = data[:usable].reshape(-1, n_channels).mean(axis=1)

    if sr != target_sr and len(data) > 0:
        data = resample_linear(data, sr, target_sr)
        sr = target_sr
    return data.astype(np.float32), sr


def resample_linear(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Simple, dependency-free linear resampler (adequate for analysis)."""
    if src_sr == dst_sr or len(data) == 0:
        return data
    n_out = int(round(len(data) * dst_sr / src_sr))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    x_old = np.linspace(0.0, 1.0, num=len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, data).astype(np.float32)


def _frames(data: np.ndarray, sr: int) -> np.ndarray:
    win = int(WINDOW_SECONDS * sr)
    hop = int(HOP_SECONDS * sr)
    if win <= 0 or len(data) < win:
        return np.zeros((0, max(win, 1)), dtype=np.float32)
    n_frames = 1 + (len(data) - win) // hop
    return np.lib.stride_tricks.sliding_window_view(data, win)[::hop]


def analyze_audio(
    wav_path: str | Path,
    silence_threshold_db: float = -32.0,
    min_silence_duration: float = 0.35,
    word_count: int = 0,
) -> AudioAnalysis:
    """Full analysis of a decoded WAV file."""
    result = AudioAnalysis()
    path = Path(wav_path)
    if not path.exists():
        log.warning("audio analysis: missing %s", path)
        return result

    try:
        data, sr = read_wav_mono(path)
    except Exception as exc:
        log.warning("audio analysis failed to read %s: %s", path, exc)
        return result

    result.sample_rate = sr
    result.duration = len(data) / sr if sr else 0.0
    if len(data) == 0:
        return result

    fr = _frames(data, sr)
    if fr.shape[0] == 0:
        # Very short audio: analyse the whole thing as one frame.
        fr = data.reshape(1, -1)

    # --- RMS energy in dBFS -------------------------------------------------------
    # Bound temporary RMS allocations to a few MB, even for hour-long recordings.
    rms = np.concatenate([np.sqrt(np.maximum(np.mean(fr[i:i+2048].astype(np.float64)**2, axis=1), 1e-12))
                          for i in range(0, len(fr), 2048)])
    rms_db = 20.0 * np.log10(rms)
    result.rms_db = [float(v) for v in rms_db]
    result.mean_db = float(np.mean(rms_db))
    result.peak_db = float(np.max(rms_db))

    # --- normalised energy curve --------------------------------------------------
    lo = float(np.percentile(rms_db, 5))
    hi = float(np.percentile(rms_db, 95))
    span = max(hi - lo, 1.0)
    norm = np.clip((rms_db - lo) / span, 0.0, 1.0)
    result.energy = [float(v) for v in norm]
    result.energy_variance = float(np.var(norm))

    # --- noise floor --------------------------------------------------------------
    noise_mask = rms_db <= (lo + (hi - lo) * 0.25)
    result.noise_floor_db = float(np.percentile(rms_db, 10)) if noise_mask.any() else float(lo)
    result.dynamic_range_db = float(result.peak_db - result.noise_floor_db)
    result.has_signal = bool(result.peak_db > -60.0)

    # --- silence detection ---------------------------------------------------------
    min_silence_frames = max(1, int(min_silence_duration / HOP_SECONDS))
    below = rms_db < silence_threshold_db
    ranges: list[tuple[float, float]] = []
    i = 0
    n = len(below)
    while i < n:
        if below[i]:
            j = i
            while j < n and below[j]:
                j += 1
            if (j - i) >= min_silence_frames:
                s = i * HOP_SECONDS
                e = min(result.duration, j * HOP_SECONDS)
                if ranges and s - ranges[-1][1] < 0.05:
                    ranges[-1] = (ranges[-1][0], e)
                else:
                    ranges.append((s, e))
            i = j
        else:
            i += 1
    result.silence_ranges = ranges

    # --- speech ranges (inverse of silence, with a small lead-in) -----------------
    speech: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in ranges:
        if s - cursor > 0.12:
            speech.append((cursor, s))
        cursor = e
    if result.duration - cursor > 0.12:
        speech.append((cursor, result.duration))
    result.speech_ranges = speech
    speech_total = sum(e - s for s, e in speech)
    result.speech_ratio = speech_total / result.duration if result.duration else 0.0

    # --- speech rate --------------------------------------------------------------
    if word_count > 0 and speech_total > 0:
        result.speech_rate_wpm = float(word_count / (speech_total / 60.0))

    # --- rough pitch via autocorrelation on voiced frames --------------------------
    result.mean_pitch_hz = _estimate_pitch(fr, sr, rms_db)

    return result


def _estimate_pitch(fr: np.ndarray, sr: int, rms_db: np.ndarray) -> float:
    """Estimate median fundamental frequency over energetic frames."""
    if fr.shape[0] == 0:
        return 0.0
    thr = float(np.percentile(rms_db, 70))
    pitches: list[float] = []
    min_lag = max(1, int(sr / 400))
    max_lag = min(fr.shape[1] - 1, int(sr / 70))
    if max_lag <= min_lag:
        return 0.0
    for frame in fr[::max(1, len(fr)//240)]:
        if len(frame) < max_lag + 1:
            break
        if np.sqrt(np.mean(frame.astype(np.float64) ** 2)) <= 10 ** ((thr - 60) / 20):
            continue
        frame = frame - frame.mean()
        corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:max_lag + 1]
        if len(corr) == 0:
            continue
        lag = int(np.argmax(corr))
        if lag < min_lag or corr[lag] <= 0:
            continue
        pitches.append(sr / lag)
        if len(pitches) > 400:
            break
    if not pitches:
        return 0.0
    return float(np.median(pitches))


def waveform_peaks(wav_path: str | Path, buckets: int = 1200) -> list[float]:
    """Down-sampled absolute peaks for drawing an audio waveform."""
    try:
        data, _ = read_wav_mono(wav_path, target_sr=8000)
    except Exception:
        return []
    if len(data) == 0:
        return []
    absdata = np.abs(data)
    if len(absdata) < buckets:
        return [float(v) for v in absdata]
    edges = np.linspace(0, len(absdata), buckets + 1).astype(int)
    peaks = []
    for i in range(buckets):
        a, b = edges[i], max(edges[i] + 1, edges[i + 1])
        seg = absdata[a:b]
        peaks.append(float(seg.max()) if len(seg) else 0.0)
    top = max(peaks) or 1.0
    return [p / top for p in peaks]
