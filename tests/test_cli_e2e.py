import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tests.common import (ORIGINAL_IPA, PATCHED_IPA, RESULT_SHA, ROOT, have,
                          member_map)


def file_sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


@unittest.skipUnless(os.environ.get('MHFU_E2E') == '1',
                     'tes lambat: set MHFU_E2E=1')
@unittest.skipUnless(have(ORIGINAL_IPA, PATCHED_IPA),
                     'original / reference IPA not available')
class CliE2ETest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'mhfu_patch', *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=300)

    def test_inspect_json(self):
        cp = self.run_cli('inspect', '--ipa', ORIGINAL_IPA, '--json')
        self.assertEqual(cp.returncode, 0, cp.stderr)
        info = json.loads(cp.stdout)
        self.assertTrue(info['supported'])
        self.assertEqual(info['steps_pending'], 36)
        self.assertEqual(info['match'], 'source')
        self.assertEqual(info['app_name'], 'MH Unite')

    def test_full_patch_matches_reference(self):
        before = file_sha(ORIGINAL_IPA)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'out.ipa')
            cp = self.run_cli('patch', '--ipa', ORIGINAL_IPA, '--out', out)
            self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
            self.assertTrue(os.path.exists(out))

            ref = member_map(PATCHED_IPA)
            got = member_map(out)
            self.assertEqual(set(got), set(ref))
            diff = [n for n in got if got[n][0] != ref[n][0]]
            self.assertEqual(diff, ['Payload/MH Unite.app/Info.plist'])

            with zipfile.ZipFile(out) as zf:
                self.assertIsNone(zf.testzip())
                exe = zf.read('Payload/MH Unite.app/MH Unite')
                self.assertEqual(hashlib.sha256(exe).hexdigest(), RESULT_SHA)
                pl = plistlib.loads(zf.read('Payload/MH Unite.app/Info.plist'))
                self.assertEqual(pl['CFBundleShortVersionString'], '1.00.11')
                self.assertIn('MHFUPatch', pl)
        self.assertEqual(before, file_sha(ORIGINAL_IPA),
                         'IPA sumber berubah!')


if __name__ == '__main__':
    unittest.main()
