"""Tests for the Windows and macOS installer packaging.

These do not run Inno Setup, NSIS or ``hdiutil`` — they check the things that
actually break: a malformed installer script, a missing icon, an
``Info.plist`` that does not describe the bundle, or a build pipeline that
forgets to call the packaging step at all.
"""
from __future__ import annotations

import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from installer_macos import (  # noqa: E402
    APP_NAME,
    BUNDLE_ID,
    PLIST_ENTRIES,
    VERSION,
    polish_app_bundle,
)
from installer_windows import inno_script, nsis_script  # noqa: E402


class TestInnoSetupScript(unittest.TestCase):
    """The Inno Setup script must be complete and self-consistent."""

    def setUp(self):
        self.script = inno_script()

    def test_declares_every_mandatory_section(self):
        for section in ("[Setup]", "[Files]", "[Icons]", "[Run]", "[Tasks]",
                        "[UninstallDelete]"):
            self.assertIn(section, self.script, f"missing {section}")

    def test_installs_the_frozen_application(self):
        # Inno resolves relative paths against the script's own directory,
        # and the script lives in build/, so the source has to be absolute.
        source = str((ROOT / "dist" / "CLIPOS").resolve()).replace("/", "\\")
        self.assertIn(r'Source: "%s\*"' % source, self.script)
        self.assertIn('DestDir: "{app}"', self.script)

    def test_source_dir_is_not_set(self):
        # When SourceDir is set, Inno resolves the Source entries relative
        # to it -- so an absolute Source would be appended to the SourceDir
        # and no file would ever be found.  That is why the installer kept
        # failing with "no files found matching".
        self.assertNotIn("SourceDir=", self.script)

    def test_the_architecture_directives_work_on_every_inno_version(self):
        # "x64compatible" needs Inno Setup 6.3; "x64" works with every 6.x.
        self.assertIn("ArchitecturesAllowed=x64\n", self.script)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64\n", self.script)
        directives = [
            line for line in self.script.splitlines()
            if line.startswith("Architectures")
        ]
        for line in directives:
            self.assertNotIn("compatible", line)

    def test_every_setup_directive_is_one_inno_setup_knows(self):
        """Inno Setup rejects the whole script when it meets a directive
        it does not know, and it says only which line was wrong.  The
        version information directives are easy to get wrong: they are
        called VersionInfo..., not AppVersionInfo....
        """
        valid = {
            "AppId", "AppName", "AppVersion", "AppVerName", "AppCopyright",
            "AppPublisher", "AppPublisherURL", "AppSupportURL",
            "AppUpdatesURL", "AppComments", "AppContact",
            "DefaultDirName", "DefaultGroupName", "DefaultUserInfoDir",
            "DefaultUserInfoGroup", "DisableProgramGroupPage",
            "DisableWelcomePage", "DisableDirPage", "AllowNoIcons",
            "AlwaysRestart", "PrivilegesRequired",
            "PrivilegesRequiredOverridesAllowed", "Compression",
            "SolidCompression", "LZMANumBlockThreads", "WizardStyle",
            "WizardSizePercent", "OutputBaseFilename", "OutputDir",
            "ArchitecturesAllowed", "ArchitecturesInstallIn64BitMode",
            "UninstallDisplayIcon", "UninstallDisplayName",
            "UninstallDisplaySize", "SetupLogging", "VersionInfoVersion",
            "VersionInfoDescription", "VersionInfoProductName",
            "VersionInfoProductVersion", "VersionInfoCompany",
            "VersionInfoCopyright", "VersionInfoTextVersion",
            "VersionInfoOriginalFilename", "UsePreviousAppDir",
            "UsePreviousGroup", "UsePreviousTasks", "UsePreviousPrivileges",
            "CloseApplications", "RestartApplications", "Uninstallable",
            "SetupMutex", "MinVersion", "OnlyBelowVersion", "Password",
            "EncryptCompressedFiles", "CreateAppDir", "CreateUninstallRegKey",
            "AppReadmeFile", "InfoBeforeFile", "InfoAfterFile",
            "LicenseFile", "DefaultLanguage",
        }
        setup = self.script.split("[Setup]", 1)[1].split("\n[", 1)[0]
        unknown = []
        for line in setup.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key not in valid:
                unknown.append(key)
        self.assertEqual(
            unknown, [],
            "Inno Setup does not know these directives: "
            + ", ".join(unknown),
        )

    def test_the_version_information_directives_are_named_correctly(self):
        self.assertIn("VersionInfoDescription=", self.script)
        self.assertNotIn("AppVersionInfo", self.script)

    def test_the_application_id_is_a_literal_and_not_a_constant(self):
        """Inno Setup reads ``{name}`` as a constant, so a GUID has to be
        written with doubled braces.  With single braces the compiler
        says "Unknown constant" and stops.
        """
        line = [l for l in self.script.splitlines() if l.startswith("AppId=")]
        self.assertEqual(len(line), 1)
        self.assertTrue(
            line[0].startswith("AppId={{") and line[0].endswith("}}"),
            f"the application id must use doubled braces: {line[0]}",
        )

    def test_every_brace_is_a_constant_inno_setup_knows(self):
        known = {
            "app", "group", "autodesktop", "autopf", "autoprograms",
            "commonpf", "commonprograms", "commonstartup", "commonstartmenu",
            "commondesktop", "commonappdata", "localappdata", "userappdata",
            "userdesktop", "userdocs", "userprofiledocuments", "userpictures",
            "usermusic", "temp", "src", "sys", "win", "sd", "pf", "cf",
            "cf32", "cf64", "fonts", "dao", "dotnetfx", "dotnetfx11",
            "dotnetfx20", "dotnetfx35", "dotnetfx40", "dotnetfx45",
            "uninstallexe", "code", "license", "help", "readme", "groupdocs",
        }
        import re
        unknown = []
        for line in self.script.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            # A doubled brace is a literal, not a constant.
            stripped = re.sub(r"\{\{[^}]*\}\}", "", stripped)
            for match in re.finditer(r"\{([^{}]*)\}", stripped):
                if match.group(1) not in known:
                    unknown.append(match.group(1))
        self.assertEqual(
            unknown, [],
            "Inno Setup does not know these constants: " + ", ".join(unknown),
        )

    def test_creates_a_start_menu_shortcut(self):
        self.assertIn('{group}\\CLIPOS', self.script)

    def test_offers_a_desktop_shortcut_as_an_optional_task(self):
        self.assertIn('{autodesktop}\\CLIPOS', self.script)
        self.assertIn('Name: "desktopicon"', self.script)

    def test_registers_an_uninstaller(self):
        self.assertIn("UninstallDisplayIcon", self.script)
        self.assertIn("UninstallDisplayName", self.script)

    def test_does_not_require_administrator_rights(self):
        # A creator tool should install for a standard user without a UAC
        # prompt; {autopf} then resolves inside the user's own profile.
        self.assertIn("PrivilegesRequired=lowest", self.script)
        self.assertIn("PrivilegesRequiredOverridesAllowed=dialog", self.script)

    def test_uses_the_same_app_id_for_install_and_uninstall(self):
        # Inno derives the uninstall registry key from AppId, so it must be
        # a fixed GUID rather than something that changes between builds.
        app_id = next(
            line for line in self.script.splitlines() if line.startswith("AppId=")
        )
        value = app_id.split("=", 1)[1].strip()
        self.assertTrue(value.startswith("{") and value.endswith("}"))
        self.assertEqual(len(value.strip("{}")), 32)

    def test_the_output_directory_is_absolute(self):
        # The script is written into build/, so a relative OutputDir would
        # put the installer somewhere nobody looks for it.
        output = str((ROOT / "build" / "dist").resolve()).replace("/", "\\")
        self.assertIn(f"OutputDir={output}", self.script)

    def test_the_source_directory_is_absolute(self):
        source = str((ROOT / "dist" / "CLIPOS").resolve()).replace("/", "\\")
        # Inno wants a backslash before the wildcard.
        self.assertIn(r'Source: "%s\*"' % source, self.script)
        # A relative path would silently point at build/dist/CLIPOS.
        self.assertNotIn('Source: "dist', self.script)

    def test_the_paths_use_windows_separators(self):
        # A forward slash next to the backslash wildcard confuses the
        # compiler, so the separators are normalised.
        for line in self.script.splitlines():
            if line.startswith("Source:") or line.startswith("OutputDir="):
                self.assertNotIn("/", line)

    def test_version_is_stamped_into_the_installer(self):
        self.assertIn(f"AppVersion={VERSION}", self.script)
        self.assertIn(f"OutputBaseFilename={APP_NAME}-Setup", self.script)

    def test_uses_lzma2_compression(self):
        self.assertIn("Compression=lzma2", self.script)
        self.assertIn("SolidCompression=yes", self.script)

    def test_launches_the_app_after_installing(self):
        self.assertIn("postinstall", self.script)
        self.assertIn(f"{{app}}\\{APP_NAME}.exe", self.script)


