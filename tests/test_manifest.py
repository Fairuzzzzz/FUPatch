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

    def test_profiles(self):
        profiles = self.m['profiles']
        self.assertEqual([p['id'] for p in profiles], [
            'iphone11-xr', 'iphone11-pro', 'iphone12-14',
            'iphone14pro-15', 'iphone14-15-promax', 'iphone16-17',
        ])
        self.assertEqual(len({p['id'] for p in profiles}), len(profiles))
        default = manifest.default_profile(self.m)
        self.assertEqual(default['id'], 'iphone12-14')
        self.assertEqual(default['result_sha256'], RESULT_SHA)
        self.assertEqual(default['steps'], [])
        self.assertEqual(manifest.profile_result_sha(self.m), RESULT_SHA)
        self.assertEqual(
            manifest.profile_result_sha(self.m, 'iphone11-xr'),
            '5e3b6912cedc7acc4ee148d1beb20b64b59388fdb9912df9c066ad62fd92b3e6')
        self.assertEqual(len(manifest.profile_steps(self.m, 'iphone11-xr')),
                         39)
        self.assertEqual(len(manifest.profile_steps(self.m, 'iphone12-14')),
                         36)
        self.assertIsNone(manifest.find_profile_for_sha(self.m, '00' * 32))
        self.assertEqual(
            manifest.find_profile_for_sha(
                self.m,
                '5e3b6912cedc7acc4ee148d1beb20b64b59388fdb9912df9c066ad62fd92b3e6'
            )['id'],
            'iphone11-xr')

    def test_profile_results_are_known(self):
        results = manifest.sha_sets(self.m)['result']
        self.assertIn(RESULT_SHA, results)
        for profile in self.m['profiles']:
            self.assertIn(profile['result_sha256'], results)
        self.assertEqual(len(results), len(set(results)))

    def test_profile_unknown(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.select_profile(self.m, 'missing-profile')

    def test_profile_steps_do_not_overlap_each_other(self):
        base = int(self.m['slice']['vaddr_base'], 0)
        for profile in self.m['profiles']:
            spans = []
            for step in profile['steps']:
                start = int(step['vaddr'], 0) - base
                spans.append((start, start + len(step['expect']) // 2))
            spans.sort()
            for (a0, a1), (b0, _b1) in zip(spans, spans[1:]):
                self.assertLessEqual(a1, b0)

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
