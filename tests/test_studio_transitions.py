"""All forty alpha recipe combinations render through the real export graph."""

from tests.test_multitrack import media
from clipos.video.studio_transitions import transition_recipes
from clipos.video.multitrack import MultitrackProject
from clipos.video.multitrack_render import export_project
from clipos.core.ffmpeg import probe
import pytest


def test_forty_recipes_render_real_overlap(media, tmp_path):
    p = MultitrackProject(width=160, height=90, fps=10)
    p.import_media(media[0])
    p.import_media(media[1], at=1)
    incoming = p.lanes[2].items[0]
    recipes = transition_recipes()
    assert len(recipes) == 40
    for index, key in enumerate(recipes):
        p.add_dissolve(p.lanes[2].id, incoming.id, 0.6, mode=key)
        output = tmp_path / f"transition-{index}.mp4"
        export_project(p, output, tmp_path / "work", encoder="cpu", window=(1, 0.8))
        info = probe(output)
        assert info.has_audio and info.video.width == 160
        p.undo()
    before = p.to_dict()
    with pytest.raises(ValueError):
        p.add_dissolve(p.lanes[2].id, incoming.id, 2, mode="left_smooth")
    assert p.to_dict() == before