class TestNsisScript(unittest.TestCase):
    """The NSIS fallback must be equally complete."""

    def setUp(self):
        self.script = nsis_script()

    def test_declares_every_mandatory_section(self):
        for section in ("Section \"Install\"", "Section \"Uninstall\""):
            self.assertIn(section, self.script)

    def test_installs_the_frozen_application(self):
        # NSIS resolves relative paths against the script's own directory
        # too, so the source has to be absolute.
        source = str((ROOT / "dist" / "CLIPOS").resolve()).replace("/", "\\")
        self.assertIn(r'File /r "%s\*"' % source, self.script)
        self.assertIn('SetOutPath "$INSTDIR"', self.script)

    def test_writes_the_installer_to_an_absolute_path(self):
        output = str(
            (ROOT / "build" / "dist" / "CLIPOS-Setup.exe").resolve()
        ).replace("/", "\\")
        self.assertIn(f'OutFile "{output}"', self.script)

    def test_creates_shortcuts_and_an_uninstaller(self):
        self.assertIn('CreateShortcut "$SMPROGRAMS\\CLIPOS\\CLIPOS.lnk"', self.script)
        self.assertIn('CreateShortcut "$DESKTOP\\CLIPOS.lnk"', self.script)
        self.assertIn('WriteUninstaller "$INSTDIR\\uninstall.exe"', self.script)

    def test_registers_the_uninstall_entry(self):
        self.assertIn("CurrentVersion\\Uninstall\\CLIPOS", self.script)
        self.assertIn('"UninstallString"', self.script)

    def test_cleans_up_on_uninstall(self):
        self.assertIn('RMDir /r "$INSTDIR"', self.script)
        self.assertIn('Delete "$DESKTOP\\CLIPOS.lnk"', self.script)

    def test_installs_for_a_standard_user(self):
        # RequestExecutionLevel user keeps the installer free of a UAC
        # prompt; the target directory lives inside the user profile.
        self.assertIn("RequestExecutionLevel user", self.script)
        self.assertIn("$LOCALAPPDATA\\Programs\\CLIPOS", self.script)

    def test_removes_the_uninstall_registry_key(self):
        self.assertIn('DeleteRegKey HKCU "Software\\Microsoft\\Windows'
                      '\\CurrentVersion\\Uninstall\\CLIPOS"', self.script)


