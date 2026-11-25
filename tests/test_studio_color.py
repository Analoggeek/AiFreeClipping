"""Actual checksum-bound .cube processing and selective grade export."""

from copy import deepcopy
from pathlib import Path
import pytest
from tests.test_multitrack import media
from tests.test_crop_config import decode
from clipos.video.multitrack import MultitrackProject
from clipos.video.studio_color import GRADE_DEFAULTS, read_cube, validate_grade
from clipos.video.multitrack_render import export_project
from clipos.video.editing_preset import EditingPreset, apply_editing_preset
from clipos.video.live_playback import stream_frames


def cube(tmp_path):
    path = tmp_path / "swap.cube"
    rows = ["LUT_3D_SIZE 2", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    for blue in (0, 1):
        for green in (0, 1):
            for red in (0, 1):
                rows.append(f"{blue} {green} {red}")
    path.write_text("\n".join(rows) + "\n")
    return path


def test_cube_strength_actual_pixels_stream_and_changed_asset_rejection(
    media, tmp_path
):
    asset = read_cube(cube(tmp_path))
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])
    grade = deepcopy(GRADE_DEFAULTS)
    grade.update(lut_path=asset["path"], lut_sha256=asset["sha256"])
    apply_editing_preset(
        p, EditingPreset("LUT", {"color_grade": {"color_grade": grade}}), {mid}
    )
    output = tmp_path / "lut.mp4"
    export_project(p, output, tmp_path / "work", encoder="cpu")
    pixel = decode(output)[5, 5]
    assert pixel[0] > pixel[2] + 100  # BGR: red input becomes blue
    stream = stream_frames(p, max_size=160)
    try:
        data = next(payload for kind, _, payload in stream if kind == "video")
    finally:
        stream.close()
    assert data[5, 5, 2] > data[5, 5, 0] + 100  # RGB stream is blue too
    grade["lut_strength"] = 0
    apply_editing_preset(
        p, EditingPreset("Neutral LUT", {"color_grade": {"color_grade": grade}}), {mid}
    )
    neutral = tmp_path / "neutral.mp4"
    export_project(p, neutral, tmp_path / "work", encoder="cpu")
    pixel = decode(neutral)[5, 5]
    assert pixel[2] > pixel[0] + 100
    Path(asset["path"]).write_text("changed bytes")
    with pytest.raises(ValueError):
        export_project(p, tmp_path / "invalid.mp4", tmp_path / "work", encoder="cpu")
    assert not (tmp_path / "invalid.mp4").exists()


def test_exposure_balance_and_grade_roundtrip(media, tmp_path):
    p = MultitrackProject(width=160, height=90, fps=10)
    mid = p.import_media(media[0])
    before = p.to_dict()
    grade = deepcopy(GRADE_DEFAULTS)
    grade.update(exposure=-1, gamma=1.1, rs=0.05, rh=-0.1)
    apply_editing_preset(
        p, EditingPreset("Grade", {"color_grade": {"color_grade": grade}}), {mid}
    )
    output = tmp_path / "graded.mp4"
    export_project(p, output, tmp_path / "work", encoder="cpu")
    assert decode(output)[5, 5, 2] < decode(media[0])[5, 5, 2] - 30
    saved = tmp_path / "assembly.json"
    p.save(saved)
    assert MultitrackProject.load(saved).to_dict() == p.to_dict()
    assert p.undo() and p.to_dict() == before
    with pytest.raises(ValueError):
        validate_grade({"gamma": float("nan")})
    bad = tmp_path / "bad.cube"
    bad.write_text("LUT_3D_SIZE 2\n0 0 0\n")
    with pytest.raises(ValueError):
        read_cube(bad)
