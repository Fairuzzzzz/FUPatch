import hashlib
import os
import plistlib
import tempfile
import unittest
import zipfile
from unittest import mock

from mhfu_patch import engine
from tools import enable_ipad_family


class EnableIpadFamilyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, 'iphone.ipa')
        self.dst = os.path.join(self.tmp.name, 'ipad-experiment.ipa')
        self.exe = b'verified synthetic executable'
        self.profile_id = 'iphone12-14'
        with zipfile.ZipFile(self.src, 'w', zipfile.ZIP_DEFLATED) as zf:
            plist = {
                'CFBundleExecutable': 'MH Unite',
                'CFBundleIdentifier': 'test.mhfu.local',
                'CFBundleShortVersionString': '1.00.11',
                'UIDeviceFamily': [1],
                'KeepThisKey': 'unchanged',
            }
            zf.writestr(
                'Payload/MH Unite.app/Info.plist',
                plistlib.dumps(plist, fmt=plistlib.FMT_BINARY, sort_keys=True))
            zf.writestr('Payload/MH Unite.app/MH Unite', self.exe)
            zf.writestr('Payload/MH Unite.app/data.bin', b'keep me')
        self.executable_sha = hashlib.sha256(self.exe).hexdigest()
        self.profile_sha_patcher = mock.patch.object(
            enable_ipad_family.manifest, 'profile_result_sha',
            return_value=self.executable_sha)
        self.profile_sha_patcher.start()
        self.addCleanup(self.profile_sha_patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def _verified_info(self, _ipa_path, profile_id=None, **_kwargs):
        self.assertEqual(profile_id, self.profile_id)
        return {
            'supported': True,
            'match': 'result',
            'profile': profile_id,
            'arm64_sha256': self.executable_sha,
            'profile_result_sha256': self.executable_sha,
        }

    @mock.patch.object(engine, 'look')
    def test_changes_only_device_family_and_preserves_executable(self, look):
        look.side_effect = self._verified_info
        report = enable_ipad_family.create_experiment(self.src, self.dst)

        self.assertEqual(look.call_count, 2)
        self.assertEqual(report['uid_device_family_before'], [1])
        self.assertEqual(report['uid_device_family_after'], [1, 2])
        self.assertEqual(report['executable_sha256_before'], self.executable_sha)
        self.assertEqual(report['executable_sha256_after'], self.executable_sha)
        self.assertEqual(
            report['archive_differences']['content_changed_members'],
            ['Payload/MH Unite.app/Info.plist'])
        self.assertEqual(report['archive_differences']['added_members'], [])
        self.assertEqual(report['archive_differences']['removed_members'], [])

        with zipfile.ZipFile(self.src) as before, zipfile.ZipFile(self.dst) as after:
            executable = 'Payload/MH Unite.app/MH Unite'
            self.assertEqual(before.read(executable), after.read(executable))
            original = plistlib.loads(
                before.read('Payload/MH Unite.app/Info.plist'))
            modified = plistlib.loads(
                after.read('Payload/MH Unite.app/Info.plist'))
            self.assertEqual(original['UIDeviceFamily'], [1])
            self.assertEqual(modified['UIDeviceFamily'], [1, 2])
            original.pop('UIDeviceFamily')
            modified.pop('UIDeviceFamily')
            self.assertEqual(original, modified)

    @mock.patch.object(engine, 'look')
    def test_experimental_profile_can_be_packaged_for_native_ipad(self, look):
        self.profile_id = 'ipad-air-m2-loading31-test'
        look.side_effect = self._verified_info
        report = enable_ipad_family.create_experiment(
            self.src, self.dst, profile_id=self.profile_id)
        self.assertEqual(report['profile'], self.profile_id)
        self.assertEqual(report['uid_device_family_after'], [1, 2])
        self.assertEqual(report['executable_sha256_before'], self.executable_sha)
        self.assertEqual(report['executable_sha256_after'], self.executable_sha)

    @mock.patch.object(engine, 'look')
    def test_rejects_unverified_binary(self, look):
        look.return_value = {
            'supported': False,
            'match': None,
            'profile': None,
            'arm64_sha256': '00' * 32,
            'profile_result_sha256': self.executable_sha,
        }
        with self.assertRaises(enable_ipad_family.ExperimentError):
            enable_ipad_family.create_experiment(self.src, self.dst)
        self.assertFalse(os.path.exists(self.dst))

    @mock.patch.object(engine, 'look')
    def test_rejects_wrong_input_family(self, look):
        look.side_effect = self._verified_info
        wrong_src = os.path.join(self.tmp.name, 'wrong-family.ipa')
        info_name = 'Payload/MH Unite.app/Info.plist'
        with zipfile.ZipFile(self.src) as source, \
                zipfile.ZipFile(wrong_src, 'w', zipfile.ZIP_DEFLATED) as output:
            for name in source.namelist():
                data = source.read(name)
                if name == info_name:
                    plist = plistlib.loads(data)
                    plist['UIDeviceFamily'] = [1, 2]
                    data = plistlib.dumps(
                        plist, fmt=plistlib.FMT_BINARY, sort_keys=True)
                output.writestr(name, data)
        with self.assertRaises(enable_ipad_family.ExperimentError):
            enable_ipad_family.create_experiment(wrong_src, self.dst)

    @mock.patch.object(engine, 'look')
    def test_never_overwrites_input_or_existing_output(self, look):
        look.side_effect = self._verified_info
        with self.assertRaises(enable_ipad_family.ExperimentError):
            enable_ipad_family.create_experiment(self.src, self.src)
        with open(self.dst, 'wb') as fh:
            fh.write(b'keep')
        with self.assertRaises(enable_ipad_family.ExperimentError):
            enable_ipad_family.create_experiment(self.src, self.dst)
        with open(self.dst, 'rb') as fh:
            self.assertEqual(fh.read(), b'keep')


if __name__ == '__main__':
    unittest.main()