class TestMacOSBundle(unittest.TestCase):
    """The .app bundle must be described correctly by its Info.plist."""

    def _make_bundle(self, tmp: Path) -> Path:
        app = tmp / f"{APP_NAME}.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleName": APP_NAME,
            "CFBundleExecutable": APP_NAME,
        }))
        (app / "Contents" / "MacOS" / APP_NAME).write_bytes(b"\xcf\xfa\xed\xfe")
        return app

    def test_info_plist_is_completed(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._make_bundle(Path(td))
            polish_app_bundle(app)
            info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())

        for key in ("CFBundleIdentifier", "CFBundleShortVersionString",
                    "CFBundleIconFile", "LSMinimumSystemVersion",
                    "NSHighResolutionCapable", "CFBundlePackageType"):
            self.assertIn(key, info, f"Info.plist is missing {key}")

    def test_bundle_identifier_is_a_reverse_dns_name(self):
        self.assertEqual(PLIST_ENTRIES["CFBundleIdentifier"], BUNDLE_ID)
        self.assertTrue(BUNDLE_ID.startswith("com."))
        self.assertIn(".", BUNDLE_ID)

    def test_declares_itself_a_video_application(self):
        self.assertEqual(
            PLIST_ENTRIES["LSApplicationCategoryType"], "public.app-category.video"
        )

    def test_states_the_minimum_macos_version(self):
        self.assertEqual(PLIST_ENTRIES["LSMinimumSystemVersion"], "11.0")

    def test_installs_the_icns_icon(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._make_bundle(Path(td))
            polish_app_bundle(app)
            icon = app / "Contents" / "Resources" / "app_icon.icns"
            self.assertTrue(icon.exists())
            self.assertGreater(icon.stat().st_size, 1024)

    def test_keeps_the_executable_name_in_sync(self):
        with tempfile.TemporaryDirectory() as td:
            app = self._make_bundle(Path(td))
            polish_app_bundle(app)
            info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
            self.assertEqual(info["CFBundleExecutable"], APP_NAME)
            self.assertTrue((app / "Contents" / "MacOS" / APP_NAME).exists())


class TestSelfExtractingInstaller(unittest.TestCase):
    """The toolchain-independent installer must produce a real PE file.

    This is the path used when neither Inno Setup nor NSIS is installed on
    the build machine, so it is the one that has to work everywhere.
    """

    @classmethod
    def setUpClass(cls):
        from installer_windows import _find_windows_compiler

        cls.compiler = _find_windows_compiler()
        if cls.compiler is None:
            raise unittest.SkipTest(
                "no Windows cross compiler available "
                "(pip install ziglang, or apt install mingw-w64)"
            )

        import tempfile

        cls.tmp = Path(tempfile.mkdtemp())
        app = cls.tmp / "CLIPOS"
        (app / "_internal" / "resources" / "ffmpeg" / "win32-x64").mkdir(parents=True)
        (app / "CLIPOS.exe").write_bytes(b"MZ fake")
        (app / "_internal" / "resources" / "ffmpeg" / "win32-x64"
         / "ffmpeg.exe").write_bytes(b"FAKE FFMPEG")
        (app / "app_icon.ico").write_bytes(b"ICO")

        from installer_windows import build_selfextracting_installer

        cls.installer = build_selfextracting_installer(app, cls.tmp / "out")

    def test_the_installer_is_a_windows_executable(self):
        data = self.installer.read_bytes()
        self.assertEqual(data[:2], b"MZ", "not a DOS/PE image")
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        self.assertEqual(data[pe_offset:pe_offset + 4], b"PE\x00\x00")

    def test_the_executable_targets_64_bit_windows(self):
        data = self.installer.read_bytes()
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        machine = int.from_bytes(data[pe_offset + 4:pe_offset + 6], "little")
        self.assertEqual(machine, 0x8664, "not an x86-64 image")

    def test_the_executable_has_no_console_window(self):
        data = self.installer.read_bytes()
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        optional = pe_offset + 24
        magic = int.from_bytes(data[optional:optional + 2], "little")
        self.assertEqual(magic, 0x20B, "expected a PE32+ image")
        subsystem = int.from_bytes(data[optional + 68:optional + 70], "little")
        self.assertEqual(subsystem, 2, "expected the GUI subsystem")

    def test_the_trailer_records_the_payload(self):
        import struct

        data = self.installer.read_bytes()
        magic, length, _ = struct.unpack("<8sII", data[-16:])
        self.assertEqual(magic, b"CLIPOSPA")
        self.assertGreater(length, 0)
        self.assertLess(length, len(data))

    def test_the_payload_is_a_valid_zip_holding_the_application(self):
        import io
        import struct
        import zipfile

        data = self.installer.read_bytes()
        _, length, _ = struct.unpack("<8sII", data[-16:])
        payload = data[-16 - length:-16]
        self.assertEqual(payload[:2], b"PK")

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip(), "the payload is corrupt")
            names = archive.namelist()
            self.assertIn("CLIPOS/CLIPOS.exe", names)
            self.assertTrue(
                any("ffmpeg.exe" in name for name in names),
                "the bundled FFmpeg is missing from the installer",
            )

    def test_the_installer_carries_the_application_icon(self):
        data = self.installer.read_bytes()
        # The icon travels inside the payload, so it must appear in the file.
        self.assertIn(b"app_icon.ico", data)


