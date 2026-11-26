"""Actual audio processing exports and selective non-destructive configuration."""

import numpy as np
import pytest
from tests.test_multitrack import media
from clipos.video.multitrack import MultitrackProject
from clipos.video.studio_audio import AUDIO_EFFECTS, validate_audio_effects
from clipos.video.editing_preset import EditingPreset, apply_editing_preset
from clipos.video.multitrack_render import export_project
from clipos.video.live_playback import stream_frames
from clipos.core.ffmpeg import probe


def test_every_audio_processor_exports_and_roundtrips(media, tmp_path):
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])
    before = p.to_dict()
    for index, (key, values) in enumerate(AUDIO_EFFECTS.items()):
        preset = EditingPreset(
            "Audio",
            {"audio_effects": {"audio_effects": [{"kind": key, "amount": values[-1]}]}},
        )
        assert apply_editing_preset(p, preset, {mid}) == 1
        assert p.lanes[0].items[0].audio_effects == []
        output = tmp_path / f"audio-{index}.mp4"
        export_project(p, output, tmp_path / "work", encoder="cpu")
        info = probe(output)
        assert info.has_audio and abs(info.duration - p.duration) < 0.1
        saved = tmp_path / "assembly.json"
        p.save(saved)
        assert MultitrackProject.load(saved).to_dict() == p.to_dict()
        assert p.undo() and p.to_dict() == before


def test_audio_processors_reach_live_pcm_and_invalid_config_is_atomic(media):
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])

    def samples():
        data = b"".join(
            payload
            for kind, _, payload in stream_frames(p, max_size=160)
            if kind == "audio"
        )
        return np.frombuffer(data, dtype="<i2").astype(float)

    original = samples()
    apply_editing_preset(
        p,
        EditingPreset(
            "Rumble cut",
            {
                "audio_effects": {
                    "audio_effects": [{"kind": "highpass", "amount": 500.0}]
                }
            },
        ),
        {mid},
    )
    processed = samples()
    assert np.sqrt(np.mean(processed**2)) < np.sqrt(np.mean(original**2)) * 0.9
    before = p.to_dict()
    with pytest.raises(ValueError):
        p.change_item(
            p.lanes[1].id,
            p.lanes[1].items[0].id,
            audio_effects=[{"kind": "external-script", "amount": 1.0}],
        )
    assert p.to_dict() == before
    with pytest.raises(ValueError):
        validate_audio_effects([{"kind": "bass", "amount": float("nan")}])
