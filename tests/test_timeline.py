"""Unit tests for the timeline model and for :meth:`ClipRenderer.render_timeline`.

The timeline model is deliberately Qt-free, so these tests run headless.  The
render test drives real FFmpeg against a real generated fixture and verifies
the produced file, not just the model.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipos.video.timeline import Segment, Timeline  # noqa: E402

FFMPEG = Path(__file__).resolve().parents[1] / "resources" / "ffmpeg"


def _ffmpeg_bin() -> Path:
    """Locate the vendored FFmpeg the same way the application does."""
    from clipos.core.ffmpeg import require_ffmpeg
    try:
        return Path(require_ffmpeg())
    except Exception:
        for folder in sorted(FFMPEG.glob("*")):
            for name in ("ffmpeg", "ffmpeg.exe"):
                candidate = folder / name
                if candidate.exists():
                    return candidate
        raise unittest.SkipTest("vendored ffmpeg is not present")


def make_fixture(path: Path, seconds: int = 6) -> Path:
    """Generate a genuine H.264/AAC clip with a visible moving element."""
    if path.exists():
        return path
    bin_ = _ffmpeg_bin()
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(bin_), "-y",
        "-f", "lavfi", "-i",
        f"testsrc=size=640x360:rate=25:duration={seconds}",
        "-f", "lavfi", "-i",
        f"sine=frequency=330:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


# --------------------------------------------------------------------- model


class TestSegment(unittest.TestCase):
    def test_source_duration(self):
        seg = Segment(id="a", start=2.0, end=7.5)
        self.assertAlmostEqual(seg.source_duration, 5.5)

    def test_duration_scales_with_speed(self):
        seg = Segment(id="a", start=0.0, end=10.0, speed=2.0)
        self.assertAlmostEqual(seg.duration, 5.0)

    def test_duration_never_divides_by_zero(self):
        seg = Segment(id="a", start=0.0, end=10.0, speed=0.0)
        self.assertGreater(seg.duration, 0.0)

    def test_mid(self):
        self.assertAlmostEqual(Segment(id="a", start=2.0, end=6.0).mid, 4.0)

    def test_round_trip_dict(self):
        seg = Segment(id="a", start=1.0, end=2.0, speed=1.5, zoom=1.2,
                      crop_x=0.25, crop_y=0.75, muted=True)
        again = Segment.from_dict(seg.to_dict())
        self.assertEqual(seg.to_dict(), again.to_dict())

    def test_from_dict_applies_defaults(self):
        seg = Segment.from_dict({"id": "a", "start": 0.0, "end": 1.0})
        self.assertEqual(seg.speed, 1.0)
        self.assertEqual(seg.zoom, 1.0)
        self.assertFalse(seg.muted)


class TestTimelineOperations(unittest.TestCase):
    def setUp(self):
        self.tl = Timeline.from_clip(0.0, 20.0, source_duration=20.0)

    def test_from_clip_creates_one_segment(self):
        self.assertEqual(len(self.tl.segments), 1)
        self.assertAlmostEqual(self.tl.duration, 20.0)

    def test_split_at_creates_two_segments(self):
        self.assertTrue(self.tl.split_at(8.0))
        self.assertEqual(len(self.tl.segments), 2)
        self.assertAlmostEqual(self.tl.segments[0].end, 8.0)
        self.assertAlmostEqual(self.tl.segments[1].start, 8.0)

    def test_split_outside_a_segment_does_nothing(self):
        self.assertFalse(self.tl.split_at(99.0))
        self.assertEqual(len(self.tl.segments), 1)

    def test_split_on_the_boundary_does_nothing(self):
        self.assertFalse(self.tl.split_at(0.0))
        self.assertEqual(len(self.tl.segments), 1)

    def test_trim_changes_the_segment_bounds(self):
        seg_id = self.tl.segments[0].id
        self.assertTrue(self.tl.trim(seg_id, new_start=5.0, new_end=15.0))
        self.assertAlmostEqual(self.tl.segments[0].start, 5.0)
        self.assertAlmostEqual(self.tl.segments[0].end, 15.0)
        self.assertAlmostEqual(self.tl.duration, 10.0)

    def test_trim_cannot_invert_a_segment(self):
        seg_id = self.tl.segments[0].id
        self.assertFalse(self.tl.trim(seg_id, new_start=10.0, new_end=5.0))
        self.assertAlmostEqual(self.tl.segments[0].start, 0.0)

    def test_delete_segment(self):
        self.tl.split_at(10.0)
        before = len(self.tl.segments)
        self.assertTrue(self.tl.delete_segment(self.tl.segments[0].id))
        self.assertEqual(len(self.tl.segments), before - 1)

    def test_delete_missing_segment_returns_false(self):
        self.assertFalse(self.tl.delete_segment("nope"))

    def test_merge_with_next_joins_two_segments(self):
        self.tl.split_at(10.0)
        self.assertTrue(self.tl.merge_with_next(0))
        self.assertEqual(len(self.tl.segments), 1)
        self.assertAlmostEqual(self.tl.segments[0].start, 0.0)
        self.assertAlmostEqual(self.tl.segments[0].end, 20.0)

    def test_merge_with_next_on_the_last_segment_fails(self):
        self.assertFalse(self.tl.merge_with_next(0))

    def test_move_segment_reorders(self):
        self.tl.split_at(10.0)
        first_id = self.tl.segments[0].id
        self.assertTrue(self.tl.move_segment(0, 1))
        self.assertEqual(self.tl.segments[1].id, first_id)

    def test_move_segment_out_of_range_fails(self):
        self.assertFalse(self.tl.move_segment(0, 5))
        self.assertFalse(self.tl.move_segment(0, -1))

    def test_set_speed_changes_the_timeline_duration(self):
        seg_id = self.tl.segments[0].id
        self.assertTrue(self.tl.set_speed(seg_id, 2.0))
        self.assertAlmostEqual(self.tl.duration, 10.0)

    def test_set_speed_clamps_to_the_supported_range(self):
        seg_id = self.tl.segments[0].id
        # Out-of-range values are clamped rather than rejected so the
        # editor can never end up with an unplayable rate.
        self.assertTrue(self.tl.set_speed(seg_id, 0.0))
        self.assertAlmostEqual(self.tl.segments[0].speed, 0.25)
        self.assertTrue(self.tl.set_speed(seg_id, 99.0))
        self.assertAlmostEqual(self.tl.segments[0].speed, 4.0)

    def test_set_zoom_and_crop(self):
        seg_id = self.tl.segments[0].id
        self.assertTrue(self.tl.set_zoom(seg_id, 1.5))
        self.assertAlmostEqual(self.tl.segments[0].zoom, 1.5)
        self.assertTrue(self.tl.set_crop(seg_id, 0.25, 0.75))
        self.assertAlmostEqual(self.tl.segments[0].crop_x, 0.25)
        self.assertAlmostEqual(self.tl.segments[0].crop_y, 0.75)

    def test_set_muted(self):
        seg_id = self.tl.segments[0].id
        self.assertTrue(self.tl.set_muted(seg_id, True))
        self.assertTrue(self.tl.segments[0].muted)

    def test_set_all_speed(self):
        self.tl.split_at(10.0)
        self.tl.set_all_speed(2.0)
        self.assertTrue(all(s.speed == 2.0 for s in self.tl.segments))
        self.assertAlmostEqual(self.tl.duration, 10.0)


class TestTimelineUndoRedo(unittest.TestCase):
    def setUp(self):
        self.tl = Timeline.from_clip(0.0, 20.0, source_duration=20.0)

    def test_undo_and_redo_a_split(self):
        self.tl.split_at(10.0)
        self.assertEqual(len(self.tl.segments), 2)
        label = self.tl.undo()
        self.assertIsNotNone(label)
        self.assertIn("split", label.lower())
        self.assertEqual(len(self.tl.segments), 1)
        self.assertIsNotNone(self.tl.redo())
        self.assertEqual(len(self.tl.segments), 2)

    def test_undo_returns_none_with_no_history(self):
        self.assertIsNone(self.tl.undo())

    def test_redo_returns_none_with_no_redo_stack(self):
        self.assertIsNone(self.tl.redo())

    def test_can_undo_and_can_redo_flags(self):
        self.assertFalse(self.tl.can_undo())
        self.assertFalse(self.tl.can_redo())
        self.tl.split_at(10.0)
        self.assertTrue(self.tl.can_undo())
        self.tl.undo()
        self.assertTrue(self.tl.can_redo())

    def test_undo_restores_the_previous_speed(self):
        seg_id = self.tl.segments[0].id
        self.tl.set_speed(seg_id, 2.0)
        self.tl.undo()
        self.assertAlmostEqual(self.tl.segments[0].speed, 1.0)

    def test_history_labels(self):
        self.tl.split_at(10.0)
        self.tl.set_speed(self.tl.segments[0].id, 1.5)
        labels = self.tl.history_labels()
        self.assertEqual(len(labels), 2)


class TestTimelinePersistence(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        tl = Timeline.from_clip(0.0, 20.0, source_duration=20.0)
        tl.split_at(10.0)
        tl.set_speed(tl.segments[0].id, 1.5)
        path = Path("/tmp/clipos_test_timeline.json")
        tl.save(path)
        again = Timeline.load(path)
        self.assertEqual(len(again.segments), 2)
        self.assertAlmostEqual(again.segments[0].speed, 1.5)
        self.assertAlmostEqual(again.duration, tl.duration)

    def test_saved_file_is_valid_json(self):
        tl = Timeline.from_clip(0.0, 5.0)
        path = Path("/tmp/clipos_test_timeline.json")
        tl.save(path)
        data = json.loads(path.read_text())
        self.assertIn("segments", data)

    def test_saved_file_records_the_source_duration(self):
        tl = Timeline.from_clip(0.0, 12.0, source_duration=12.0)
        path = Path("/tmp/clipos_test_timeline.json")
        tl.save(path)
        data = json.loads(path.read_text())
        self.assertAlmostEqual(data["source_duration"], 12.0)
        self.assertEqual(len(data["segments"]), 1)

    def test_loaded_timeline_keeps_the_source_duration(self):
        tl = Timeline.from_clip(0.0, 12.0, source_duration=12.0)
        path = Path("/tmp/clipos_test_timeline.json")
        tl.save(path)
        again = Timeline.load(path)
        self.assertAlmostEqual(again.source_duration, 12.0)


class TestTimelineTimeMapping(unittest.TestCase):
    def setUp(self):
        self.tl = Timeline.from_clip(10.0, 30.0, source_duration=30.0)

    def test_source_time_at_the_start(self):
        self.assertAlmostEqual(self.tl.source_time_at(0.0), 10.0)

    def test_source_time_at_the_end(self):
        self.assertAlmostEqual(self.tl.source_time_at(20.0), 30.0)

    def test_segment_at_returns_the_right_segment(self):
        seg = self.tl.segment_at(5.0)
        self.assertIsNotNone(seg)
        self.assertAlmostEqual(seg.start, 10.0)

    def test_output_time_at_maps_back_to_the_source(self):
        self.assertAlmostEqual(self.tl.output_time_at(15.0), 5.0)

    def test_segment_at_past_the_end_clamps_to_the_last_segment(self):
        # The editor scrubs against the segment list, so a time beyond the
        # end resolves to the final segment rather than to nothing.
        seg = self.tl.segment_at(999.0)
        self.assertIsNotNone(seg)
        self.assertEqual(seg.id, self.tl.segments[-1].id)


# ------------------------------------------------------------------- render


class TestRenderTimeline(unittest.TestCase):
    """Drives the real renderer and verifies the real output file."""

    @classmethod
    def setUpClass(cls):
        cls.src = make_fixture(Path("/tmp/clipos_tl_test/source.mp4"))
        from clipos.core.ffmpeg import require_ffprobe
        try:
            cls.probe = Path(require_ffprobe())
        except Exception:
            cls.probe = _ffmpeg_bin().parent / "ffprobe"

    def _probe_json(self, path: Path) -> dict:
        out = subprocess.run(
            [str(self.probe), "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", str(path)],
            check=True, capture_output=True, text=True,
        )
        return json.loads(out.stdout)

    def _render(self, timeline: Timeline, out: Path, settings):
        from clipos.video.renderer import ClipRenderer
        renderer = ClipRenderer(Path("/tmp/clipos_tl_test/work"))
        return renderer.render_timeline(self.src, out, timeline, settings)

    def _settings(self, **kw):
        from clipos.video.renderer import RenderSettings
        base = dict(aspect="9:16", width=1080, height=1920, fps=30,
                    codec="h264", bitrate_kbps=4000, crf=23,
                    smart_reframe=False, auto_zoom=False,
                    remove_silence=False, show_captions=False)
        base.update(kw)
        return RenderSettings(**base)

    def test_render_timeline_produces_a_real_vertical_file(self):
        tl = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        out = Path("/tmp/clipos_tl_test/out_basic.mp4")
        result = self._render(tl, out, self._settings())
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 1000)
        self.assertEqual(result.width, 1080)
        self.assertEqual(result.height, 1920)

    def test_rendered_file_has_a_video_and_an_audio_stream(self):
        tl = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        out = Path("/tmp/clipos_tl_test/out_streams.mp4")
        self._render(tl, out, self._settings())
        info = self._probe_json(out)
        kinds = {s["codec_type"] for s in info["streams"]}
        self.assertIn("video", kinds)
        self.assertIn("audio", kinds)

    def test_rendered_video_is_really_1080x1920(self):
        tl = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        out = Path("/tmp/clipos_tl_test/out_size.mp4")
        self._render(tl, out, self._settings())
        info = self._probe_json(out)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.assertEqual(int(video["width"]), 1080)
        self.assertEqual(int(video["height"]), 1920)

    def test_split_segments_shorten_the_output(self):
        whole = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        out_whole = Path("/tmp/clipos_tl_test/out_whole.mp4")
        self._render(whole, out_whole, self._settings())

        trimmed = Timeline.from_clip(0.0, 2.0, source_duration=6.0)
        out_short = Path("/tmp/clipos_tl_test/out_short.mp4")
        self._render(trimmed, out_short, self._settings())

        def duration(p: Path) -> float:
            info = self._probe_json(p)
            return float(info["format"]["duration"])

        self.assertLess(duration(out_short), duration(out_whole))

    def test_two_split_segments_produce_a_longer_file_than_one(self):
        one = Timeline.from_clip(0.0, 2.0, source_duration=6.0)
        out_one = Path("/tmp/clipos_tl_test/out_one.mp4")
        self._render(one, out_one, self._settings())

        two = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        two.split_at(2.0)
        out_two = Path("/tmp/clipos_tl_test/out_two.mp4")
        self._render(two, out_two, self._settings())

        def duration(p: Path) -> float:
            return float(self._probe_json(p)["format"]["duration"])

        self.assertGreater(duration(out_two), duration(out_one))

    def test_speed_change_retimes_the_output(self):
        normal = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        out_normal = Path("/tmp/clipos_tl_test/out_n.mp4")
        self._render(normal, out_normal, self._settings())

        fast = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        fast.set_speed(fast.segments[0].id, 2.0)
        out_fast = Path("/tmp/clipos_tl_test/out_f.mp4")
        self._render(fast, out_fast, self._settings())

        def duration(p: Path) -> float:
            return float(self._probe_json(p)["format"]["duration"])

        self.assertAlmostEqual(duration(out_fast), duration(out_normal) / 2.0,
                               delta=0.6)

    def test_zoom_and_crop_still_render(self):
        tl = Timeline.from_clip(0.0, 3.0, source_duration=6.0)
        tl.set_zoom(tl.segments[0].id, 1.4)
        tl.set_crop(tl.segments[0].id, 0.3, 0.7)
        out = Path("/tmp/clipos_tl_test/out_zoom.mp4")
        result = self._render(tl, out, self._settings())
        self.assertTrue(out.exists())
        self.assertEqual((result.width, result.height), (1080, 1920))

    def test_muted_segment_still_produces_a_playable_file(self):
        tl = Timeline.from_clip(0.0, 3.0, source_duration=6.0)
        tl.set_muted(tl.segments[0].id, True)
        out = Path("/tmp/clipos_tl_test/out_muted.mp4")
        self._render(tl, out, self._settings())
        self.assertTrue(out.exists())
        info = self._probe_json(out)
        self.assertIn("video", {s["codec_type"] for s in info["streams"]})

    def test_render_reports_no_warnings_for_a_clean_timeline(self):
        tl = Timeline.from_clip(0.0, 3.0, source_duration=6.0)
        out = Path("/tmp/clipos_tl_test/out_clean.mp4")
        result = self._render(tl, out, self._settings())
        self.assertEqual(result.warnings, [])

    def test_cancellation_stops_the_render(self):
        tl = Timeline.from_clip(0.0, 4.0, source_duration=6.0)
        out = Path("/tmp/clipos_tl_test/out_cancel.mp4")
        from clipos.video.renderer import ClipRenderer
        renderer = ClipRenderer(Path("/tmp/clipos_tl_test/work"))
        result = renderer.render_timeline(
            self.src, out, tl, self._settings(),
            cancel_cb=lambda: True,
        )
        self.assertTrue(result.cancelled)


if __name__ == "__main__":
    unittest.main(verbosity=2)
