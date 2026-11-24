"""Shared, measured-signal music ducking for range and edited-timeline exports."""
from __future__ import annotations

import math


def music_mix_parts(voice: str, music_index: int, duration: float,
                    volume: float, ducking: bool, has_voice: bool):
    """Return FFmpeg graph parts and output label (no file/network access).

    Sidechain is the source waveform, not speaker diarization: loud game audio
    also ducks music. amix's default averaging is compensated by volume=2;
    a non-auto-level limiter bounds peaks without boosting quiet passages.
    """
    if isinstance(volume, bool) or not math.isfinite(volume) or not 0 <= volume <= 1:
        raise ValueError('Background music volume must be finite and within 0..1')
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Music mix duration must be positive')
    parts = [f'[{music_index}:a]aresample=48000,aformat=channel_layouts=stereo,'
             f'volume={volume:.6f},atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[musicbed]']
    if ducking and has_voice:
        parts += [f'{voice}asplit=2[voicemix][voicekey]',
                  '[musicbed][voicekey]sidechaincompress=threshold=0.03:ratio=8:'
                  'attack=20:release=350:makeup=1[duckedmusic]']
        voice, bed = '[voicemix]', '[duckedmusic]'
    else:
        bed = '[musicbed]'
    parts.append(f'{voice}{bed}amix=inputs=2:duration=first:dropout_transition=0,'
                 'volume=2,alimiter=limit=0.95:level=0[musicmix]')
    return parts, '[musicmix]'
