"""Regression tests for the defects found while walking through the GUI.

Each test here corresponds to a bug that was visible in the running
application:

* a video shorter than the shortest requested clip produced no clips at all;
* the "Detected Moments" rows were squeezed and the text was clipped;
* the dashboard's count-up animation never stopped and showed the wrong
  intermediate values;
* the My Projects page called a method that does not exist.
"""
from __future__ import annotations

import ctypes
import glob
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The Qt widgets need libGL, which bare containers do not have.  LD_LIBRARY_PATH
# is read by the loader when the process starts, so the generated stubs are
# loaded explicitly instead.
_STUBS = ROOT / ".stublibs"
if _STUBS.is_dir():
    for _stub in sorted(glob.glob(str(_STUBS / "*.so*"))):
        try:
            ctypes.CDLL(_stub, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from clipos.ai.audio_analysis import AudioAnalysis  # noqa: E402
from clipos.ai.clip_detector import _candidate_windows  # noqa: E402
from clipos.ai.transcription import Transcript  # noqa: E402
from clipos.ai.visual_analysis import VisualAnalysis  # noqa: E402


class TestShortSourcesStillProduceClips(unittest.TestCase):
    """A source shorter than the requested minimum used to yield nothing."""

    def _windows(self, duration, band):
        return _candidate_windows(
            duration, band[0], band[1],
            Transcript(), VisualAnalysis(), AudioAnalysis(),
        )

    def test_short_source_yields_one_window(self):
        windows = self._windows(12.0, (30.0, 45.0))
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0], (0.0, 12.0))

    def test_window_covers_the_whole_short_source(self):
        windows = self._windows(8.0, (30.0, 45.0))
        self.assertEqual(windows[0][0], 0.0)
        self.assertAlmostEqual(windows[0][1], 8.0)

    def test_very_short_source_still_yields_a_window(self):
        windows = self._windows(2.0, (30.0, 45.0))
        self.assertEqual(len(windows), 1)

    def test_normal_source_yields_several_windows(self):
        windows = self._windows(45.0, (30.0, 45.0))
        self.assertGreater(len(windows), 1)

    def test_fallback_anchor_step_is_never_zero(self):
        # int(max_dur) could be 0, which made range() empty.
        windows = self._windows(40.0, (5.0, 6.0))
        self.assertTrue(windows)

    def test_no_window_is_longer_than_the_source(self):
        for duration in (3.0, 12.0, 45.0, 120.0):
            for band in ((15.0, 30.0), (30.0, 45.0), (60.0, 90.0)):
                for start, end in self._windows(duration, band):
                    self.assertLessEqual(end, duration + 0.01)
                    self.assertGreaterEqual(start, 0.0)
                    self.assertGreater(end, start)


class TestVideoThumbnailApi(unittest.TestCase):
    """The widget's method is set_video, not setVideo."""

    def test_set_video_exists(self):
        from clipos.ui.widgets.common import VideoThumbnail
        self.assertTrue(hasattr(VideoThumbnail, "set_video"))

    def test_setVideo_does_not_exist(self):
        # If this ever becomes true the My Projects page must be updated
        # rather than the widget silently growing a second spelling.
        from clipos.ui.widgets.common import VideoThumbnail
        self.assertFalse(hasattr(VideoThumbnail, "setVideo"))



class TestStatTileAnimation(unittest.TestCase):
    """The count-up must reach the target and then stop."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_set_value_without_animation_shows_the_value(self):
        from clipos.ui.widgets.common import StatTile
        tile = StatTile(value="0")
        tile.set_value("42", animate=False)
        self.assertEqual(tile._value_label.text(), "42")

    def test_non_numeric_value_is_shown_verbatim(self):
        from clipos.ui.widgets.common import StatTile
        tile = StatTile(value="0")
        tile.set_value("4.0 MB")
        self.assertEqual(tile._value_label.text(), "4.0 MB")

    def test_a_new_value_stops_the_previous_timer(self):
        from clipos.ui.widgets.common import StatTile
        tile = StatTile(value="0")
        tile.set_value("10")
        first = tile._timer
        tile.set_value("20")
        self.assertIsNot(tile._timer, first)
        self.assertFalse(first.isActive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
