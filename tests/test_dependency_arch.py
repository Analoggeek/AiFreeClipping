"""Regressions for universal Python accidentally installing ARM Intel wheels."""
import importlib.util
from pathlib import Path
from unittest.mock import patch, Mock
import unittest
import platform
import sys
import tempfile
import subprocess


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1]/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deps = load('install_deps')
verify_arch = load('verify_python_arch')


class ArchitectureTests(unittest.TestCase):
    def test_intel_pip_is_explicitly_launched_under_rosetta(self):
        with patch.object(deps.sys, 'platform', 'darwin'), patch.object(deps.platform, 'machine', return_value='x86_64'):
            self.assertEqual(deps.pip('install', 'cryptography'), ['arch','-x86_64',deps.sys.executable,'-m','pip','install','--only-binary=cryptography','cryptography'])

    def test_arm_pip_stays_arm(self):
        with patch.object(deps.sys, 'platform', 'darwin'), patch.object(deps.platform, 'machine', return_value='arm64'):
            self.assertEqual(deps.python_command('-c', 'pass')[:2], ['arch','-arm64'])

    def test_non_mac_uses_normal_python(self):
        with patch.object(deps.sys, 'platform', 'win32'):
            self.assertEqual(deps.pip('show','numpy'), [deps.sys.executable,'-m','pip','show','numpy'])

    def test_installed_check_also_preserves_arch(self):
        with patch.object(deps.sys, 'platform', 'darwin'), patch.object(deps.platform, 'machine', return_value='x86_64'), patch.object(deps.subprocess,'run', return_value=Mock(returncode=0)) as run:
            self.assertTrue(deps.installed('cryptography'))
            self.assertEqual(run.call_args.args[0][:2], ['arch','-x86_64'])

    def test_mac_crypto_cannot_fall_back_to_arm_source_build(self):
        with patch.object(deps.sys, 'platform', 'darwin'), patch.object(deps.platform, 'machine', return_value='x86_64'):
            cmd = deps.pip('install', *deps.CORE)
            self.assertIn('--only-binary=cryptography', cmd)
            self.assertIn('faster-whisper>=1.0,<2', cmd)

    def test_verifier_rejects_wrong_interpreter(self):
        with patch.object(verify_arch.sys,'platform','darwin'), patch.object(verify_arch.platform,'machine',return_value='arm64'):
            with self.assertRaisesRegex(RuntimeError,'Expected macOS x86_64'):
                verify_arch.verify('x86_64')


class NativeLipoTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'requires Apple lipo')
    def test_real_lipo_command_on_python(self):
        # -verify_arch accepts multiple architectures; the input filename must
        # precede it or Apple's lipo parses that filename as another arch.
        subprocess.run(['lipo', sys.executable, '-verify_arch', platform.machine()], check=True)

    def test_audit_supplies_input_before_variadic_architectures(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder)/'bad.so'
            binary.write_bytes(b'fixture')
            with patch.object(verify_arch.sys,'platform','darwin'), patch.object(verify_arch.platform,'machine',return_value='x86_64'), patch.object(verify_arch.sysconfig,'get_path',return_value=folder), patch.object(verify_arch.subprocess,'run',return_value=Mock(returncode=1,stderr='wrong architecture')) as run:
                with self.assertRaisesRegex(RuntimeError,'wrong architecture'):
                    verify_arch.verify('x86_64')
                self.assertEqual(run.call_args.args[0], ['lipo',str(binary.resolve()),'-verify_arch','x86_64'])
