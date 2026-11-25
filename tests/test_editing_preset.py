"""Real selective project transactions, persistence and actual FFmpeg export."""

from copy import deepcopy
import pytest

from clipos.video.multitrack import MultitrackProject, Media, Lane, Item
from clipos.video.editing_preset import EditingPreset, DEFAULTS, apply_editing_preset


def project(tmp_path):
    return MultitrackProject(
        width=160,
        height=90,
        fps=10,
        media=[
            Media("m1", str(tmp_path / "one.mp4"), 2, True, True),
            Media("m2", str(tmp_path / "two.mp4"), 4, True, True),
        ],
        lanes=[
            Lane("v1", "Video 1", "video", [Item("i1", "m1", 0, 0, 2)]),
            Lane("a1", "Audio 1", "audio", [Item("s1", "m1", 0, 0, 2)]),
            Lane("v2", "Video 2", "video", [Item("i2", "m2", 2, 0, 4, brightness=0.2)]),
            Lane("a2", "Audio 2", "audio", [Item("s2", "m2", 2, 0, 4, gain=0.4)]),
        ],
    ).validate()


def test_color_only_atomic_apply_undo_and_roundtrip(tmp_path):
    p = project(tmp_path)
    before = p.to_dict()
    preset = EditingPreset(
        "Warm", {"color": {"brightness": 0.1, "contrast": 1.2, "saturation": 0.9}}
    )
    assert apply_editing_preset(p, preset, {"m1", "m2"}) == 2
    assert p.lanes[0].items[0].contrast == 1.2
    assert p.lanes[2].items[0].contrast == 1.2
    assert p.lanes[3].items[0].gain == 0.4
    assert p.lanes[2].items[0].at == 2
    path = tmp_path / "preset.json"
    preset.save(path)
    assert EditingPreset.load(path).to_dict() == preset.to_dict()
    assert p.undo() and p.to_dict() == before
    assert p.redo() and p.lanes[0].items[0].contrast == 1.2


def test_audio_relative_fades_adapt_to_different_durations_and_selection(tmp_path):
    p = project(tmp_path)
    preset = EditingPreset(
        "Voice",
        {"audio": {"gain": 0.8, "fade_in_fraction": 0.1, "fade_out_fraction": 0.2}},
    )
    apply_editing_preset(p, preset, {"m2"})
    assert p.lanes[1].items[0].gain == 1
    assert p.lanes[3].items[0].fade_in == pytest.approx(0.4)
    assert p.lanes[3].items[0].fade_out == pytest.approx(0.8)
    assert p.lanes[2].items[0].brightness == 0.2


def test_caption_only_keeps_text_timing_audio_and_color(tmp_path):
    p = project(tmp_path)
    p.add_caption("First dialogue", 0, 1)
    p.add_caption("Second dialogue", 2, 1)
    before = deepcopy(p.to_dict())
    from clipos.captions.caption_engine import CAPTION_STYLES

    style = next(key for key in CAPTION_STYLES if key != "bold_viral")
    preset = EditingPreset(
        "Captions",
        {
            "captions": {
                "caption_style": style,
                "caption_options": {"size_override": 42},
            }
        },
    )
    assert apply_editing_preset(p, preset, {"m1"}) == 1
    captions = [i for l in p.lanes if l.kind == "caption" for i in l.items]
    assert captions[0].caption_style == style and captions[0].text == "First dialogue"
    assert captions[1].caption_style == "bold_viral"
    assert captions[0].at == 0 and captions[0].length == 1
    assert p.to_dict()["lanes"][:4] == before["lanes"][:4]


def test_locked_target_rolls_back_whole_batch_and_rejects_unsupported_data(tmp_path):
    p = project(tmp_path)
    p.lanes[2].locked = True
    before = p.to_dict()
    with pytest.raises(ValueError, match="locked"):
        apply_editing_preset(
            p,
            EditingPreset("Color", {"color": deepcopy(DEFAULTS["color"])}),
            {"m1", "m2"},
        )
    assert p.to_dict() == before
    assert not p.undo()
    with pytest.raises(ValueError):
        EditingPreset("Bad", {"shell": {"command": "execute"}}).validate()
    with pytest.raises(ValueError):
        EditingPreset(
            "Bad",
            {"color": {"brightness": float("nan"), "contrast": 1, "saturation": 1}},
        ).validate()


def test_actual_preset_color_reaches_encoded_output(tmp_path):
    from tests.test_crop_config import source, decode
    from clipos.video.multitrack_render import export_project
    from clipos.core.ffmpeg import probe

    path = source(tmp_path, 160, 90)
    p = MultitrackProject(width=160, height=90, fps=10)
    p.import_media(path)
    original = p.to_dict()
    preset = EditingPreset(
        "Bright", {"color": {"brightness": 0.2, "contrast": 1.0, "saturation": 1.0}}
    )
    apply_editing_preset(p, preset, {p.media[0].id})
    output = tmp_path / "edited.mp4"
    export_project(p, output, tmp_path / "work", encoder="cpu")
    info = probe(output)
    assert (info.video.width, info.video.height) == (160, 90)
    assert decode(output).mean() > decode(path).mean() + 10
    assert p.media[0].path == str(path)
    assert p.undo() and p.to_dict() == original
