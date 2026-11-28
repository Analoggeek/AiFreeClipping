"""Regression coverage for cut-aware, subject-following portrait crops."""
from __future__ import annotations

import random
import subprocess

import pytest

from app.config import ffmpeg_binary
from app.services import render, scoring, vision


def _at(path: list[list[float]], t: float) -> float:
    if t <= path[0][0]:
        return path[0][1]
    if t >= path[-1][0]:
        return path[-1][1]
    for (t0, x0), (t1, x1) in zip(path, path[1:]):
        if t0 <= t <= t1:
            return x0 + (x1 - x0) * (t - t0) / (t1 - t0)
    return path[-1][1]


def test_long_sources_spread_the_analysis_budget_over_the_whole_video():
    # 30,000 frames at 30 fps is about 17 minutes. A 900-sample cap should
    # lower the sample rate rather than accidentally stopping after frame 900.
    assert vision._sampling_step(30, 2, 30_000, 900) == 34
    assert vision._sampling_step(30, 2, 900, 900) == 15


def test_follow_path_holds_noise_and_snaps_to_a_new_shot():
    observations = [
        {"t": 0.0, "width": 1920, "height": 1080,
         "tracks": [{"id": 1, "x": 0.30, "prominence": 0.08}]},
        {"t": 0.5, "width": 1920, "height": 1080,
         "tracks": [{"id": 1, "x": 0.32, "prominence": 0.08}]},
        {"t": 1.0, "width": 1920, "height": 1080,
         "tracks": [{"id": 1, "x": 0.31, "prominence": 0.08}]},
        {"t": 1.5, "width": 1920, "height": 1080,
         "tracks": [{"id": 1, "x": 0.72, "prominence": 0.08}]},
    ]
    path = vision._follow_crop_path(observations, [1.2])
    assert _at(path, 0.5) == pytest.approx(0.30)
    assert _at(path, 1.1998) == pytest.approx(0.30, abs=0.001)
    assert _at(path, 1.2) == pytest.approx(0.72)
    assert path[-1][1] == pytest.approx(0.72)


def test_follow_path_clamps_to_the_crop_and_needs_a_real_subject():
    empty = [{"t": 0, "width": 1920, "height": 1080, "tracks": []}]
    assert vision._follow_crop_path(empty, []) == []
    portrait = [{"t": 0, "width": 540, "height": 960,
                 "tracks": [{"id": 1, "x": 0.9, "prominence": 0.1}]}]
    assert vision._follow_crop_path(portrait, []) == []

    wide = [{"t": 0, "width": 1920, "height": 1080,
             "tracks": [{"id": 1, "x": 1.2, "prominence": 0.1}]}]
    path = vision._follow_crop_path(wide, [])
    crop_fraction = 1080 * (9 / 16) / 1920
    assert path[0][1] == pytest.approx(1 - crop_fraction / 2)


def test_vision_analysis_resets_tracking_at_shot_cuts_and_returns_the_path(monkeypatch, tmp_path):
    class Frame:
        shape = (1080, 1920, 3)

        def __init__(self, center: float):
            self.center = center

    frames = [
        (t, None, 0.1, Frame(center))
        for t, center in ((0.0, 0.25), (0.5, 0.25), (1.0, 0.75), (1.5, 0.75))
    ]
    monkeypatch.setattr(vision, "_frame_sampler", lambda *_args: iter(frames))
    monkeypatch.setattr(vision, "_scene_cuts", lambda *_args: [(0.75, 0.8)])
    monkeypatch.setattr(vision, "_detector", lambda *_args: lambda frame: (
        ([frame.center * 1920 - 80, 200, frame.center * 1920 + 80, 800], 0.9),
    ))
    monkeypatch.setattr(vision, "_weights_dir", lambda: tmp_path)

    result = vision._analyze_one("source.mp4", None, 2, "auto", None, track_reframe=True)
    assert result["reframe_version"] == vision.REFRAME_VERSION
    assert result["track_count"] == 2
    before_cut = _at(result["crop_path"], 0.5)
    assert _at(result["crop_path"], 0.7498) == pytest.approx(before_cut, abs=0.001)
    # A provisional detection on the first post-cut sample lets the crop snap
    # to the new subject at the cut, without waiting for ByteTrack confirmation.
    assert _at(result["crop_path"], 0.75) == pytest.approx(0.75)
    assert result["crop_path"][-1][1] > 0.5


def test_candidate_window_keeps_path_boundaries_and_scene_snap_keys():
    path = [[0.0, 0.25], [1.9999, 0.25], [2.0, 0.75], [4.0, 0.75]]
    clipped = scoring._crop_path_window({"crop_path": path}, 1.0, 3.0)
    assert clipped[0] == [1.0, 0.25]
    assert clipped[1:3] == [[1.9999, 0.25], [2.0, 0.75]]
    assert clipped[-1] == [3.0, 0.75]


