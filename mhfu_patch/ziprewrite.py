"""Rewrite an IPA: copy members as-is, replace/remove/add as needed."""
import os
import struct
import zlib

LH_SIG = b'PK\x03\x04'
CD_SIG = b'PK\x01\x02'
EOCD_SIG = b'PK\x05\x06'
CD_FMT = '<IHHHHHHIIIHHHHHII'
CD_SIZE = struct.calcsize(CD_FMT)

# fixed timestamp so the output is deterministic
FIXED_DATE = ((2026 - 1980) << 9) | (10 << 5) | 22
FIXED_TIME = 0


class ZipError(ValueError):
    pass


def _b(value):
    return value.encode('utf-8') if isinstance(value, str) else value


def read_index(path):
    """Read the EOCD + central directory without extracting the archive."""
    with open(path, 'rb') as fh:
        size = os.fstat(fh.fileno()).st_size
        back = min(size, 66000)
        fh.seek(size - back)
        buf = fh.read(back)
        pos = buf.rfind(EOCD_SIG)
        if pos < 0:
            raise ZipError('EOCD not found (not a zip?)')
        (sig, disk, cddisk, nrec, ntot, cdsize, cdoff,
         clen) = struct.unpack('<IHHHHIIH', buf[pos:pos + 22])
        if disk or cddisk or nrec != ntot:
            raise ZipError('multi-disk archives are not supported')
        if cdoff == 0xFFFFFFFF or cdsize == 0xFFFFFFFF or nrec == 0xFFFF:
            raise ZipError('ZIP64 archives are not supported')
        comment = buf[pos + 22:pos + 22 + clen]
        fh.seek(cdoff)
        cd = fh.read(cdsize)
    entries = []
    i = 0
    while i < len(cd):
        if cd[i:i + 4] != CD_SIG:
            raise ZipError('central directory is corrupt at offset %d' % i)
        vals = struct.unpack(CD_FMT, cd[i:i + CD_SIZE])
        (sig, vmade, vneed, flags, method, mtime, mdate, crc, csize, usize,
         fnl, exl, cml, dstart, iattr, eattr, off) = vals
        p = i + CD_SIZE
        entries.append({
            'vmade': vmade, 'vneed': vneed, 'flags': flags, 'method': method,
            'mtime': mtime, 'mdate': mdate, 'crc': crc, 'csize': csize,
            'usize': usize,
            'name': cd[p:p + fnl],
            'extra': cd[p + fnl:p + fnl + exl],
            'comment': cd[p + fnl + exl:p + fnl + exl + cml],
            'dstart': dstart, 'iattr': iattr, 'eattr': eattr, 'off': off,
        })
        i = p + fnl + exl + cml
    if len(entries) != nrec:
        raise ZipError('entry count %d != %d from EOCD' % (len(entries), nrec))
    return {'path': path, 'size': size, 'entries': entries, 'comment': comment}


def names(index):
    return [e['name'].decode('utf-8', 'replace') for e in index['entries']]


def read_member(path, name):
    import zipfile
    with zipfile.ZipFile(path) as zf:
        try:
            info = zf.getinfo(name)
        except KeyError:
            raise ZipError('member %r not found' % name)
        return zf.read(info)


def rewrite(src, dst, replacements=None, removals=None, additions=None,
            progress=None, level=6):
    """Write a new IPA.

    replacements: {name(bytes): new content(bytes)}
    removals    : set of name(bytes) to drop
    additions   : list of (name(bytes), content(bytes)) to add
    progress    : f(done, total, bytes_done, bytes_total)
    """
    replacements = {(_b(k)): v for k, v in (replacements or {}).items()}
    removals = {_b(n) for n in (removals or set())}
    additions = [(_b(n), d) for n, d in (additions or [])]
    index = read_index(src)
    present = {e['name'] for e in index['entries']}
    for name, _ in additions:
        if name in present:
            raise ZipError('member %r already exists' % name.decode('utf-8', 'replace'))

    kept = [e for e in index['entries'] if e['name'] not in removals]
    total_bytes = sum(e['usize'] for e in kept) + sum(len(d) for _, d in additions)
    total_members = len(kept) + len(additions)
    done = 0
    written_bytes = 0
    written = []

    tmp = dst
    with open(src, 'rb') as fi, open(tmp, 'wb') as fo:
        for ent in kept:
            fi.seek(ent['off'])
            head = fi.read(30)
            if head[:4] != LH_SIG:
                raise ZipError('local header is corrupt for %r' % ent['name'])
            lfnl, lexl = struct.unpack('<HH', head[26:30])
            lname = fi.read(lfnl)
            lextra = fi.read(lexl)
            raw = fi.read(ent['csize'])
            if len(raw) != ent['csize']:
                raise ZipError('truncated data for %r' % ent['name'])

            crc, csize, usize = ent['crc'], ent['csize'], ent['usize']
            method = ent['method']
            if ent['name'] in replacements:
                blob = replacements[ent['name']]
                comp = zlib.compressobj(level, zlib.DEFLATED, -15)
                raw = comp.compress(blob) + comp.flush()
                crc = zlib.crc32(blob) & 0xFFFFFFFF
                csize, usize = len(raw), len(blob)
                method = 8

            flags = ent['flags'] & ~0x08
            offset = fo.tell()
            fo.write(struct.pack('<IHHHHHIIIHH', 0x04034B50, ent['vneed'], flags,
                                 method, ent['mtime'], ent['mdate'], crc, csize,
                                 usize, len(lname), len(lextra)))
            fo.write(lname)
            fo.write(lextra)
            fo.write(raw)
            written.append((ent, offset, flags, method, crc, csize, usize,
                            ent['name'], ent['extra'], ent['comment']))
            done += 1
            written_bytes += usize
            if progress:
                progress(done, total_members, written_bytes, total_bytes)

        for name, blob in additions:
            comp = zlib.compressobj(level, zlib.DEFLATED, -15)
            raw = comp.compress(blob) + comp.flush()
            crc = zlib.crc32(blob) & 0xFFFFFFFF
            offset = fo.tell()
            fo.write(struct.pack('<IHHHHHIIIHH', 0x04034B50, 20, 0, 8,
                                 FIXED_TIME, FIXED_DATE, crc, len(raw), len(blob),
                                 len(name), 0))
            fo.write(name)
            fo.write(raw)
            written.append((None, offset, 0, 8, crc, len(raw), len(blob),
                            name, b'', b''))
            done += 1
            written_bytes += len(blob)
            if progress:
                progress(done, total_members, written_bytes, total_bytes)

        cd_off = fo.tell()
        for (ent, offset, flags, method, crc, csize, usize, name, extra,
             comment) in written:
            if ent is None:
                vmade, iattr, eattr, dstart = 0x031E, 0, 0, 0
                mtime, mdate = FIXED_TIME, FIXED_DATE
            else:
                vmade, iattr, eattr = ent['vmade'], ent['iattr'], ent['eattr']
                dstart = ent['dstart']
                mtime, mdate = ent['mtime'], ent['mdate']
            fo.write(struct.pack(CD_FMT, 0x02014B50, vmade, 20, flags, method,
                                 mtime, mdate, crc, csize, usize, len(name),
                                 len(extra), len(comment), dstart, iattr, eattr,
                                 offset))
            fo.write(name)
            fo.write(extra)
            fo.write(comment)
        cd_size = fo.tell() - cd_off
        fo.write(struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, len(written),
                             len(written), cd_size, cd_off, len(index['comment'])))
        fo.write(index['comment'])
        total = fo.tell()
    return {'members': len(written), 'bytes': total}
