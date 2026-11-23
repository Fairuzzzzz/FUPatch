import io
import os
import struct
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


def build_zip_with_local_extra_mismatch(path):
    central_extra = (
        b'\x55\x54\x05\x00\x03' + struct.pack('<I', 123456789)
        + b'\x55\x78\x00\x00'
    )
    local_extra = (
        b'\x55\x54\x09\x00\x03' + struct.pack('<II', 123456789, 987654321)
        + b'\x55\x78\x04\x00' + struct.pack('<HH', 1000, 1000)
    )
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo('payload.bin')
        info.compress_type = zipfile.ZIP_DEFLATED
        info.extra = central_extra
        zf.writestr(info, b'archive payload' * 100)

    with open(path, 'rb') as fh:
        data = bytearray(fh.read())
    name_len, old_extra_len = struct.unpack_from('<HH', data, 26)
    extra_off = 30 + name_len
    data_off = extra_off + old_extra_len
    struct.pack_into('<H', data, 28, len(local_extra))
    data = data[:extra_off] + local_extra + data[data_off:]
    eocd = data.rfind(ziprewrite.EOCD_SIG)
    cd_off = struct.unpack_from('<I', data, eocd + 16)[0]
    struct.pack_into('<I', data, eocd + 16, cd_off + len(local_extra) - old_extra_len)
    with open(path, 'wb') as fh:
        fh.write(data)


def local_extra(path, entry):
    with open(path, 'rb') as fh:
        fh.seek(entry['off'])
        header = fh.read(30)
        name_len, extra_len = struct.unpack('<HH', header[26:30])
        fh.seek(name_len, os.SEEK_CUR)
        return fh.read(extra_len)