class TestStaging(unittest.TestCase):
    """The installer must read from a short path.

    Windows cannot open a path longer than 260 characters.  A frozen
    PyInstaller tree carries the whole Python runtime, Qt and OpenCV, so the
    deepest file goes past that easily -- and the Inno Setup compiler fails
    with "The system cannot find the path specified" while it compresses.
    """

    @classmethod
    def setUpClass(cls):
        from installer_windows import staging_dir

        cls.staging = staging_dir()

    def test_the_staging_directory_is_short(self):
        # Anything longer than this defeats the point of staging.
        self.assertLess(len(str(self.staging)), 40,
                        f"the staging path is too long: {self.staging}")

    def test_the_staging_directory_is_not_inside_the_repository(self):
        # The repository lives in a long path on a CI runner.
        self.assertNotIn(str(ROOT), str(self.staging))

    def test_staging_copies_the_application(self):
        import shutil
        import tempfile

        from installer_windows import stage_for_installer

        source = Path(tempfile.mkdtemp()) / "CLIPOS"
        (source / "_internal" / "resources").mkdir(parents=True)
        (source / "CLIPOS.exe").write_bytes(b"MZ")
        (source / "_internal" / "resources" / "app_icon.ico").write_bytes(b"ICO")

        try:
            staged = stage_for_installer(source)
            self.assertTrue(staged.exists())
            self.assertTrue((staged / "CLIPOS.exe").exists())
            self.assertTrue((staged / "_internal" / "resources"
                             / "app_icon.ico").exists())
        finally:
            shutil.rmtree(self.staging, ignore_errors=True)
            shutil.rmtree(source.parent, ignore_errors=True)


