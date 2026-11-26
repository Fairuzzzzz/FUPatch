import unittest

from tests.common import RESULT_SHA
from mhfu_patch import manifest
from copy import deepcopy


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
            'ipad-air-m2',
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
        ipad = manifest.select_profile(self.m, 'ipad-air-m2')

        self.assertFalse(ipad.get('default', False))
        self.assertEqual(ipad['label'], 'iPad Air 11-inch')
        common = next(s for s in self.m['binary_steps'] if s['id'] == 'safe-area.34')
        expected = bytearray.fromhex(common['replace'])
        self.assertEqual(len(expected), 456)
        self.assertEqual(expected[0x174:0x178].hex(), '7302090b')
        expected[0x177] = 0x4b
        self.assertEqual(ipad['overrides'], [{'id': common['id'], 'replace': expected.hex()}])
        self.assertEqual(sum(len(bytes.fromhex(s['replace'])) for s in ipad['steps']), 368)
        self.assertEqual(len(ipad['steps']), 5)

        self.assertEqual(
            ipad['result_sha256'],
            'ff26548f0e32f240e01c30e2e172bd005087b43ea1a517527bc84668339be10e'
        )

        self.assertEqual(
            len(manifest.profile_steps(self.m, 'ipad-air-m2')),
            41
        )

        self.assertEqual(
            manifest.find_profile_for_sha(
                self.m, ipad['result_sha256']
            )['id'],
            'ipad-air-m2'
        )

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

    def test_invalid_profile_info_changes(self):
        invalid_changes = [
            [],
            'invalid',
            {'unknown': True},
            {'set': []},
            {'set': {'': True}},
            {'set': {123: True}},
            {'remove': 'UIDeviceFamily'},
            {'remove': ['']},
            {'remove': [123]},
            {'remove': ['UIDeviceFamily', 'UIDeviceFamily']},
            {
                'set': {'UIDeviceFamily': [1, 2]},
                'remove': ['UIDeviceFamily'],
            },
        ]

        for changes in invalid_changes:
            with self.subTest(changes=changes):
                m = deepcopy(self.m)
                profile = manifest.select_profile(
                    m, 'ipad-air-m2')
                profile['info_changes'] = changes

                with self.assertRaises(manifest.ManifestError):
                    manifest.validate(m)

    def test_default_profile_info_changes_rejected(self):
        m = deepcopy(self.m)

        profile = manifest.default_profile(m)
        profile['info_changes'] = {
            'set': {'UIDeviceFamily': [1, 2]},
        }

        with self.assertRaises(manifest.ManifestError):
            manifest.validate(m)

    def test_invalid_base_info_changes(self):
        invalid_changes = [
            {'set': []},
            {'remove': 'UILaunchImageFile'},
            {'remove': ['UILaunchImageFile', 'UILaunchImageFile']},
            {
                'set': {'UIDeviceFamily': [1]},
                'remove': ['UIDeviceFamily'],
            },
        ]

        for changes in invalid_changes:
            with self.subTest(changes=changes):
                m = deepcopy(self.m)
                m['info_changes'] = changes

                with self.assertRaises(manifest.ManifestError):
                    manifest.validate(m)

    def test_unknown_set(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.load_set('missing-set')

    def test_ipad_profile_info_changes(self):
        from mhfu_patch.manifest import load_set, profile_info_changes

        m = load_set()
        changes = profile_info_changes(m, 'ipad-air-m2')

        self.assertEqual(changes['set']['UIDeviceFamily'], [1, 2])


    def test_existing_profiles_info_changes(self):
        from mhfu_patch.manifest import load_set, profile_info_changes

        m = load_set()

        for profile in m['profiles']:
            if profile['id'] == 'ipad-air-m2':
                continue

            with self.subTest(profile=profile['id']):
                self.assertEqual(
                    profile_info_changes(m, profile),
                    m['info_changes'],
                )


    def test_ipad_preserves_common_info_changes(self):
        from mhfu_patch.manifest import load_set, profile_info_changes

        m = load_set()
        expected = dict(m['info_changes']['set'])
        expected['UIDeviceFamily'] = [1, 2]

        changes = profile_info_changes(m, 'ipad-air-m2')

        self.assertEqual(changes['set'], expected)
        self.assertEqual(
            changes['remove'],
            m['info_changes']['remove'],
        )


    def test_profile_info_changes_merge(self):
        from mhfu_patch.manifest import profile_info_changes

        m = {
            'info_changes': {
                'set': {'A': 1, 'B': 2},
                'remove': ['C', 'D'],
            },
        }

        profile = {
            'info_changes': {
                'set': {'A': 10, 'C': 30},
                'remove': ['B', 'E'],
            },
        }

        changes = profile_info_changes(m, profile)

        self.assertEqual(changes['set'], {'A': 10, 'C': 30})
        self.assertEqual(set(changes['remove']), {'B', 'D', 'E'})
        self.assertEqual(m['info_changes']['set'], {'A': 1, 'B': 2})
        self.assertEqual(m['info_changes']['remove'], ['C', 'D'])


if __name__ == '__main__':
    unittest.main()
