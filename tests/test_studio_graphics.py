"""Real original plates, replaceable text/logo, alpha animation and compositing."""

from copy import deepcopy
import av
import numpy as np
from PIL import Image
import pytest

from tests.test_multitrack import media
from clipos.video.studio_graphics import graphic_catalog, render_graphic, inspect_logo
from clipos.video.multitrack import MultitrackProject
from clipos.video.multitrack_render import export_project
from clipos.core.ffmpeg import probe


def spec(template):
    return {
        "template": template,
        "title": "Original title",
        "subtitle": "Local subtitle",
        "logo_path": "",
        "logo_sha256": "",
        "width": 160,
        "height": 288,
        "fps": 10,
        "duration": 1.0,
        "animation": "fade",
    }


def test_all_original_asset_plates_render_both_animations_with_real_alpha(tmp_path):
    catalog = graphic_catalog()
    assert len(catalog) == 50
    for key in catalog:
        for animation in ("fade", "slide"):
            settings = spec(key)
            settings["animation"] = animation
            output = render_graphic(settings, tmp_path)
            info = probe(output)
            assert info.has_video and not info.has_audio
            with av.open(str(output)) as container:
                frames = [
                    f.to_ndarray(format="rgba") for f in container.decode(video=0)
                ]
            assert 9 <= len(frames) <= 11
            assert frames[5][:, :, 3].max() > 200 and frames[5][:, :, 3].min() == 0
            assert frames[0][:, :, 3].max() < 10


def test_logo_replacement_graphic_project_and_final_composite(media, tmp_path):
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (32, 32), "lime").save(logo)
    settings = spec("slate_lower_third")
    settings["logo_path"], settings["logo_sha256"] = inspect_logo(logo)
    graphic = render_graphic(settings, tmp_path)
    p = MultitrackProject(width=160, height=288, fps=10)
    p.import_media(media[0])
    mid = p.import_media(graphic)
    next(m for m in p.media if m.id == mid).graphic = deepcopy(settings)
    p.validate()
    saved = tmp_path / "assembly.json"
    p.save(saved)
    assert MultitrackProject.load(saved).media[-1].graphic["title"] == "Original title"
    final = tmp_path / "composited.mp4"
    export_project(p, final, tmp_path / "work", encoder="cpu")
    with av.open(str(final)) as container:
        frames = [f.to_ndarray(format="rgb24") for f in container.decode(video=0)]
    # Outside graphic stays red; the original geometric plate visibly overlays it.
    assert frames[5][20, 20, 0] > 200
    assert frames[5][240, 20, 0] < 150
    Image.new("RGBA", (32, 32), "blue").save(logo)
    with pytest.raises(ValueError, match="changed"):
        render_graphic(settings, tmp_path)
    assert graphic.is_file()


def test_physical_sync_stimulus_has_digital_flash_and_click(tmp_path):
    from scripts.create_av_sync_fixture import create

    path = create(tmp_path / "sync.mov", 3)
    with av.open(str(path)) as container:
        frames = [f.to_ndarray(format="rgb24") for f in container.decode(video=0)]
    assert len(frames) == 180
    for n in range(180):
        assert (frames[n].mean() > 240) == (n % 60 == 0)
    with av.open(str(path)) as container:
        audio = np.concatenate(
            [f.to_ndarray().reshape(-1) for f in container.decode(audio=0)]
        )
    for second in range(3):
        assert np.max(np.abs(audio[second * 48000 : second * 48000 + 480])) > 1000
        assert np.max(np.abs(audio[second * 48000 + 500 : (second + 1) * 48000])) == 0
    with pytest.raises(FileExistsError):
        create(path, 3)


def test_asset_catalog_is_original_unique_rgba_with_valid_editable_slots():
    import hashlib
    from clipos.core.resources import resource_dir

    catalog = graphic_catalog()
    hashes = set()
    for key, entry in catalog.items():
        path = resource_dir("templates") / "motion" / entry["asset"]
        assert path.name == key + ".png"
        hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        with Image.open(path) as image:
            assert image.mode == "RGBA" and image.size == (720, 1280)
            for slot in ("title_box", "subtitle_box", "logo_box"):
                x, y, w, h = entry[slot]
                assert 0 <= x < x + w <= image.width and 0 <= y < y + h <= image.height
    assert len(hashes) == len(catalog)


def test_fifty_pack_manifests_and_separate_scene_artwork():
    import json
    from clipos.core.resources import resource_dir

    root = resource_dir("templates") / "motion"
    for key, entry in graphic_catalog().items():
        pack = json.loads((root / (key + ".pack.json")).read_text())
        assert pack["id"] == key and pack["design"] == entry
        assert pack["license"] == "CC0-1.0"
        assert pack["editable"] == ["title", "subtitle", "logo"]
        if key.startswith("scene_"):
            with (
                Image.open(root / entry["artwork"]) as art,
                Image.open(root / entry["panel"]) as panel,
                Image.open(root / entry["asset"]) as plate,
            ):
                composed = Image.alpha_composite(panel, art)
                assert composed.tobytes() == plate.tobytes()


def test_all_fifty_original_design_packs_export_with_recipe_license_and_no_overwrite(
    tmp_path,
):
    import json, zipfile
    from clipos.video.studio_graphics import export_graphic_pack

    for key, entry in graphic_catalog().items():
        path = tmp_path / (key + ".zip")
        export_graphic_pack(key, path)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read("pack.json"))
            assert manifest["id"] == key and manifest["design"] == entry
            assert entry["asset"] in archive.namelist()
            assert "CC0-1.0" in archive.read("LICENSE.txt").decode()
            if key.startswith("scene_"):
                assert (
                    entry["artwork"] in archive.namelist()
                    and entry["panel"] in archive.namelist()
                )
        before = path.read_bytes()
        with pytest.raises(FileExistsError):
            export_graphic_pack(key, path)
        assert path.read_bytes() == before