class TestBuildPipeline(unittest.TestCase):
    """The build script must actually reach the packaging step."""

    def test_build_script_calls_the_windows_installer(self):
        text = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
        self.assertIn("from installer_windows import build_windows_installer",
                      text)
        self.assertIn("from installer_macos import build_dmg, finalize_app_bundle",
                      text)

    def test_build_script_no_longer_duplicates_the_installer_scripts(self):
        text = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
        # The scripts now live in their own modules so they can be tested.
        self.assertNotIn("def _inno_script", text)
        self.assertNotIn("def _nsis_script", text)

    def test_a_workflow_builds_both_platforms(self):
        workflow = ROOT / ".github" / "workflows" / "build-installers.yml"
        self.assertTrue(workflow.exists(), "no installer workflow")
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("windows-2022", text)
        self.assertIn("macos-14", text)
        self.assertIn("scripts/build.py windows", text)
        self.assertIn("scripts/build.py macos", text)
        self.assertIn("innosetup", text.lower())

    def test_the_inno_setup_version_is_pinned(self):
        """The Inno Setup package on Chocolatey has moved between 5.x and
        6.x over the years.  Inno 5 does not understand the
        ``ArchitecturesAllowed`` directive at all, so the version has to be
        pinned or the installer script is rejected.
        """
        for name in ("build-installers.yml", "release.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "choco install innosetup --version=", text,
                f"{name} does not pin the Inno Setup version",
            )

    def test_only_one_macos_runner_is_needed(self):
        """A second macOS runner is not always free, and the job that
        cannot get one is cancelled.  Both applications are therefore built
        on the same runner, with the Intel one cross-compiled.
        """
        for name in ("build-installers.yml", "release.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            self.assertNotIn(
                "macos-13", text,
                f"{name} still needs a second macOS runner",
            )
            self.assertIn(
                "--target-arch x86_64", text,
                f"{name} does not build the Intel application",
            )

    def test_the_disk_image_names_carry_the_architecture(self):
        """Both disk images have to survive on one machine."""
        text = (ROOT / "scripts" / "installer_macos.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("suffix = f\"-{arch}\" if arch else \"\"", text)

    def test_the_compiler_output_directory_is_created(self):
        """Neither Inno Setup nor NSIS creates the directory they write
        their installer to, and both fail with a bare "Can't open output
        file" when it is missing.
        """
        text = (ROOT / "scripts" / "installer_windows.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'compiler_out = build_dir / "dist"', text,
            "the installer compiler output directory is never created",
        )
        self.assertIn(
            'compiler_out.mkdir(parents=True, exist_ok=True)', text,
            "the installer compiler output directory is never created",
        )

    def test_the_compilers_write_into_the_created_directory(self):
        text = (ROOT / "scripts" / "installer_windows.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'produced = compiler_out / f"{APP_NAME}-Setup.exe"', text,
            "the installer is read back from a directory that may not exist",
        )


class TestFailureReporting(unittest.TestCase):
    """A packaging failure has to say what went wrong.

    The job summary is not always readable from outside, and the build
    logs are stored on a host that cannot always be reached, so the
    failure has to be written into ``build/build-error.log`` as well.
    """

    def test_a_failure_is_written_to_the_build_error_log(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import installer_windows

        log = ROOT / "build" / "build-error.log"
        before = log.read_text(encoding="utf-8") if log.exists() else ""
        try:
            installer_windows._write_summary("Test failure", "the details")
            after = log.read_text(encoding="utf-8")
        finally:
            if log.exists():
                log.write_text(before, encoding="utf-8")
        self.assertIn("Test failure", after)
        self.assertIn("the details", after)

    def test_the_inno_report_contains_the_compiler_output(self):
        text = (ROOT / "scripts" / "installer_windows.py").read_text(
            encoding="utf-8"
        )
        # The report has to carry what the compiler actually said, not just
        # the exit code.
        self.assertIn("--- stdout ---", text)
        self.assertIn("--- stderr ---", text)
        # And the compiler's own log, which names the file it could not open.
        self.assertIn("Setup Log.txt", text)

    def test_the_nsis_failure_is_reported_too(self):
        text = (ROOT / "scripts" / "installer_windows.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"NSIS failed"', text)


if __name__ == "__main__":
    unittest.main()
