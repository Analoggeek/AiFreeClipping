"""Regressions for universal Python accidentally installing ARM Intel wheels."""
import importlib.util
from pathlib import Path
from unittest.mock import patch, Mock
import unittest


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
            self.assertIn('google-auth-oauthlib>=1.2,<2', cmd)

    def test_verifier_rejects_wrong_interpreter(self):
        with patch.object(verify_arch.sys,'platform','darwin'), patch.object(verify_arch.platform,'machine',return_value='arm64'):
            with self.assertRaisesRegex(RuntimeError,'Expected macOS x86_64'):
                verify_arch.verify('x86_64')