def central_directory_offset(data):
    eocd = data.rfind(ziprewrite.EOCD_SIG)
    return struct.unpack_from('<I', data, eocd + 16)[0]


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

    def test_normalize_local_extras_to_central_directory(self):
        source = os.path.join(self.tmp.name, 'mismatch.ipa')
        output = os.path.join(self.tmp.name, 'normalized.ipa')
        build_zip_with_local_extra_mismatch(source)
        source_index = ziprewrite.read_index(source)
        source_entry = source_index['entries'][0]
        self.assertNotEqual(local_extra(source, source_entry),
                            source_entry['extra'])

        ziprewrite.rewrite(source, output, normalize_local_extras=True)

        output_index = ziprewrite.read_index(output)
        output_entry = output_index['entries'][0]
        self.assertEqual(local_extra(output, output_entry),
                         output_entry['extra'])
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
            self.assertIsNone(after.testzip())
            self.assertEqual(before.read('payload.bin'),
                             after.read('payload.bin'))

    def test_default_rewrite_preserves_mismatched_local_extra(self):
        source = os.path.join(self.tmp.name, 'mismatch-default.ipa')
        output = os.path.join(self.tmp.name, 'preserved.ipa')
        build_zip_with_local_extra_mismatch(source)
        before_index = ziprewrite.read_index(source)
        before_entry = before_index['entries'][0]
        before_extra = local_extra(source, before_entry)

        ziprewrite.rewrite(source, output)

        after_index = ziprewrite.read_index(output)
        after_entry = after_index['entries'][0]
        self.assertEqual(local_extra(output, after_entry), before_extra)
        self.assertNotEqual(local_extra(output, after_entry),
                            after_entry['extra'])
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
            self.assertIsNone(after.testzip())
            self.assertEqual(before.read('payload.bin'),
                             after.read('payload.bin'))

    def test_rejects_zip64_eocd_sentinel(self):
        broken = os.path.join(self.tmp.name, 'zip64-eocd.ipa')
        with open(self.src, 'rb') as fh:
            data = bytearray(fh.read())
        eocd = data.rfind(ziprewrite.EOCD_SIG)
        struct.pack_into('<I', data, eocd + 16, 0xFFFFFFFF)
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'ZIP64'):
            ziprewrite.read_index(broken)

    def test_rejects_zip64_locator(self):
        broken = os.path.join(self.tmp.name, 'zip64-locator.ipa')
        with open(self.src, 'rb') as fh:
            data = bytearray(fh.read())
        eocd = data.rfind(ziprewrite.EOCD_SIG)
        locator = struct.pack('<IIQI', 0x07064B50, 0, 0, 1)
        data[eocd:eocd] = locator
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'ZIP64'):
            ziprewrite.read_index(broken)

    def test_rejects_zip64_entry_sentinel(self):
        broken = os.path.join(self.tmp.name, 'zip64-entry.ipa')
        with open(self.src, 'rb') as fh:
            data = bytearray(fh.read())
        cd_offset = central_directory_offset(data)
        struct.pack_into('<I', data, cd_offset + 20, 0xFFFFFFFF)
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'ZIP64'):
            ziprewrite.read_index(broken)

    def test_rejects_zip64_extra_field(self):
        source = os.path.join(self.tmp.name, 'zip64-extra-source.ipa')
        broken = os.path.join(self.tmp.name, 'zip64-extra.ipa')
        build_zip_with_local_extra_mismatch(source)
        with open(source, 'rb') as fh:
            data = bytearray(fh.read())
        cd_offset = central_directory_offset(data)
        name_length = struct.unpack_from('<H', data, cd_offset + 28)[0]
        struct.pack_into('<H', data, cd_offset + 46 + name_length, 0x0001)
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'ZIP64'):
            ziprewrite.read_index(broken)

    def test_rejects_truncated_central_metadata(self):
        broken = os.path.join(self.tmp.name, 'truncated-central.ipa')
        with open(self.src, 'rb') as fh:
            data = bytearray(fh.read())
        cd_offset = central_directory_offset(data)
        struct.pack_into('<H', data, cd_offset + 30, 0xFFFF)
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'truncated'):
            ziprewrite.read_index(broken)

    def test_rejects_malformed_central_extra_field(self):
        source = os.path.join(self.tmp.name, 'malformed-central-source.ipa')
        broken = os.path.join(self.tmp.name, 'malformed-central.ipa')
        build_zip_with_local_extra_mismatch(source)
        with open(source, 'rb') as fh:
            data = bytearray(fh.read())
        cd_offset = central_directory_offset(data)
        name_length = struct.unpack_from('<H', data, cd_offset + 28)[0]
        extra_offset = cd_offset + 46 + name_length
        struct.pack_into('<H', data, extra_offset + 2, 0xFFFF)
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'extra-field'):
            ziprewrite.read_index(broken)

    def test_rejects_truncated_local_header(self):
        broken = os.path.join(self.tmp.name, 'truncated-local-header.ipa')
        with open(self.src, 'rb') as fh:
            data = bytearray(fh.read())
        cd_offset = central_directory_offset(data)
        struct.pack_into('<I', data, cd_offset + 42, cd_offset - 10)
        with open(broken, 'wb') as fh:
            fh.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'truncated local header'):
            ziprewrite.rewrite(broken, self.dst)

    def test_rejects_truncated_local_extra(self):
        source = os.path.join(self.tmp.name, 'truncated-local-extra.ipa')
        build_zip_with_local_extra_mismatch(source)
        with open(source, 'r+b') as fh:
            fh.seek(28)
            fh.write(struct.pack('<H', 0xFFFF))

        with self.assertRaisesRegex(ziprewrite.ZipError, 'truncated local extra'):
            ziprewrite.rewrite(source, self.dst, normalize_local_extras=True)

    def test_rejects_malformed_local_extra_field(self):
        source = os.path.join(self.tmp.name, 'malformed-local-extra.ipa')
        build_zip_with_local_extra_mismatch(source)
        with open(source, 'r+b') as fh:
            fh.seek(26)
            name_length, _extra_length = struct.unpack('<HH', fh.read(4))
            fh.seek(30 + name_length + 2)
            fh.write(struct.pack('<H', 0xFFFF))

        with self.assertRaisesRegex(ziprewrite.ZipError, 'extra-field'):
            ziprewrite.rewrite(source, self.dst)

    def test_rejects_mismatched_local_filename(self):
        broken = os.path.join(self.tmp.name, 'mismatched-name.ipa')
        with open(self.src, 'rb') as source, open(broken, 'wb') as output:
            data = bytearray(source.read())
            data[30] ^= 1
            output.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'filename mismatch'):
            ziprewrite.rewrite(broken, self.dst)

    def test_rejects_bad_local_header_signature(self):
        broken = os.path.join(self.tmp.name, 'bad-local-header.ipa')
        with open(self.src, 'rb') as source, open(broken, 'wb') as output:
            data = bytearray(source.read())
            data[0:4] = b'BAD!'
            output.write(data)

        with self.assertRaisesRegex(ziprewrite.ZipError, 'local header'):
            ziprewrite.rewrite(broken, self.dst)


if __name__ == '__main__':
    unittest.main()
