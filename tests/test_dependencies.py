"""Tests for the dependency setup.

The build machine installs its dependencies through ``scripts/install_deps.py``
rather than ``pip install -r requirements.txt``.  That is not a stylistic
choice: ``scenedetect`` depends on ``opencv-python`` -- the *GUI* build --
which pip resolves as a separate distribution from ``opencv-python-headless``
even though the two overwrite each other's files.  The result is a broken
install on any headless machine:

    ImportError: libGL.so.1: cannot open shared object file

and, with OpenCV 5.x, a missing ``cv2.CascadeClassifier``, which CLIPOS uses
for face detection.  These tests pin that down so the problem cannot come
back unnoticed.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestOpenCVVersion(unittest.TestCase):
    """The installed OpenCV must have the API CLIPOS relies on."""

    def test_opencv_imports(self):
        import cv2  # noqa: F401

    def test_cascade_classifier_is_available(self):
        # OpenCV 5.x removed it; CLIPOS uses it for the Haar fallback.
        import cv2

        self.assertTrue(
            hasattr(cv2, "CascadeClassifier"),
            "cv2.CascadeClassifier is missing — OpenCV 5.x was installed",
        )

    def test_the_version_is_below_five(self):
        import cv2

        major = int(cv2.__version__.split(".")[0])
        self.assertLess(major, 5, "OpenCV 5 removed APIs CLIPOS uses")

    def test_opencv_does_not_need_a_display(self):
        """The GUI build cannot even be imported without libGL."""
        result = subprocess.run(
            [sys.executable, "-c",
             "import cv2; print(cv2.__version__)"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(
            result.returncode, 0,
            "importing cv2 failed — the GUI build of OpenCV is installed:\n"
            + result.stderr[-800:],
        )


class TestInstallScript(unittest.TestCase):
    """The install script must repair the OpenCV installation."""

    @classmethod
    def setUpClass(cls):
        cls.script = ROOT / "scripts" / "install_deps.py"
        cls.text = cls.script.read_text(encoding="utf-8")

    def test_the_script_exists(self):
        self.assertTrue(self.script.exists())

    def test_it_removes_the_gui_build_of_opencv(self):
        self.assertIn("FORBIDDEN", self.text)
        self.assertIn('"opencv-python"', self.text)

    def test_it_reinstalls_the_headless_build_last(self):
        # The reinstall has to come after the other packages, because those
        # are what drag the GUI build in.
        self.assertIn("HEADLESS_OPENCV", self.text)
        self.assertIn("--force-reinstall", self.text)
        self.assertIn("opencv-python-headless>=4.8,<5", self.text)

    def test_it_never_installs_pytorch(self):
        # PyTorch is several gigabytes and is only used to *detect* a GPU;
        # faster-whisper uses CTranslate2 and needs no PyTorch at all.
        self.assertNotIn("torch", self.text.replace("PyTorch", ""))

    def test_it_verifies_the_result(self):
        self.assertIn("CascadeClassifier", self.text)
        self.assertIn("=== verifying ===", self.text)

    def test_the_requirements_file_points_at_the_script(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("scripts/install_deps.py", requirements)

    def test_the_requirements_file_does_not_pull_in_torch(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        for line in requirements.splitlines():
            stripped = line.strip()
            if stripped.startswith("torch"):
                self.fail(
                    "torch must not be a dependency — it is a multi-gigabyte "
                    "download and CLIPOS does not need it"
                )


class TestWorkflows(unittest.TestCase):
    """The CI workflows must install the dependencies the safe way."""

    def setUp(self):
        self.workflows = list((ROOT / ".github" / "workflows").glob("*.yml"))

    def test_there_are_workflows(self):
        self.assertTrue(self.workflows)

    def test_every_workflow_uses_the_install_script(self):
        for workflow in self.workflows:
            text = workflow.read_text(encoding="utf-8")
            if "Install dependencies" not in text:
                continue
            self.assertIn(
                "scripts/install_deps.py", text,
                f"{workflow.name} installs the dependencies the wrong way",
            )

    def test_the_linux_job_has_a_display_for_qt(self):
        text = (ROOT / ".github" / "workflows" / "build-installers.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("build_gl_stubs.py", text)
        self.assertIn("QT_QPA_PLATFORM", text)
        self.assertIn("LD_LIBRARY_PATH", text)

    def test_the_workflows_do_not_queue_up_more_than_one_run(self):
        """Several runs at once starve the runner pool and the jobs that
        lose get cancelled -- which is exactly how the macOS build kept
        disappearing.  Every workflow therefore needs a concurrency group.
        """
        for workflow in self.workflows:
            text = workflow.read_text(encoding="utf-8")
            self.assertIn(
                "concurrency:", text,
                f"{workflow.name} has no concurrency group, so its runs pile up",
            )

    def test_the_release_workflow_keeps_a_finished_run_alive(self):
        """A release run must not be cancelled half way through: the tag
        is already published, so cancelling would leave a broken release.
        """
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("cancel-in-progress: false", text)

    def test_every_job_has_a_timeout(self):
        """Without a timeout a stuck job blocks the whole release."""
        for workflow in self.workflows:
            text = workflow.read_text(encoding="utf-8")
            for job in self._jobs(text):
                self.assertIn(
                    "timeout-minutes:", job,
                    f"{workflow.name} has a job without a timeout",
                )

    @staticmethod
    def _jobs(text):
        """Return the body of every job in a workflow.

        Only the blocks under the top level ``jobs:`` key are real jobs --
        ``on:`` has its own sub-blocks that are not jobs at all.
        """
        blocks = []
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.startswith("jobs:"):
                start = index + 1
                break
        if start is None:
            return blocks
        current = None
        for line in lines[start:]:
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
                if current is not None:
                    blocks.append("\n".join(current))
                current = [line]
                continue
            if current is not None:
                current.append(line)
        if current is not None:
            blocks.append("\n".join(current))
        return blocks


class TestPipelineDoesNotDownloadModels(unittest.TestCase):
    """The analysis must not reach out to the network for a model.

    The app's contract is that models come from the model manager, not from
    the analysis pipeline.  Downloading during a pipeline run would make an
    offline install look broken and would hang a build machine.
    """

    def test_the_pipeline_checks_the_model_is_installed(self):
        text = (ROOT / "clipos" / "video" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("model_installed", text)

    def test_the_pipeline_imports_the_check(self):
        text = (ROOT / "clipos" / "video" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("from ..ai.transcription import", text)
        self.assertIn("model_installed,", text)


if __name__ == "__main__":
    unittest.main()
