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

import yaml

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

    def test_the_build_workflow_keeps_a_finished_run_alive(self):
        """A build takes half an hour.  Cancelling the one that is already
        running to start a newer one throws all of that away.
        """
        text = (ROOT / ".github" / "workflows" / "build-installers.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("cancel-in-progress: false", text)

    def test_the_runner_context_is_not_used_at_the_job_level(self):
        """The ``runner`` context only exists once a job has a machine.

        Using it in a job level ``env`` makes GitHub reject the whole
        workflow file, and the run fails before a single job starts --
        which looks exactly like a build failure and is very hard to see.
        """
        for workflow in self.workflows:
            text = workflow.read_text(encoding="utf-8")
            for job in self._jobs(text):
                # The job header is everything before the first step.
                header = job.split("- ", 1)[0]
                self.assertNotIn(
                    "runner.", header,
                    f"{workflow.name} uses the runner context in a job header",
                )

    def test_every_job_has_a_timeout(self):
        """Without a timeout a stuck job blocks the whole release."""
        for workflow in self.workflows:
            text = workflow.read_text(encoding="utf-8")
            for job in self._jobs(text):
                self.assertIn(
                    "timeout-minutes:", job,
                    f"{workflow.name} has a job without a timeout",
                )

    def test_a_step_with_shell_syntax_runs_under_bash(self):
        """A step that uses shell syntax has to say which shell it uses.

        A step without ``shell: bash`` runs under PowerShell on the
        Windows runner, where ``mkdir -p``, ``$RUNNER_OS`` and
        ``${PIPESTATUS[0]}`` mean nothing.  The step then fails at the
        first line, before it does any work, and the reason is buried
        in a shell error that says nothing about the build.
        """
        markers = ("$RUNNER_OS", "${PIPESTATUS", "$GITHUB_STEP_SUMMARY",
                   "LD_LIBRARY_PATH=", "mkdir -p")
        for workflow in self.workflows:
            data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
            for job_name, job in (data.get("jobs") or {}).items():
                for step in job.get("steps") or []:
                    run = step.get("run")
                    if not isinstance(run, str):
                        continue
                    if not any(marker in run for marker in markers):
                        continue
                    self.assertEqual(
                        step.get("shell"), "bash",
                        f"{workflow.name} / {job_name} / "
                        f"{step.get('name')} uses shell syntax but does not "
                        f"ask for bash",
                    )

    def test_the_macos_jobs_use_a_runner_that_is_actually_handed_out(self):
        """The macOS runner image has to be one the pool gives away.

        A job on a runner image the pool does not hand out is cancelled
        before a machine is assigned -- it starts and finishes within a
        second, with no steps at all, and there is nothing in the log to
        explain it.  macos-14 behaved that way here; macos-15 ran
        straight away.
        """
        for workflow in self.workflows:
            text = workflow.read_text(encoding="utf-8")
            for job in self._jobs(text):
                for line in job.splitlines():
                    stripped = line.strip()
                    if not stripped.startswith("runs-on:"):
                        continue
                    image = stripped.split(":", 1)[1].strip()
                    if "macos" not in image:
                        continue
                    self.assertNotEqual(
                        image, "macos-14",
                        f"{workflow.name} builds macOS on a runner image "
                        f"that is never assigned",
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


class TestRepositoryIsSane(unittest.TestCase):
    """The repository must not carry anything that breaks a checkout.

    A file whose name contains backslashes -- a Windows path that was
    used as a file name -- is one file on Linux and a directory on
    Windows.  Git checks it out as a directory on the Windows runner,
    and the checkout silently ends up wrong: the scripts are not there,
    the build stops with "No such file or directory", and nothing says
    why.
    """

    def test_no_file_has_a_backslash_in_its_name(self):
        import subprocess

        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.skipTest("git is not available")
        stray = [name for name in result.stdout.splitlines() if "\\" in name]
        self.assertEqual(
            stray, [],
            "these files break the checkout on Windows: "
            + ", ".join(stray),
        )

    def test_the_pattern_that_caused_it_is_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("\\\\*", ignored)

    def test_the_build_scripts_are_all_there(self):
        """The workflows call these by name, so a missing one stops the
        build with a message that says nothing about the reason.
        """
        for name in ("install_deps.py", "build.py", "installer_windows.py",
                     "installer_macos.py", "vendor_ffmpeg.py",
                     "verify_bundle.py", "e2e_test.py", "report_diag.py",
                     "build_gl_stubs.py", "linux_installer.py",
                     "installer_launcher.c"):
            self.assertTrue(
                (ROOT / "scripts" / name).exists(),
                f"scripts/{name} is missing",
            )


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
