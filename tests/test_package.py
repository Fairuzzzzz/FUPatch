import plistlib
import unittest

from tests.common import ROOT, make_synthetic_ipa
from mhfu_patch import manifest, package


class PackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = manifest.load_set()

    def test_remove_exact_and_glob(self):
        names = [
            'Payload/MH Unite.app/LaunchImage.png',
            'Payload/MH Unite.app/LaunchImage-568h@2x.png',
            'Payload/MH Unite.app/_CodeSignature/',
            'Payload/MH Unite.app/_CodeSignature/CodeResources',
            '.ZipComment',
            'iTunesArtwork',
            'iTunesMetadata.plist',
            'Payload/MH Unite.app/Info.plist',
            'Payload/MH Unite.app/MH Unite',
            'Payload/MH Unite.app/Data.bin',
        ]
        got = package.resolve_removals(self.m['members_remove'], names)
        self.assertIn('Payload/MH Unite.app/LaunchImage.png', got)
        self.assertIn('Payload/MH Unite.app/_CodeSignature/CodeResources', got)
        self.assertIn('.ZipComment', got)
        self.assertIn('iTunesMetadata.plist', got)
        self.assertNotIn('Payload/MH Unite.app/Info.plist', got)
        self.assertNotIn('Payload/MH Unite.app/MH Unite', got)
        self.assertNotIn('Payload/MH Unite.app/Data.bin', got)

    def test_remove_is_idempotent(self):
        self.assertEqual(package.resolve_removals(self.m['members_remove'], []), set())

    def test_additions_skip_existing(self):
        present = {self.m['members_add'][0]['name']}
        self.assertEqual(package.resolve_additions(self.m['members_add'], present,
                                                   ROOT), [])
        added = package.resolve_additions(self.m['members_add'], set(), ROOT)
        self.assertEqual(len(added), 1)
        self.assertTrue(added[0][1].startswith(b'<?xml'))

    def test_info_plist(self):
        raw = plistlib.dumps({
            'CFBundleExecutable': 'MH Unite',
            'CFBundleIdentifier': 'x.y',
            'CFBundleShortVersionString': '1.00.11',
            'CFBundleVersion': '1.00.11',
            'UILaunchImageFile': 'LaunchImage',
            'UIDeviceFamily': [1, 2],
            'Extra': 'tetap',
        }, fmt=plistlib.FMT_BINARY)
        out = plistlib.loads(package.patch_info_plist(
            raw, self.m, '1.00.200', marker_suffix='2026-10-22'))
        self.assertEqual(out['CFBundleShortVersionString'], '1.00.200')
        self.assertEqual(out['CFBundleVersion'], '1.00.200')
        self.assertEqual(out['UIDeviceFamily'], [1])
        self.assertEqual(out['UILaunchStoryboardName'], 'LaunchScreen')
        self.assertIs(out['UIFileSharingEnabled'], True)
        self.assertIs(out['LSSupportsOpeningDocumentsInPlace'], True)
        self.assertNotIn('UILaunchImageFile', out)
        self.assertEqual(out['Extra'], 'tetap')
        self.assertEqual(out['MHFUPatch'], self.m['id'] + ' 2026-10-22')

    def test_info_plist_deterministic(self):
        raw = plistlib.dumps({'CFBundleVersion': '1.00.11'},
                             fmt=plistlib.FMT_BINARY)
        a = package.patch_info_plist(raw, self.m, '1.00.200')
        b = package.patch_info_plist(raw, self.m, '1.00.200')
        self.assertEqual(a, b)

    def test_synthetic_ipa_helper(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = make_synthetic_ipa(tmp + '/x.ipa', b'\xcf\xfa\xed\xfe' + b'\0' * 60)
            self.assertTrue(path)

    def test_missing_fixture(self):
        spec = [{'name': 'Payload/X.app/bar.txt', 'source': 'assets/missing.txt'}]
        with self.assertRaises(package.PackageError):
            package.resolve_additions(spec, set(), '/tmp')


if __name__ == '__main__':
    unittest.main()