def test_proposals_keep_smart_crop_paths_only_for_full_frame_portrait_clips():
    media = [{"id": "m1", "duration": 30, "title": "Source"}]
    transcript = {"m1": {"segments": [{
        "start": 0, "end": 30, "text": "An exciting moment unfolds.",
        "words": [{"start": t, "end": t + 0.2, "word": "wow", "probability": 0.9}
                  for t in range(0, 30, 2)],
    }]}}
    vision_data = {"m1": {
        "timeline": [{"t": t, "activity": 0.8} for t in range(30)],
        "crop_path": [[0.0, 0.3], [30.0, 0.7]],
    }}
    portrait = scoring.propose(
        media, transcript, vision_data, count=1, min_duration=5, max_duration=5,
        platform="shorts",
    )
    assert portrait and len(portrait[0].crop_path) >= 2
    assert "portrait framing follows a tracked subject" in portrait[0].reasons
    assert portrait[0].crop_path[0][0] == pytest.approx(portrait[0].start)
    assert portrait[0].crop_path[-1][0] == pytest.approx(portrait[0].end)

    landscape = scoring.propose(
        media, transcript, vision_data, count=1, min_duration=5, max_duration=5,
        platform="landscape",
    )
    custom = scoring.propose(
        media, transcript, vision_data, count=1, min_duration=5, max_duration=5,
        platform="shorts", regions={"m1": [{"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}]},
    )
    assert landscape and landscape[0].crop_path == []
    assert custom and custom[0].crop_path == []


def test_render_builds_a_frame_evaluated_crop_only_for_full_frame_portrait():
    path = [[10.0, 0.25], [11.0, 0.75]]
    moving = render._moving_crop_filter(path, "9:16", 1920, 1080)
    assert moving is not None
    assert moving.startswith("crop=w=ih*0.5625000000:h=ih:x='")
    assert "if(lt(t,11.000000)" in moving

    assert render._moving_crop_filter(path, "16:9", 1920, 1080) is None
    assert render._moving_crop_filter(path, "9:16", 360, 640) is None
    assert render._moving_crop_filter([], "9:16", 1920, 1080) is None

    options = {
        "aspect": "9:16", "resolution": "720p", "source_width": 1920,
        "source_height": 1080, "crop_path": path, "blur_background": True, "sfx": [],
    }
    args = render.build_clip_args("source.mp4", 10, 12, "out.mp4", options, has_audio=False)
    graph = args[args.index("-filter_complex") + 1]
    assert "trim=start=10.000:end=12.000," + moving in graph
    assert "split=2[bg][fg]" not in graph

    options["region"] = {"x": 0.1, "y": 0.1, "w": 0.6, "h": 0.8}
    regional = render.build_clip_args("source.mp4", 10, 12, "out.mp4", options, has_audio=False)
    regional_graph = regional[regional.index("-filter_complex") + 1]
    assert "if(lt(t,11.000000)" not in regional_graph


def test_long_crop_paths_are_reduced_to_a_ffmpeg_safe_expression():
    rng = random.Random(22)
    path = [[index * 0.5, rng.uniform(0.2, 0.8)] for index in range(121)]
    moving = render._moving_crop_filter(path, "9:16", 1920, 1080)
    assert moving is not None and len(moving) < 5000
    result = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i",
         "testsrc2=size=640x360:rate=5", "-t", "0.2", "-vf", moving, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-800:]


def test_dense_shot_snaps_are_sampled_across_the_crop_expression_budget():
    path: list[list[float]] = []
    for index in range(40):
        time_value = float(index)
        old_center = 0.25 if index % 2 == 0 else 0.75
        path.extend([[time_value, old_center], [time_value + 0.0001, 1 - old_center]])
    compact = render._simplify_crop_points(path)
    snaps = sum(
        t1 - t0 <= 0.002 and abs(x1 - x0) >= 0.03
        for (t0, x0), (t1, x1) in zip(compact, compact[1:])
    )
    assert len(compact) <= 64
    assert snaps >= 30
    moving = render._moving_crop_filter(path, "9:16", 1920, 1080)
    assert moving is not None
    result = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i",
         "testsrc2=size=640x360:rate=5", "-t", "0.2", "-vf", moving, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-800:]


def test_ffmpeg_output_follows_a_cut_aware_crop_path(tmp_path):
    ffmpeg = ffmpeg_binary()
    source = tmp_path / "red-left-blue-right.mp4"
    output = tmp_path / "reframed.mp4"
    generated = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=640x360:r=10:d=2",
            "-vf", "drawbox=x=320:y=0:w=320:h=360:color=blue:t=fill",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
        ], capture_output=True, text=True,
    )
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg test source could not be encoded: {generated.stderr[-250:]}")

    options = {
        "aspect": "9:16", "resolution": "source", "source_width": 640,
        "source_height": 360,
        "crop_path": [[0.0, 0.30], [1.0, 0.30], [1.0001, 0.70], [2.0, 0.70]],
        "blur_background": True, "sfx": [],
    }
    encoded = subprocess.run(
        render.build_clip_args(str(source), 0, 2, str(output), options, has_audio=False),
        capture_output=True, text=True,
    )
    assert encoded.returncode == 0, encoded.stderr[-1200:]

    def mean_rgb(at: float) -> tuple[float, float, float]:
        frame = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(at), "-i", str(output),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True,
        )
        assert frame.returncode == 0 and frame.stdout
        pixels = frame.stdout
        count = len(pixels) // 3
        return tuple(sum(pixels[channel::3]) / count for channel in range(3))

    first = mean_rgb(0.2)
    last = mean_rgb(1.8)
    assert first[0] > first[2] + 40
    assert last[2] > last[0] + 40
