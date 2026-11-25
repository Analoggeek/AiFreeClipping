"""Actual supported FFmpeg effects; no claim of twenty distinct algorithms."""

from copy import deepcopy
import pytest
from tests.test_multitrack import media
from clipos.video.studio_effects import EFFECTS, effect_recipes, validate_effects
from clipos.video.multitrack import MultitrackProject
from clipos.video.multitrack_render import export_project
from clipos.video.editing_preset import EditingPreset, apply_editing_preset
from clipos.video.live_playback import stream_frames
from clipos.core.ffmpeg import probe


def test_all_effect_primitives_and_twenty_recipes_render(media, tmp_path):
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])
    before = p.to_dict()
    configurations = [
        [{"kind": key, "amount": values[-1]}] for key, values in EFFECTS.items()
    ] + list(effect_recipes().values())
    assert len(effect_recipes()) == 20
    for index, effects in enumerate(configurations):
        apply_editing_preset(
            p,
            EditingPreset("Effects", {"effects": {"effects": deepcopy(effects)}}),
            {mid},
        )
        output = tmp_path / f"effect-{index}.mp4"
        export_project(p, output, tmp_path / "work", encoder="cpu", window=(0, 0.3))
        assert probe(output).has_audio
        assert p.undo() and p.to_dict() == before


def test_effect_stream_uses_same_graph_and_rejects_injection(media):
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])
    apply_editing_preset(
        p,
        EditingPreset(
            "Swap", {"effects": {"effects": [{"kind": "rgb_swap", "amount": 1.0}]}}
        ),
        {mid},
    )
    stream = stream_frames(p, max_size=160)
    try:
        for kind, _, payload in stream:
            if kind == "video":
                assert payload[5, 5, 2] > payload[5, 5, 0] + 100
                break
    finally:
        stream.close()
    with pytest.raises(ValueError):
        validate_effects([{"kind": "movie=https://evil.invalid/file", "amount": 1.0}])
    with pytest.raises(ValueError):
        validate_effects([{"kind": "blur", "amount": float("nan")}])
