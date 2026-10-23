import io
import os
import tempfile
import unittest
import zipfile

from mhfu_patch import ziprewrite


def build_zip(path):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('a.txt', b'alpha' * 100)
        zf.writestr('keep/b.bin', os.urandom(4096))
        zf.writestr('drop.txt', b'buang aku')
        zf.writestr('Payload/X.app/data.bin', b'data' * 300)


class ZipRewriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, 'in.ipa')
        self.dst = os.path.join(self.tmp.name, 'out.ipa')
        build_zip(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rewrite(self):
        calls = []

        def progress(done, total, wb, tb):
            calls.append((done, total))

        res = ziprewrite.rewrite(
            self.src, self.dst,
            replacements={'a.txt': b'ALPHA-NEW' * 50},
            removals={'drop.txt', 'Payload/X.app/data.bin'},
            additions=[('new/hello.txt', 'hello world'.encode())],
            progress=progress)

        self.assertEqual(res['members'], 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][0], calls[-1][1])

        with zipfile.ZipFile(self.dst) as zf:
            self.assertIsNone(zf.testzip())
            names = set(zf.namelist())
            self.assertEqual(names, {'a.txt', 'keep/b.bin', 'new/hello.txt'})
            self.assertEqual(zf.read('a.txt'), b'ALPHA-NEW' * 50)
            self.assertEqual(zf.read('new/hello.txt'), 'hello world'.encode())

        with zipfile.ZipFile(self.src) as zf:
            original_keep = zf.read('keep/b.bin')
        with zipfile.ZipFile(self.dst) as zf:
            self.assertEqual(zf.read('keep/b.bin'), original_keep)

    def test_deterministic(self):
        kwargs = dict(replacements={'a.txt': b'x' * 10},
                      removals={'drop.txt'},
                      additions=[('z.txt', b'zz')])
        ziprewrite.rewrite(self.src, self.dst, **kwargs)
        with open(self.dst, 'rb') as fh:
            first = fh.read()
        os.remove(self.dst)
        ziprewrite.rewrite(self.src, self.dst, **kwargs)
        with open(self.dst, 'rb') as fh:
            self.assertEqual(first, fh.read())

    def test_add_duplicate_rejected(self):
        with self.assertRaises(ziprewrite.ZipError):
            ziprewrite.rewrite(self.src, self.dst,
                               additions=[('a.txt', b'duplikat')])

    def test_progress_cancel(self):
        class Stop(Exception):
            pass

        def progress(done, total, wb, tb):
            raise Stop()

        with self.assertRaises(Stop):
            ziprewrite.rewrite(self.src, self.dst, progress=progress)
        self.assertTrue(os.path.exists(self.dst))       # the caller removes it

    def test_read_member(self):
        self.assertEqual(ziprewrite.read_member(self.src, 'drop.txt'), b'buang aku')
        with self.assertRaises(ziprewrite.ZipError):
            ziprewrite.read_member(self.src, 'missing')

    def test_names(self):
        idx = ziprewrite.read_index(self.src)
        self.assertIn('a.txt', ziprewrite.names(idx))
        self.assertEqual(idx['size'], os.path.getsize(self.src))


if __name__ == '__main__':
    unittest.main()
