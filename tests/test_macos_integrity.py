"""Final-seal and DMG integrity regressions, including native macOS tests."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import installer_macos as mac


class SigningTests(unittest.TestCase):
    def test_no_identity_still_reseals_app_without_claiming_notarization(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(mac.shutil, 'which', return_value='/usr/bin/codesign'), patch.object(mac.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertTrue(mac.sign_app(Path('CLIPOS.app')))
            sign = run.call_args_list[0].args[0]
            self.assertEqual(sign[sign.index('--sign')+1], '-')
            self.assertNotIn('runtime', sign)
            self.assertNotIn('--timestamp', sign)
            verify = run.call_args_list[1]
            self.assertIn('--strict', verify.args[0])
            self.assertTrue(verify.kwargs['check'])

    def test_failed_signature_stops_packaging(self):
        with patch.object(mac, 'polish_app_bundle'), patch.object(mac, 'sign_app', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'refusing to package'):
                mac.finalize_app_bundle(Path('CLIPOS.app'))

    def test_finalization_orders_all_mutations_before_signing(self):
        events = []
        with patch.dict(os.environ, {}, clear=True), patch.object(mac, 'polish_app_bundle', side_effect=lambda app: events.append('polish')), patch.object(mac, 'sign_app', side_effect=lambda *args: events.append('sign') or True), patch.object(mac, 'verify_app_signature', side_effect=lambda app: events.append('verify')):
            mac.finalize_app_bundle(Path('CLIPOS.app'))
        self.assertEqual(events, ['polish', 'sign', 'verify'])

    def test_signature_verification_failure_is_not_ignored(self):
        with patch.object(mac.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'codesign')):
            with self.assertRaises(subprocess.CalledProcessError):
                mac.verify_app_signature(Path('CLIPOS.app'))

    def test_notarization_uses_zip_and_correct_stapler_tool(self):
        def command(args, **kwargs):
            return Mock(returncode=0, stdout=json.dumps({'status': 'Accepted'}), stderr='')
        with patch.dict(os.environ, {'CLIPOS_NOTARY_PROFILE': 'ci-profile'}), patch.object(mac.sys, 'platform', 'darwin'), patch.object(mac.shutil, 'which', return_value='/usr/bin/xcrun'), patch.object(mac.subprocess, 'run', side_effect=command) as run:
            self.assertTrue(mac.notarize_app(Path('CLIPOS.app')))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0][:4], ['ditto', '-c', '-k', '--keepParent'])
            self.assertEqual(commands[-2], ['xcrun', 'stapler', 'staple', 'CLIPOS.app'])
            self.assertEqual(commands[-1], ['xcrun', 'stapler', 'validate', 'CLIPOS.app'])

    def test_notary_rejection_does_not_staple(self):
        with patch.dict(os.environ, {'CLIPOS_NOTARY_PROFILE': 'ci-profile'}), patch.object(mac.sys, 'platform', 'darwin'), patch.object(mac.shutil, 'which', return_value='xcrun'), patch.object(mac.subprocess, 'run', return_value=Mock(returncode=0, stdout='{"status":"Invalid"}', stderr='')) as run:
            with self.assertRaisesRegex(RuntimeError, 'not accepted'):
                mac.notarize_app(Path('CLIPOS.app'))
            self.assertFalse(any('stapler' in c.args[0] for c in run.call_args_list))

    def test_mounted_image_detaches_if_its_signature_fails(self):
        mount_info = plistlib.dumps({'system-entities': [{'dev-entry': '/dev/disk99', 'mount-point': '/Volumes/test'}]})
        with patch.object(mac.subprocess, 'run', return_value=Mock(stdout=mount_info)) as run, patch.object(mac, 'verify_app_signature', side_effect=RuntimeError('bad seal')):
            with self.assertRaisesRegex(RuntimeError, 'bad seal'):
                mac.verify_dmg(Path('test.dmg'), 'intel')
            self.assertEqual(run.call_args_list[-1].args[0], ['hdiutil', 'detach', '/dev/disk99'])


@unittest.skipUnless(sys.platform == 'darwin', 'Native codesign and hdiutil require macOS')
class NativeIntegrityTests(unittest.TestCase):
    def test_intel_and_arm_final_app_and_actual_dmg(self):
        # A tiny real executable exercises the packaging bug without downloading
        # AI models. This is packaging proof, not a full CLIPOS workflow test.
        for arch in ('x86_64', 'arm64'):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'CLIPOS_CODESIGN_IDENTITY': '', 'CLIPOS_NOTARY_PROFILE': ''}):
                folder = Path(td)
                app = folder/'CLIPOS.app'
                binary = app/'Contents'/'MacOS'/'CLIPOS'
                binary.parent.mkdir(parents=True)
                source = folder/'main.c'
                source.write_text('int main(void) { return 0; }\n')
                subprocess.run(['clang', '-arch', arch, str(source), '-o', str(binary)], check=True)
                mac.polish_app_bundle(app)
                self.assertTrue(mac.sign_app(app))
                # Reproduce the previous bug: changing a sealed plist.
                info = app/'Contents'/'Info.plist'
                data = plistlib.loads(info.read_bytes())
                data['CFBundleDisplayName'] = 'Mutation invalidates the seal'
                info.write_bytes(plistlib.dumps(data))
                with self.assertRaises(subprocess.CalledProcessError):
                    mac.verify_app_signature(app)
                mac.finalize_app_bundle(app)
                mac.verify_app_signature(app)
                dmg = mac.build_dmg(app, folder/'out', arch='intel' if arch == 'x86_64' else arch)
                self.assertTrue(dmg.is_file())


if __name__ == '__main__':
    unittest.main()


def test_bundle_resources_prefer_application_over_ocr_models(tmp_path):
    from scripts.verify_bundle import resource_root
    app=tmp_path/'CLIPOS.app'
    resources=app/'Contents'/'Resources'
    (resources/'rapidocr_onnxruntime'/'models').mkdir(parents=True)
    own=resources/'resources'
    for name in ('ffmpeg','cascades','models','icons','sounds'):(own/name).mkdir(parents=True)
    assert resource_root(app)==own
    # PyInstaller can move real resources under Frameworks and symlink them.
    import shutil
    shutil.rmtree(own)
    own=app/'Contents'/'Frameworks'/'resources'
    for name in ('ffmpeg','cascades','models','icons','sounds'):(own/name).mkdir(parents=True)
    assert resource_root(app)==own
