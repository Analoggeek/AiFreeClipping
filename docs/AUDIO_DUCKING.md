# Local background music mixing and ducking

This increment implements actual signal-driven music ducking and fixes two
existing inconsistencies: music level could attenuate the source-audio filter,
and edited-timeline exports did not include selected background music.

## Actual behavior

- `bgm_volume` applies only to a separate music branch. It no longer attenuates
  foreground audio in `_build_audio_filter`.
- Range exports (including silence-cut keeps) and edited-segment timeline exports
  use the same `music_mix_parts` implementation.
- Selected local audio loops and trims to edited output duration, including
  speed-adjusted segment durations. It is mixed after the edited source audio.
- `bgm_ducking=True` splits the source waveform into audible source and compressor
  sidechain. FFmpeg `sidechaincompress` reduces the music using threshold 0.03,
  ratio 8, attack 20 ms and release 350 ms. It does not reduce foreground gain.
- No-source-audio exports bypass the compressor. Muted source segments naturally
  supply a silent key. Ducking can be disabled for a fixed-level mix.
- FFmpeg amix averaging is compensated, followed by a 0.95 peak limiter with
  automatic level boosting disabled. This bounds peaks, not a certified LUFS
  output target. Limiter buffering can introduce a small audio delay.
- Missing selected music fails with an actionable error instead of silently
  exporting without it. Invalid audio content still produces a real FFmpeg error.
- Settings now exposes local audio selection/clear, music level and ducking.
  Preferences flow through shared render settings, JSON settings export/import,
  and both render entrypoints. The bounded agent can change ducking/level, but
  does not receive arbitrary filesystem selection privileges.
- Existing source denoising and dynamic gain filters remain available. Dynamic
  gain normalization is not described as measured two-pass loudness compliance.

## Evidence

Selected regression command includes `test_audio_ducking.py`, animated caption,
creator export, history/recovery, reference activity, encoder and local-agent
coverage (excluding two Qt-import tests blocked by missing native libGL).
Result: **189 passed, 2 deselected**, 8.62 seconds.

New real FFmpeg PCM tests use distinct 440 Hz source and 1000 Hz music signals.
Spectral measurements verify music attenuation during source activity, recovery
in silence, preserved source amplitude, independently adjustable music level,
and bounded peaks. Four actual audiovisual export cases cover range/timeline ×
ducking on/off, including a speed edit and music looping beyond its source length.
Additional tests check invalid volume, no-audio graph behavior, missing-file errors
and persisted settings/agent validation. GUI changes were syntax-checked, not
native-interaction tested in this sandbox.

## Not completed by this increment

Ducking responds to all loud source audio: game effects/music can activate it.
It is not VAD, diarization, audiovisual active-speaker recognition, voice/source
separation, semantic audio enhancement, multitrack automation, or a full audio
workstation. User-controlled compressor parameters, integrated waveform curves,
manual music offsets, native visual/listening acceptance and long/4K benchmarks
remain pending. Default empty music selection adds no new mixing stage.
