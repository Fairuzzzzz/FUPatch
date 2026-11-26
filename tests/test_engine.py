import hashlib
import os
import plistlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.common import (BASE186, FINAL, ORIG_BIN, RESULT_SHA, arm64_stub,
                          have, make_synthetic_ipa)
from mhfu_patch import engine, manifest

BASE = 0x100000000


@unittest.skipUnless(have(ORIG_BIN, FINAL), 'golden binary not available')
class BinaryStepsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = manifest.load_set()
        cls.orig = Path(ORIG_BIN).read_bytes()
        cls.final = Path(FINAL).read_bytes()

    def test_source_to_final(self):
        out, applied, skipped = engine.apply_steps(self.orig, self.m)
        self.assertEqual(hashlib.sha256(out).hexdigest(), RESULT_SHA)
        self.assertEqual(len(applied), 36)
        self.assertEqual(skipped, [])

    def test_final_is_noop(self):
        out, applied, skipped = engine.apply_steps(self.final, self.m)
        self.assertEqual(out, self.final)
        self.assertEqual(applied, [])
        self.assertEqual(len(skipped), 36)

    @unittest.skipUnless(have(BASE186), '1.00.186 binary not available')
    def test_base186(self):
        data = Path(BASE186).read_bytes()
        out, applied, skipped = engine.apply_steps(data, self.m)
        self.assertEqual(hashlib.sha256(out).hexdigest(), RESULT_SHA)
        self.assertEqual(len(applied), 4)
        self.assertEqual(len(skipped), 32)
        self.assertTrue(all(s.startswith('coating.') for s in applied), applied)

    def test_mismatch_raises(self):
        bad = bytearray(self.orig)
        step = self.m['binary_steps'][0]
        off = int(step['vaddr'], 0) - BASE
        bad[off] ^= 0xFF
        with self.assertRaises(engine.StepMismatch):
            engine.apply_steps(bytes(bad), self.m)

    def test_profiles(self):
        expected = {
            'iphone11-xr':
                '5e3b6912cedc7acc4ee148d1beb20b64b59388fdb9912df9c066ad62fd92b3e6',
            'iphone11-pro':
                'ba7c0ad048a6f92e2b6b3ec2bee88e404dc0bf3a6f528679c2f116599a16f659',
            'iphone12-14': RESULT_SHA,
            'iphone14pro-15':
                '3e552759d2f61a736effed3ce2180252ade40eaeb73cbe55b17e55c7a938fabc',
            'iphone14-15-promax':
                'd76bc28a0457befab44018afd2fb25ef82220e9a2774b0ce6f9b7a2d447dd815',
            'iphone16-17':
                '3e552759d2f61a736effed3ce2180252ade40eaeb73cbe55b17e55c7a938fabc',
        }
        for profile_id, sha in expected.items():
            profile = manifest.select_profile(self.m, profile_id)
            out, applied, skipped = engine.apply_steps(
                self.orig, self.m, profile=profile)
            self.assertEqual(hashlib.sha256(out).hexdigest(), sha,
                             profile_id)
            self.assertEqual(len(applied),
                             len(manifest.profile_steps(self.m, profile)))
            self.assertEqual(skipped, [])

    def test_iphone11_guard_and_constants(self):
        profile = manifest.select_profile(self.m, 'iphone11-xr')
        out, _applied, _skipped = engine.apply_steps(
            self.orig, self.m, profile=profile)
        def at(addr, size):
            off = addr - BASE
            return out[off:off + size].hex()
        self.assertEqual(at(0x10045f088, 4), '00b51fb4')
        self.assertEqual(at(0x10045f08c, 4), 'a5fd0014')
        self.assertEqual(at(0x10049e720, 16),
                         '001c40b9c0035fd600008052c0035fd6')
        self.assertEqual(at(0x10049e51c, 16),
                         '0000b0420000b0420000000000002842')
        self.assertEqual(at(0x1005c7848, 4), '0000803f')

    def test_result_sha_enforced(self):
        """apply_steps itself does not verify; engine.patch does."""
        out, _applied, _skipped = engine.apply_steps(self.orig, self.m)
        self.assertEqual(len(out), len(self.orig))


