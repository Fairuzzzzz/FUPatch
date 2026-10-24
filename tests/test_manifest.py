import unittest

from tests.common import RESULT_SHA
from mhfu_patch import manifest


class ManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = manifest.load_set()

    def test_valid(self):
        manifest.validate(self.m)

    def test_step_count_and_bytes(self):
        steps = self.m['binary_steps']
        self.assertEqual(len(steps), 36)
        self.assertEqual(sum(len(s['replace']) // 2 for s in steps), 1008)

    def test_result_sha(self):
        self.assertEqual(self.m['slice']['result_sha256'], RESULT_SHA)

    def test_step_ids_unique(self):
        ids = [s['id'] for s in self.m['binary_steps']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_features_defined(self):
        known = {f['id'] for f in self.m['features']}
        used = {s['feature'] for s in self.m['binary_steps']}
        self.assertTrue(used <= known, used - known)

    def test_package_delta(self):
        self.assertEqual(len(self.m['members_remove']['exact']), 11)
        self.assertEqual(len(self.m['members_add']), 1)
        self.assertTrue(self.m['members_add'][0]['name']
                        .endswith('LaunchScreen.storyboard'))

    def test_info_changes(self):
        changes = self.m['info_changes']
        self.assertEqual(changes['remove'], ['UILaunchImageFile'])
        self.assertEqual(changes['set']['UIDeviceFamily'], [1])
        self.assertEqual(changes['set']['UILaunchStoryboardName'], 'LaunchScreen')
        self.assertIn('NSBluetoothAlwaysUsageDescription', changes['set'])
        self.assertIs(changes['set']['UIFileSharingEnabled'], True)
        self.assertIs(changes['set']['LSSupportsOpeningDocumentsInPlace'], True)

    def test_classify(self):
        self.assertEqual(manifest.classify(self.m, RESULT_SHA), 'result')
        src = self.m['slice']['source_sha256'][0]
        self.assertEqual(manifest.classify(self.m, src), 'source')
        self.assertIsNone(manifest.classify(self.m, '00' * 32))

    def test_step_ids_and_ranges_disjoint(self):
        base = int(self.m['slice']['vaddr_base'], 0)
        spans = []
        for step in self.m['binary_steps']:
            start = int(step['vaddr'], 0) - base
            spans.append((start, start + len(step['expect']) // 2))
        spans.sort()
        for (a0, a1), (b0, _b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0)

    def test_unknown_set(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.load_set('missing-set')


if __name__ == '__main__':
    unittest.main()
