"""Original preset counts and actual rendered previews, not asset-pack claims."""

import json
import subprocess
import pytest

from tests.test_multitrack import media
from clipos.captions.caption_engine import CAPTION_STYLES
from clipos.captions.original_styles import original_style_keys
from clipos.video.creative_templates import templates
from clipos.video.editing_preset import EditingPreset, apply_editing_preset
from clipos.video.multitrack import MultitrackProject, Item
from clipos.video.overlay_tracks import write_caption
from clipos.video.multitrack_render import export_project
from clipos.video.renderer import _ass_filter
from clipos.core.ffmpeg import require_ffmpeg, probe


def test_fifty_original_styles_are_distinct_and_all_render(tmp_path):
    keys = original_style_keys()
    assert len(keys) == len(set(keys)) == 50
    signatures = set()
    for index, key in enumerate(keys):
        style = CAPTION_STYLES[key]
        data = style.to_dict()
        data.pop("key")
        data.pop("name")
        data.pop("description")
        signatures.add(json.dumps(data, sort_keys=True))
        cue = Item(
            "caption",
            "",
            0,
            0,
            2,
            text="Create your story",
            caption_style=key,
            caption_words=[
                {"w": "Create", "s": 0.0, "e": 0.5},
                {"w": "your", "s": 0.5, "e": 1.0},
                {"w": "story", "s": 1.0, "e": 1.5},
            ],
        )
        ass = tmp_path / "preview.ass"
        write_caption(ass, cue, 360, 640)
        output = tmp_path / f"{index}.png"
        subprocess.run(
            [
                require_ffmpeg(),
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=360x640:r=10:d=1",
                "-vf",
                _ass_filter(ass),
                "-ss",
                "0.6",
                "-frames:v",
                "1",
                "-threads",
                "1",
                str(output),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        assert output.stat().st_size > 100
    assert len(signatures) == 50


def test_fifty_original_recipe_templates_validate_and_preserve_structure(
    media, tmp_path
):
    catalog = templates()
    assert len(catalog) == 50
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])
    p.add_caption("Review this edit", 0, 1)
    before = p.to_dict()
    for recipe in catalog.values():
        assert recipe["required_assets"] == []
        preset = EditingPreset.from_dict(recipe["preset"])
        apply_editing_preset(p, preset, {mid})
        assert p.media[0].path == str(media[0])
        assert p.lanes[-1].items[0].text == "Review this edit"
        assert p.undo() and p.to_dict() == before
    # Exercise all five treatment variants through actual captioned media export.
    for index, recipe in enumerate(list(catalog.values())[:5]):
        apply_editing_preset(p, EditingPreset.from_dict(recipe["preset"]), {mid})
        output = tmp_path / f"template-{index}.mp4"
        export_project(p, output, tmp_path / "work", encoder="cpu", window=(0, 0.5))
        info = probe(output)
        assert info.has_audio and info.video.width == 160
        p.undo()
