"""Rewrite an IPA: copy members as-is, replace/remove/add as needed."""
import os
import struct
import zlib

LH_SIG = b'PK\x03\x04'
CD_SIG = b'PK\x01\x02'
EOCD_SIG = b'PK\x05\x06'
ZIP64_LOCATOR_SIG = b'PK\x06\x07'
CD_FMT = '<IHHHHHHIIIHHHHHII'
CD_SIZE = struct.calcsize(CD_FMT)
MAX_U16 = 0xFFFF
MAX_U32 = 0xFFFFFFFF
ZIP64_EXTRA_ID = 0x0001

# fixed timestamp so the output is deterministic
FIXED_DATE = ((2026 - 1980) << 9) | (10 << 5) | 22
FIXED_TIME = 0


class ZipError(ValueError):
    pass


def _validate_extra_fields(extra, context):
    """Validate classic ZIP extra-field framing and reject ZIP64 fields."""
    offset = 0
    while offset < len(extra):
        if len(extra) - offset < 4:
            raise ZipError('truncated extra-field header in %s' % context)
        field_id, field_size = struct.unpack_from('<HH', extra, offset)
        offset += 4
        if field_id == ZIP64_EXTRA_ID:
            raise ZipError('ZIP64 extra fields are not supported (%s)' % context)
        if field_size > len(extra) - offset:
            raise ZipError('truncated extra-field data in %s' % context)
        offset += field_size


def _require_classic_u32(value, description):
    if not 0 <= value < MAX_U32:
        raise ZipError('%s exceeds classic ZIP limits' % description)


def _b(value):
    return value.encode('utf-8') if isinstance(value, str) else value


def read_index(path):
    """Read and validate a single-disk, classic ZIP central directory."""
    with open(path, 'rb') as fh:
        size = os.fstat(fh.fileno()).st_size
        back = min(size, 22 + MAX_U16)
        fh.seek(size - back)
        buf = fh.read(back)
        pos = buf.rfind(EOCD_SIG)
        eocd = None
        while pos >= 0:
            if pos + 22 <= len(buf):
                fields = struct.unpack_from('<IHHHHIIH', buf, pos)
                comment_length = fields[-1]
                if pos + 22 + comment_length == len(buf):
                    eocd = (pos, fields)
                    break
            pos = buf.rfind(EOCD_SIG, 0, pos)
        if eocd is None:
            raise ZipError('valid EOCD not found (not a classic ZIP?)')

        pos, (sig, disk, cddisk, nrec, ntot, cdsize, cdoff, clen) = eocd
        eocd_offset = size - back + pos
        comment = buf[pos + 22:pos + 22 + clen]
        if len(comment) != clen:
            raise ZipError('truncated ZIP comment')
        if (nrec == MAX_U16 or ntot == MAX_U16 or cdsize == MAX_U32
                or cdoff == MAX_U32):
            raise ZipError('ZIP64 archives are not supported')
        if disk or cddisk or nrec != ntot:
            raise ZipError('multi-disk archives are not supported')
        if eocd_offset >= 20:
            fh.seek(eocd_offset - 20)
            if fh.read(4) == ZIP64_LOCATOR_SIG:
                raise ZipError('ZIP64 archives are not supported')
        cd_end = cdoff + cdsize
        if cd_end > eocd_offset or cd_end != eocd_offset:
            raise ZipError(
                'unsupported data between central directory and EOCD')
        fh.seek(cdoff)
        cd = fh.read(cdsize)
        if len(cd) != cdsize:
            raise ZipError('truncated central directory')

    entries = []
    i = 0
    while i < len(cd):
        if len(cd) - i < CD_SIZE:
            raise ZipError('truncated central-directory header at offset %d' % i)
        if cd[i:i + 4] != CD_SIG:
            raise ZipError('central directory is corrupt at offset %d' % i)
        vals = struct.unpack(CD_FMT, cd[i:i + CD_SIZE])
        (sig, vmade, vneed, flags, method, mtime, mdate, crc, csize, usize,
         fnl, exl, cml, dstart, iattr, eattr, off) = vals
        p = i + CD_SIZE
        record_end = p + fnl + exl + cml
        if record_end > len(cd):
            raise ZipError(
                'truncated central-directory metadata at offset %d' % i)
        if (csize == MAX_U32 or usize == MAX_U32 or off == MAX_U32
                or dstart == MAX_U16):
            raise ZipError('ZIP64 entries are not supported')
        if dstart:
            raise ZipError('multi-disk entries are not supported')
        name = cd[p:p + fnl]
        extra = cd[p + fnl:p + fnl + exl]
        _validate_extra_fields(extra, 'central entry %r' % name)
        entries.append({
            'vmade': vmade, 'vneed': vneed, 'flags': flags, 'method': method,
            'mtime': mtime, 'mdate': mdate, 'crc': crc, 'csize': csize,
            'usize': usize,
            'name': name,
            'extra': extra,
            'comment': cd[p + fnl + exl:p + fnl + exl + cml],
            'dstart': dstart, 'iattr': iattr, 'eattr': eattr, 'off': off,
        })
        i = record_end
    if len(entries) != nrec:
        raise ZipError('entry count %d != %d from EOCD' % (len(entries), nrec))
    return {
        'path': path,
        'size': size,
        'entries': entries,
        'comment': comment,
        'cd_offset': cdoff,
        'eocd_offset': eocd_offset,
    }


