"""Measured music-frequency attenuation from actual dialogue-driven FFmpeg PCM."""

from copy import deepcopy
import subprocess
import numpy as np
import pytest

from clipos.core.ffmpeg import require_ffmpeg, probe
from clipos.video.multitrack import MultitrackProject
from clipos.video.studio_audio import DUCK_DEFAULTS, ducking_graph
from clipos.video.live_playback import stream_frames
from clipos.video.multitrack_render import export_project
from clipos.video.editing_preset import EditingPreset, apply_editing_preset


def create_audio(tmp_path, name, frequency, duration):
    path = tmp_path / (name + ".wav")
    subprocess.run(
        [
            require_ffmpeg(),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def pcm(project):
    payload = b"".join(
        data
        for kind, _, data in stream_frames(project, max_size=160)
        if kind == "audio"
    )
    return np.frombuffer(payload, dtype="<i2").reshape(-1, 2).mean(axis=1) / 32768


def amplitude(data, start, end, frequency=1000):
    a, b = round(start * 48000), round(end * 48000)
    segment = data[a:b]
    time = np.arange(a, b) / 48000
    return abs(np.mean(segment * np.exp(-2j * np.pi * frequency * time))) * 2


def test_real_ducking_reduces_only_music_during_dialogue_and_recovers(tmp_path):
    voice = create_audio(tmp_path, "voice", 400, 1)
    music = create_audio(tmp_path, "music", 1000, 4)
    p = MultitrackProject(width=160, height=90, fps=10)
    p.import_media(voice, at=1)
    music_id = p.import_media(music)
    p.lanes[1].items[0].audio_role = "music"
    original = pcm(p)
    before = p.to_dict()
    settings = deepcopy(DUCK_DEFAULTS)
    settings.update(threshold_db=-40.0, ratio=10.0, release_ms=100.0)
    preset = EditingPreset(
        "Dialogue duck", {"audio_routing": {"audio_role": "music", "ducking": settings}}
    )
    assert apply_editing_preset(p, preset, {music_id}) == 1
    ducked = pcm(p)
    assert amplitude(ducked, 1.4, 1.9) < amplitude(original, 1.4, 1.9) * 0.5
    assert amplitude(ducked, 0.2, 0.7) > amplitude(original, 0.2, 0.7) * 0.9
    assert amplitude(ducked, 3.2, 3.7) > amplitude(original, 3.2, 3.7) * 0.9
    # Batch window after dialogue ends must not falsely claim a missing driver.
    output = tmp_path / "music-gap.mp4"
    export_project(p, output, tmp_path / "work", encoder="cpu", window=(3.0, 0.5))
    assert probe(output).has_audio
    seek_bytes = b"".join(
        data
        for kind, _, data in stream_frames(p, start=2.05, max_size=160)
        if kind == "audio"
    )
    seek_pcm = (
        np.frombuffer(seek_bytes, dtype="<i2").reshape(-1, 2).mean(axis=1) / 32768
    )
    assert amplitude(seek_pcm, 0.05, 0.2) == pytest.approx(
        amplitude(ducked, 2.1, 2.25), rel=0.08
    )
    saved = tmp_path / "assembly.json"
    p.save(saved)
    assert MultitrackProject.load(saved).to_dict() == p.to_dict()
    assert p.undo() and p.to_dict() == before


def test_ducking_requires_explicit_dialogue_role_and_valid_parameters():
    with pytest.raises(ValueError, match="dialogue"):
        ducking_graph([("[music]", "music", deepcopy(DUCK_DEFAULTS))], 2.0)
    # Voice elsewhere on timeline is valid; this interval contains silence only.
    assert ducking_graph(
        [("[music]", "music", deepcopy(DUCK_DEFAULTS))], 2.0, dialogue_available=True
    ) == ([], ["[music]"])
    with pytest.raises(ValueError):
        ducking_graph([("[x]", "dialogue", deepcopy(DUCK_DEFAULTS))], 2.0)
