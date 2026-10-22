import hashlib
import os
import tempfile
import unittest
import zipfile

from tests.common import (BASE186, FINAL, ORIG_BIN, RESULT_SHA, arm64_stub,
                          have, make_synthetic_ipa)
from mhfu_patch import engine, manifest

BASE = 0x100000000


@unittest.skipUnless(have(ORIG_BIN, FINAL), 'biner golden tidak tersedia')
class BinaryStepsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = manifest.load_set()
        cls.orig = open(ORIG_BIN, 'rb').read()
        cls.final = open(FINAL, 'rb').read()

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

    @unittest.skipUnless(have(BASE186), 'biner 186 tidak tersedia')
    def test_base186(self):
        data = open(BASE186, 'rb').read()
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

    def test_result_sha_enforced(self):
        """apply_steps sendiri tidak memverifikasi; engine.patch yang melakukannya."""
        out, _applied, _skipped = engine.apply_steps(self.orig, self.m)
        self.assertEqual(len(out), len(self.orig))


@unittest.skipUnless(have(ORIG_BIN), 'biner golden tidak tersedia')
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
                                 b'bukan biner')
        with self.assertRaises((engine.PatchError, ValueError)):
            engine.look(ipa)

    def test_dry_run_writes_nothing(self):
        out = os.path.join(self.tmp.name, 'out.ipa')
        report = engine.patch(self.ipa, out, dry_run=True)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(report['version'], '1.00.194')
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

    def test_same_path_rejected(self):
        with self.assertRaises(engine.PatchError):
            engine.patch(self.ipa, self.ipa)

    def test_existing_output_rejected(self):
        out = os.path.join(self.tmp.name, 'out.ipa')
        open(out, 'wb').write(b'x')
        with self.assertRaises(engine.PatchError):
            engine.patch(self.ipa, out)
        engine.patch(self.ipa, out, force=True)

    def test_invalid_version(self):
        with self.assertRaises(engine.PatchError):
            engine.patch(self.ipa, os.path.join(self.tmp.name, 'o.ipa'),
                         version='1.00 beta')

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
