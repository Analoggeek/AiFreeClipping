"""Tests for the architecture of the native binaries and of the macOS builds.

An application that is built for the wrong architecture is worse than no
application at all: it does not start, and nothing in the log says why.
These tests cover the two ways that goes wrong.

**The bundled binaries.**  The packages the build downloads are not always
labelled correctly.  The ``ffprobe-static`` tarball puts an Intel binary
in its Apple Silicon folder, which means an Apple Silicon machine runs it
through Rosetta -- or not at all, when Rosetta is not installed.  Every
binary is now checked against the architecture it is filed under.

**The macOS builds.**  PyInstaller has to be told which architecture to
build for.  Setting ``ARCHFLAGS`` is not enough: PyInstaller keeps the
architecture of the machine that is doing the build, uses the wrong
bootloader, and skips the checks on the collected binaries.  The Intel
application has to be built with ``--target-architecture x86_64``.
"""
from __future__ import annotations

import os
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from clipos.core.binary_arch import (  # noqa: E402
    EXPECTED_ARCH,
    binary_arch,
    can_run,
    check_arch,
    running_architecture,
)


def _macho_header(cputype: int) -> bytes:
    """A minimal 64-bit Mach-O header for the given CPU type."""
    return struct.pack("<Iii", 0xFEEDFACF, cputype, 0)


def _elf_header(machine: int) -> bytes:
    """A minimal 64-bit ELF header for the given machine."""
    return (b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8)
            + struct.pack("<HHI", 3, machine, 1) + struct.pack("<I", 0)
            + struct.pack("<HH", 0, 0) + struct.pack("<Q", 0))