@unittest.skipUnless(have(ORIG_BIN), 'golden binary not available')
class LookAndPatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = open(ORIG_BIN, 'rb').read()
        self.ipa = make_synthetic_ipa(os.path.join(self.tmp.name, 'in.ipa'),
                                     self.orig)

    def tearDown(self):
        self.tmp.cleanup()

    def test_look_source(self):
        info = engine.look(self.ipa)
        self.assertTrue(info['supported'])
        self.assertEqual(info['match'], 'source')
        self.assertEqual(info['steps_pending'], 36)
        self.assertEqual(info['steps_applied'], 0)
        self.assertEqual(info['exe_kind'], 'thin')
        self.assertEqual(info['arm64_sha256'],
                         hashlib.sha256(self.orig).hexdigest())
        self.assertIn('Payload/MH Unite.app/LaunchImage.png',
                      info['remove_pending'])
        self.assertEqual(info['add_pending'],
                         ['Payload/MH Unite.app/LaunchScreen.storyboard'])

    def test_look_final(self):
        with open(FINAL, 'rb') as fh:
            ipa = make_synthetic_ipa(
                os.path.join(self.tmp.name, 'final.ipa'), fh.read())
        info = engine.look(ipa)
        self.assertTrue(info['supported'])
        self.assertEqual(info['match'], 'result')
        self.assertEqual(info['steps_pending'], 0)
        self.assertEqual(info['steps_applied'], 36)

    def test_look_unknown(self):
        ipa = make_synthetic_ipa(os.path.join(self.tmp.name, 'x.ipa'),
                                 arm64_stub())
        info = engine.look(ipa)
        self.assertFalse(info['supported'])
        self.assertIsNone(info['match'])

    def test_not_macho(self):
        ipa = make_synthetic_ipa(os.path.join(self.tmp.name, 'y.ipa'),
                                 b'not a binary')
        with self.assertRaises((engine.PatchError, ValueError)):
            engine.look(ipa)

    def test_dry_run_writes_nothing(self):
        out = os.path.join(self.tmp.name, 'out.ipa')
        report = engine.patch(self.ipa, out, dry_run=True)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(report['version'], '1.00.11')
        self.assertEqual(len(report['applied']), 36)
        self.assertEqual(report['members'], 4)

    def test_patch_output(self):
        out = os.path.join(self.tmp.name, 'out.ipa')
        report = engine.patch(self.ipa, out, version='1.00.195')
        self.assertTrue(os.path.exists(out))
        self.assertEqual(report['version'], '1.00.195')
        self.assertEqual(report['slice_sha256'], RESULT_SHA)
        self.assertEqual(len(report['removed']), 3)
        self.assertEqual(len(report['added']), 1)

        with zipfile.ZipFile(out) as zf:
            self.assertIsNone(zf.testzip())
            names = set(zf.namelist())
            self.assertIn('Payload/MH Unite.app/LaunchScreen.storyboard', names)
            self.assertNotIn('iTunesMetadata.plist', names)
            self.assertNotIn('Payload/MH Unite.app/LaunchImage.png', names)
            self.assertIn('Payload/MH Unite.app/data.bin', names)
            exe = zf.read('Payload/MH Unite.app/MH Unite')
            self.assertEqual(hashlib.sha256(exe).hexdigest(), RESULT_SHA)

    def test_look_profile(self):
        info = engine.look(self.ipa, profile_id='iphone11-xr')
        self.assertTrue(info['supported'])
        self.assertEqual(info['match'], 'source')
        self.assertEqual(info['profile'], 'iphone11-xr')
        self.assertEqual(info['profile_label'], 'iPhone 11 / XR')
        self.assertEqual(info['steps_total'], 39)
        self.assertEqual(info['steps_pending'], 39)
        self.assertEqual(info['steps_applied'], 0)
        self.assertEqual(
            info['profile_result_sha256'],
            '5e3b6912cedc7acc4ee148d1beb20b64b59388fdb9912df9c066ad62fd92b3e6')
        self.assertEqual([p['id'] for p in info['profiles']],
                         ['iphone11-xr', 'iphone11-pro', 'iphone12-14',
                          'iphone14pro-15', 'iphone14-15-promax',
                          'iphone16-17', 'ipad-air-m2'])

    def test_patch_profile(self):
        out = os.path.join(self.tmp.name, 'iphone11.ipa')
        report = engine.patch(self.ipa, out, profile='iphone11-xr')
        self.assertTrue(os.path.exists(out))
        self.assertEqual(report['profile'], 'iphone11-xr')
        self.assertEqual(
            report['slice_sha256'],
            '5e3b6912cedc7acc4ee148d1beb20b64b59388fdb9912df9c066ad62fd92b3e6')
        with zipfile.ZipFile(out) as zf:
            self.assertIsNone(zf.testzip())
            exe = zf.read('Payload/MH Unite.app/MH Unite')
            self.assertEqual(
                hashlib.sha256(exe).hexdigest(),
                '5e3b6912cedc7acc4ee148d1beb20b64b59388fdb9912df9c066ad62fd92b3e6')

    def test_look_profile_result(self):
        m = manifest.load_set()
        profile = manifest.select_profile(m, 'iphone11-xr')
        patched, _applied, _skipped = engine.apply_steps(
            self.orig, m, profile=profile)
        ipa = make_synthetic_ipa(
            os.path.join(self.tmp.name, 'iphone11-result.ipa'), patched)
        info = engine.look(ipa)
        self.assertTrue(info['supported'])
        self.assertEqual(info['match'], 'result')
        self.assertEqual(info['profile'], 'iphone11-xr')
        self.assertEqual(info['steps_total'], 39)
        self.assertEqual(info['steps_pending'], 0)
        self.assertEqual(info['steps_applied'], 39)

    def test_same_path_rejected(self):
        with self.assertRaises(engine.PatchError):
            engine.patch(self.ipa, self.ipa)

    def test_existing_output_rejected(self):
        out = os.path.join(self.tmp.name, 'out.ipa')
        Path(out).write_bytes(b'x')
        with self.assertRaises(engine.PatchError):
            engine.patch(self.ipa, out)
        engine.patch(self.ipa, out, force=True)

    def test_invalid_version(self):
        with self.assertRaises(engine.PatchError):
            engine.patch(self.ipa, os.path.join(self.tmp.name, 'o.ipa'),
                         version='1.00 beta')

    def test_patch_ipad_profile(self):
        out = os.path.join(self.tmp.name, 'ipad.ipa')

        report = engine.patch(
            self.ipa, out, profile='ipad-air-m2')

        expected_sha = (
            'ff26548f0e32f240e01c30e2e172bd00'
            '5087b43ea1a517527bc84668339be10e'
        )

        self.assertEqual(report['profile'], 'ipad-air-m2')
        self.assertEqual(report['slice_sha256'], expected_sha)

        with zipfile.ZipFile(out) as zf:
            self.assertIsNone(zf.testzip())

            info = plistlib.loads(
                zf.read('Payload/MH Unite.app/Info.plist'))

            exe = zf.read('Payload/MH Unite.app/MH Unite')

            self.assertEqual(info['UIDeviceFamily'], [1, 2])
            self.assertEqual(
                hashlib.sha256(exe).hexdigest(), expected_sha)

    def test_repair_ipad_plist_only(self):
        patched = os.path.join(self.tmp.name, 'ipad.ipa')
        broken = os.path.join(self.tmp.name, 'ipad-broken.ipa')
        repaired = os.path.join(self.tmp.name, 'ipad-repaired.ipa')

        engine.patch(
            self.ipa, patched, profile='ipad-air-m2')

        info_name = 'Payload/MH Unite.app/Info.plist'
        exe_name = 'Payload/MH Unite.app/MH Unite'

        # Create an otherwise patched IPA with incorrect device family.
        with zipfile.ZipFile(patched) as src:
            with zipfile.ZipFile(broken, 'w') as dst:
                for entry in src.infolist():
                    data = src.read(entry)

                    if entry.filename == info_name:
                        info = plistlib.loads(data)
                        info['UIDeviceFamily'] = [1]
                        data = plistlib.dumps(info)

                    dst.writestr(entry, data)

        report = engine.patch(
            broken, repaired, profile='ipad-air-m2')

        # No binary patches or member changes should be required.
        self.assertEqual(report['applied'], [])
        self.assertEqual(report['added'], [])
        self.assertEqual(report['removed'], [])

        with zipfile.ZipFile(patched) as original:
            with zipfile.ZipFile(repaired) as result:
                self.assertIsNone(result.testzip())
                self.assertEqual(
                    result.read(exe_name), original.read(exe_name))
                self.assertEqual(
                    plistlib.loads(result.read(info_name)),
                    plistlib.loads(original.read(info_name)))
                self.assertEqual(
                    set(result.namelist()),
                    set(original.namelist()))

        # A fully repaired IPA must trigger the no-change guard.
        with self.assertRaises(engine.PatchError):
            engine.patch(
                repaired,
                os.path.join(self.tmp.name, 'redundant.ipa'),
                profile='ipad-air-m2')

    def test_no_change_guard(self):
        with open(FINAL, 'rb') as fh:
            final_ipa = make_synthetic_ipa(
                os.path.join(self.tmp.name, 'final.ipa'), fh.read())
        once = os.path.join(self.tmp.name, 'once.ipa')
        engine.patch(final_ipa, once, version='1.00.197')
        with self.assertRaises(engine.PatchError):
            engine.patch(once, os.path.join(self.tmp.name, 'z.ipa'),
                         version='1.00.197')


if __name__ == '__main__':
    unittest.main()
