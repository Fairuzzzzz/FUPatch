"""Mach-O helpers: fat/thin detection, arm64 slice, cryptid, sha256."""
import hashlib
import struct

FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF
MH_MAGIC_64 = 0xFEEDFACF
MH_MAGIC = 0xFEEDFACE
LC_ENCRYPTION_INFO = 0x21
LC_ENCRYPTION_INFO_64 = 0x2C
CPU_TYPE_ARM = 0x0000000C
CPU_TYPE_ARM64 = 0x0100000C


class MachOError(ValueError):
    pass


def arch_name(cputype, cpusubtype):
    sub = cpusubtype & 0xFF
    if cputype == CPU_TYPE_ARM64:
        return 'arm64e' if sub == 2 else 'arm64'
    if cputype == CPU_TYPE_ARM:
        return 'armv7s' if sub == 11 else ('armv7k' if sub == 12 else 'armv7')
    return 'cpu-%#x' % (cputype & 0xFFFFFFFF)


def _u32le(data, off):
    return struct.unpack_from('<I', data, off)[0]


def _u32be(data, off):
    return struct.unpack_from('>I', data, off)[0]


def _thin_slice(data, offset, magic, cputype=None, cpusubtype=None):
    if offset + 32 > len(data):
        raise MachOError('truncated slice at offset %#x' % offset)
    if magic == MH_MAGIC_64:
        hdr = 32
    elif magic == MH_MAGIC:
        hdr = 28
    else:
        raise MachOError('unknown Mach-O magic %#x' % magic)
    cpu = _u32le(data, offset + 4)
    sub = _u32le(data, offset + 8)
    ncmds = _u32le(data, offset + 16)
    off = offset + hdr
    cryptid = None
    cryptoff = None
    for _ in range(ncmds):
        if off + 8 > len(data):
            raise MachOError('truncated load command')
        cmd = _u32le(data, off)
        size = _u32le(data, off + 4)
        if size < 8:
            raise MachOError('corrupt load command (%d bytes)' % size)
        if cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64):
            cryptoff = _u32le(data, off + 8)
            cryptid = _u32le(data, off + 16)
        off += size
    blob = data[offset:offset + 0]  # placeholder; the caller fills in the size
    del blob
    return {
        'arch': arch_name(cpu, sub),
        'cputype': cpu,
        'cpusubtype': sub,
        'offset': offset,
        'size': None,
        'cryptid': cryptid,
        'cryptoff': cryptoff,
        'encrypted': bool(cryptid),
    }


def analyze(data):
    """Describe a Mach-O blob.

    Returns {'kind': 'fat'|'thin', 'slices': [...], 'size': len(data)}.
    Each slice: arch, cputype, cpusubtype, offset, size, cryptid, encrypted.
    """
    if len(data) < 8:
        raise MachOError('file is too short')
    be = _u32be(data, 0)
    if be in (FAT_MAGIC, FAT_MAGIC_64):
        return _analyze_fat(data, be)
    le = _u32le(data, 0)
    if le in (MH_MAGIC_64, MH_MAGIC):
        sl = _thin_slice(data, 0, le)
        sl['size'] = len(data)
        sl['sha256'] = hashlib.sha256(data).hexdigest()
        return {'kind': 'thin', 'slices': [sl], 'size': len(data)}
    raise MachOError('not a Mach-O (magic %#x / %#x)' % (be, le))


def _analyze_fat(data, magic):
    count = _u32be(data, 4)
    if count == 0 or count > 16:
        raise MachOError('unreasonable fat slice count: %d' % count)
    wide = magic == FAT_MAGIC_64
    entry = 32 if wide else 20
    base = 8
    slices = []
    for i in range(count):
        off = base + i * entry
        if off + entry > len(data):
            raise MachOError('truncated fat header')
        cpu = _u32be(data, off)
        sub = _u32be(data, off + 4)
        if wide:
            start = struct.unpack_from('>Q', data, off + 8)[0]
            size = struct.unpack_from('>Q', data, off + 16)[0]
        else:
            start = _u32be(data, off + 8)
            size = _u32be(data, off + 12)
        if start + size > len(data):
            raise MachOError('slice %d runs past the end of the file' % i)
        sub_data = data[start:start + size]
        try:
            sl = _thin_slice(sub_data, 0, _u32le(sub_data, 0), cpu, sub)
        except MachOError:
            sl = {'arch': arch_name(cpu, sub), 'cputype': cpu, 'cpusubtype': sub,
                  'cryptid': None, 'cryptoff': None, 'encrypted': False}
        sl['offset'] = start
        sl['size'] = size
        sl['sha256'] = hashlib.sha256(sub_data).hexdigest()
        slices.append(sl)
    return {'kind': 'fat', 'slices': slices, 'size': len(data)}


def find_arm64(analysis):
    """arm64 slice (prefer plain arm64, then arm64e)."""
    best = None
    for sl in analysis['slices']:
        if sl['arch'] == 'arm64':
            return sl
        if sl['arch'] == 'arm64e' and best is None:
            best = sl
    return best


def extract(data, sl):
    return data[sl['offset']:sl['offset'] + sl['size']]


def replace_slice(data, sl, new_slice):
    if len(new_slice) != sl['size']:
        raise MachOError('new slice size %d != %d' % (len(new_slice), sl['size']))
    out = bytearray(data)
    out[sl['offset']:sl['offset'] + sl['size']] = new_slice
    return bytes(out)