class TestArchitectureReading(unittest.TestCase):
    """The architecture of a binary has to be read out of the file."""

    def test_reads_a_macho_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bin"
            path.write_bytes(_macho_header(0x0100000C))
            self.assertEqual(binary_arch(path), "arm64")

    def test_reads_an_intel_macho_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bin"
            path.write_bytes(_macho_header(0x01000007))
            self.assertEqual(binary_arch(path), "x86_64")

    def test_reads_a_fat_macho_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bin"
            header = struct.pack(">II", 0xCAFEBABE, 2)
            # The fat header is big endian, and so is each entry.
            entry = struct.pack(">iiIII", 0x0100000C, 3, 0, 0, 0)
            entry2 = struct.pack(">iiIII", 0x01000007, 3, 0, 0, 0)
            path.write_bytes(header + entry + entry2)
            found = binary_arch(path)
            self.assertIn("arm64", found.split("|"))
            self.assertIn("x86_64", found.split("|"))

    def test_reads_an_elf_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bin"
            path.write_bytes(_elf_header(62))
            self.assertEqual(binary_arch(path), "x86_64")

    def test_says_nothing_about_a_file_that_is_not_a_binary(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "notes.txt"
            path.write_bytes(b"just some text, not a binary at all")
            self.assertIsNone(binary_arch(path))


class TestArchitectureChecks(unittest.TestCase):
    """A binary filed under the wrong architecture must be refused."""

    def test_a_matching_binary_passes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bin"
            path.write_bytes(_macho_header(0x0100000C))
            # No exception means it passed.
            check_arch(path, "darwin-arm64")

    def test_a_mismatched_binary_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bin"
            # An Intel binary filed as Apple Silicon.
            path.write_bytes(_macho_header(0x01000007))
            with self.assertRaises(SystemExit) as caught:
                check_arch(path, "darwin-arm64")
            self.assertIn("x86_64", str(caught.exception))
            self.assertIn("arm64", str(caught.exception))

    def test_every_platform_has_an_expected_architecture(self):
        for key in ("darwin-arm64", "darwin-x64", "linux-x64",
                    "win32-x64", "win32-ia32", "linux-ia32"):
            self.assertIn(key, EXPECTED_ARCH)

    def test_the_packages_are_not_mixed_up(self):
        """Each platform has to come from a package of its own.

        The "ffprobe-static" tarball puts an Intel binary in its Apple
        Silicon folder, so it cannot be used for the Apple Silicon
        build.  Each platform therefore gets its own package, and the
        name has to say which machine it is for.
        """
        from scripts.vendor_ffmpeg import FFPROBE_PKGS

        for key, (pkg, _) in FFPROBE_PKGS.items():
            self.assertIn(
                key.rsplit("-", 1)[-1], pkg,
                f"the {key} ffprobe comes from {pkg}, which is a package "
                f"for a different machine",
            )

    def test_the_ffprobe_static_tarball_is_not_used(self):
        """Its Apple Silicon folder holds an Intel binary."""
        from scripts.vendor_ffmpeg import FFPROBE_PKGS

        for key, (pkg, _) in FFPROBE_PKGS.items():
            self.assertNotIn(
                "ffprobe-static", pkg,
                f"the {key} ffprobe comes from the ffprobe-static tarball, "
                f"whose Apple Silicon folder holds an Intel binary",
            )


class TestVendoredBinaries(unittest.TestCase):
    """The binaries that are actually downloaded have to be right.

    The test is skipped when the binaries have not been fetched, because
    they are deliberately not kept in the repository.
    """

    def test_the_downloaded_binaries_match_their_folder(self):
        root = ROOT / "resources" / "ffmpeg"
        if not root.is_dir():
            self.skipTest("the native binaries have not been fetched")
        checked = 0
        for key, expected in EXPECTED_ARCH.items():
            folder = root / key
            if not folder.is_dir():
                continue
            for binary in sorted(folder.iterdir()):
                if not binary.is_file():
                    continue
                found = binary_arch(binary)
                if found is None:
                    continue
                checked += 1
                self.assertIn(
                    expected, found.split("|"),
                    f"{binary} is a {found} binary but it is filed as "
                    f"{expected}",
                )
        if not checked:
            self.skipTest("no native binaries to check")


class TestMacOSArchitecture(unittest.TestCase):
    """The macOS builds have to be built for the architecture they claim."""

    def _build_script(self) -> str:
        return (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")

    def test_pyinstaller_is_told_which_architecture_to_build_for(self):
        """ARCHFLAGS alone is not enough.

        PyInstaller uses the architecture of the machine that is doing the
        build unless it is told otherwise: it keeps the wrong bootloader
        and skips the checks on the collected binaries.  The Intel
        application was therefore an Apple Silicon application with an
        Intel name.
        """
        text = self._build_script()
        self.assertIn("--target-architecture", text)

    def test_the_target_architecture_reaches_pyinstaller(self):
        text = self._build_script()
        self.assertIn("pyinstaller_args(target, target_arch)", text)
        self.assertIn('freeze("macos", target_arch)', text)

    def test_the_architecture_argument_is_accepted(self):
        text = self._build_script()
        self.assertIn("--target-arch", text)

    def test_the_bundle_check_looks_at_the_architecture(self):
        """A bundle named for one machine must be built for that machine."""
        text = (ROOT / "scripts" / "verify_bundle.py").read_text(encoding="utf-8")
        self.assertIn("check_architecture", text)
        self.assertIn("right architecture", text)


class TestWorkflows(unittest.TestCase):
    """Both macOS applications have to be built, and both have to be checked."""

    def _workflows(self):
        for name in ("build-installers.yml", "release.yml"):
            path = ROOT / ".github" / "workflows" / name
            if path.exists():
                yield name, path.read_text(encoding="utf-8")

    def test_the_intel_build_uses_an_intel_python(self):
        """An Intel application needs an Intel Python.

        The extension modules have to be compiled for the machine the
        application is meant to run on, so the Python that does the
        freezing has to be an Intel one.  On an Apple Silicon runner the
        Python that is already there is the wrong one.

        A virtual environment made from that Python would not help: it
        would still hold Apple Silicon wheels, and PyInstaller refuses
        to build an Intel application out of them.  The Intel interpreter
        itself is installed.
        """
        for name, text in self._workflows():
            self.assertIn(
                "architecture: x64", text,
                f"{name} does not install an Intel Python for the Intel "
                f"application",
            )
            self.assertIn(
                "CLIPOS_BUILD_PYTHON", text,
                f"{name} does not tell the build which Python to use",
            )
            self.assertNotIn(
                "virtualenv", text,
                f"{name} makes a virtual environment for the Intel build; "
                f"it would still hold Apple Silicon wheels",
            )

    def test_the_build_finds_the_interpreter_for_the_architecture(self):
        """The interpreter has to match the architecture being built.

        On an Apple Silicon machine the interpreter that comes first on
        the path is the Apple Silicon one, and an Intel build made with
        it produces an application with Apple Silicon extension modules.
        The build therefore looks for an interpreter of the right
        architecture.
        """
        text = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
        self.assertIn("find_python_for_arch", text)
        self.assertIn("_python_architecture", text)

    def test_the_build_script_honours_the_python_it_is_given(self):
        text = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
        self.assertIn("CLIPOS_BUILD_PYTHON", text)

    def test_both_applications_are_built(self):
        for name, text in self._workflows():
            self.assertIn("--target-arch arm64", text, f"{name} does not build "
                          f"the Apple Silicon application")
            self.assertIn("--target-arch x86_64", text, f"{name} does not "
                          f"build the Intel application")

    def test_the_apple_silicon_application_is_not_overwritten(self):
        """The Intel build must not land on top of the other one."""
        for name, text in self._workflows():
            self.assertIn(
                "CLIPOS-arm64.app", text,
                f"{name} does not move the Apple Silicon application out of "
                f"the way before building the Intel one",
            )

    def test_both_applications_are_checked(self):
        for name, text in self._workflows():
            self.assertIn(
                "CLIPOS-intel.app", text,
                f"{name} does not check the Intel application",
            )


class TestBundleLayout(unittest.TestCase):
    """The bundle check has to understand a macOS application bundle.

    A macOS application keeps its files under ``Contents``, and the
    one-folder build on the other platforms keeps them under
    ``_internal``.  The check used to understand only the second one, so
    it failed on every macOS bundle.
    """

    def _make_app(self, tmp: Path, name: str = "CLIPOS-intel.app") -> Path:
        app = tmp / name
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Frameworks" / "PySide6").mkdir(parents=True)
        (app / "Contents" / "Resources").mkdir(parents=True)
        (app / "Contents" / "Frameworks" / "base_library.zip").write_bytes(b"x")
        (app / "Contents" / "MacOS" / "CLIPOS").write_bytes(b"\xcf\xfa\xed\xfe")
        return app

    def test_an_application_bundle_is_recognised(self):
        import verify_bundle

        with tempfile.TemporaryDirectory() as td:
            app = self._make_app(Path(td))
            self.assertTrue(verify_bundle.is_app_bundle(app))

    def test_the_files_of_a_bundle_are_found(self):
        import verify_bundle

        with tempfile.TemporaryDirectory() as td:
            app = self._make_app(Path(td))
            self.assertEqual(verify_bundle.find_bundle(app), app)
            self.assertEqual(
                verify_bundle.internal_dir(app), app / "Contents"
            )

    def test_the_resources_are_found_in_a_bundle(self):
        """The resources may sit one level down inside the bundle.

        PyInstaller puts them under ``Contents/Resources/resources``, and
        the ``Contents/Resources`` directory is always there whether or
        not it holds anything -- so the directory is found by what is
        inside it.
        """
        import verify_bundle

        with tempfile.TemporaryDirectory() as td:
            app = self._make_app(Path(td), "CLIPOS-arm64.app")
            # PyInstaller keeps them one level down.
            resources = app / "Contents" / "Resources" / "resources"
            resources.mkdir()
            (resources / "ffmpeg").mkdir()
            (resources / "sounds").mkdir()
            found = verify_bundle.resource_root(app)
            self.assertTrue((found / "ffmpeg").is_dir())

    def test_the_resources_are_found_directly_in_the_bundle(self):
        import verify_bundle

        with tempfile.TemporaryDirectory() as td:
            app = self._make_app(Path(td))
            (app / "Contents" / "Resources" / "ffmpeg").mkdir()
            found = verify_bundle.resource_root(app)
            self.assertTrue((found / "ffmpeg").is_dir())

    def test_the_application_binary_is_found_in_a_bundle(self):
        import verify_bundle

        with tempfile.TemporaryDirectory() as td:
            app = self._make_app(Path(td))
            found = verify_bundle.find_bundle(app)
            binary = (
                found / "Contents" / "MacOS" / "CLIPOS"
            )
            self.assertTrue(binary.exists())


class TestRuntimeGuard(unittest.TestCase):
    """The application should notice a binary that cannot run here."""

    def test_the_guard_exists(self):
        from clipos.core.ffmpeg import (
            binary_architecture,
            bundled_binary_matches_machine,
        )

        self.assertTrue(callable(bundled_binary_matches_machine))
        self.assertTrue(callable(binary_architecture))

    def test_a_missing_binary_is_not_a_problem(self):
        from clipos.core.ffmpeg import bundled_binary_matches_machine

        self.assertTrue(bundled_binary_matches_machine(None))
        self.assertTrue(bundled_binary_matches_machine(""))

    def test_the_running_architecture_is_known(self):
        from clipos.core.ffmpeg import _running_architecture

        self.assertIn(
            _running_architecture(),
            ("x86_64", "arm64", "i386"),
        )


if __name__ == "__main__":
    unittest.main()