def _read_local_record(fh, entry, index):
    """Validate a local record and return its name, extra, and data offset."""
    if entry['off'] >= index['cd_offset']:
        raise ZipError('local header offset is outside the file data region')
    if entry['off'] + 30 > index['cd_offset']:
        raise ZipError('truncated local header for %r' % entry['name'])
    fh.seek(entry['off'])
    header = fh.read(30)
    if len(header) != 30:
        raise ZipError('truncated local header for %r' % entry['name'])
    (signature, version, flags, method, mtime, mdate, crc, csize, usize,
     name_length, extra_length) = struct.unpack('<IHHHHHIIIHH', header)
    if signature != 0x04034B50:
        raise ZipError('local header is corrupt for %r' % entry['name'])
    if flags != entry['flags'] or method != entry['method']:
        raise ZipError('local/central header mismatch for %r' % entry['name'])
    if csize == MAX_U32 or usize == MAX_U32:
        raise ZipError('ZIP64 local entries are not supported')

    name = fh.read(name_length)
    if len(name) != name_length:
        raise ZipError('truncated local filename for %r' % entry['name'])
    if name != entry['name']:
        raise ZipError('local/central filename mismatch for %r' % entry['name'])
    extra = fh.read(extra_length)
    if len(extra) != extra_length:
        raise ZipError('truncated local extra field for %r' % entry['name'])
    _validate_extra_fields(extra, 'local entry %r' % entry['name'])

    if not flags & 0x08 and (
            crc != entry['crc'] or csize != entry['csize']
            or usize != entry['usize']):
        raise ZipError('local/central size or CRC mismatch for %r'
                       % entry['name'])

    data_offset = entry['off'] + 30 + name_length + extra_length
    data_end = data_offset + entry['csize']
    if data_end > index['cd_offset'] or data_end > index['size']:
        raise ZipError('truncated compressed data for %r' % entry['name'])
    return name, extra, data_offset


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
            progress=None, level=6, normalize_local_extras=False):
    """Write a new IPA.

    replacements: {name(bytes): new content(bytes)}
    removals    : set of name(bytes) to drop
    additions   : list of (name(bytes), content(bytes)) to add
    progress    : f(done, total, bytes_done, bytes_total)
    normalize_local_extras: use central extra fields in local headers
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
    if len(kept) + len(additions) >= MAX_U16:
        raise ZipError('ZIP64 output is not supported')
    for name, _blob in additions:
        if len(name) > MAX_U16:
            raise ZipError('member name exceeds classic ZIP limits')

    # Validate every local record before creating the destination, so malformed
    # headers cannot silently shift reads into a neighboring member.
    with open(src, 'rb') as check:
        for ent in kept:
            _read_local_record(check, ent, index)

    total_bytes = sum(e['usize'] for e in kept) + sum(len(d) for _, d in additions)
    total_members = len(kept) + len(additions)
    done = 0
    written_bytes = 0
    written = []

    tmp = dst
    with open(src, 'rb') as fi, open(tmp, 'wb') as fo:
        for ent in kept:
            lname, lextra, data_offset = _read_local_record(fi, ent, index)
            fi.seek(data_offset)
            raw = fi.read(ent['csize'])
            if len(raw) != ent['csize']:
                raise ZipError('truncated data for %r' % ent['name'])
            if normalize_local_extras:
                lextra = ent['extra']

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
            _require_classic_u32(offset, 'local header offset')
            _require_classic_u32(csize, 'compressed member size')
            _require_classic_u32(usize, 'uncompressed member size')
            if len(lname) > MAX_U16 or len(lextra) > MAX_U16:
                raise ZipError('local header metadata exceeds classic ZIP limits')
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
            if len(blob) >= MAX_U32:
                raise ZipError('uncompressed member size exceeds classic ZIP limits')
            comp = zlib.compressobj(level, zlib.DEFLATED, -15)
            raw = comp.compress(blob) + comp.flush()
            crc = zlib.crc32(blob) & 0xFFFFFFFF
            offset = fo.tell()
            _require_classic_u32(offset, 'local header offset')
            _require_classic_u32(len(raw), 'compressed member size')
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
        _require_classic_u32(cd_off, 'central directory offset')
        for (ent, offset, flags, method, crc, csize, usize, name, extra,
             comment) in written:
            if len(name) > MAX_U16 or len(extra) > MAX_U16 \
                    or len(comment) > MAX_U16:
                raise ZipError('central directory metadata exceeds classic ZIP limits')
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
        _require_classic_u32(cd_size, 'central directory size')
        if len(written) >= MAX_U16 or len(index['comment']) > MAX_U16:
            raise ZipError('ZIP64 output is not supported')
        fo.write(struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, len(written),
                             len(written), cd_size, cd_off, len(index['comment'])))
        fo.write(index['comment'])
        total = fo.tell()
    return {'members': len(written), 'bytes': total}
