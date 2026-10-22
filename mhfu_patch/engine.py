"""Mesin patch: inspeksi IPA, terapkan langkah biner, tulis IPA baru."""
import hashlib
import os
import plistlib
import re
import shutil
import time

from . import macho, package
from . import manifest as mf
from . import ziprewrite

VERSION_RE = re.compile(r'^\d{1,3}(\.\d{1,3}){1,3}$')


class PatchError(RuntimeError):
    pass


class StepMismatch(PatchError):
    def __init__(self, step, offset, found, expected):
        self.step_id = step['id']
        self.offset = offset
        self.found = found.hex()
        self.expected = expected.hex()
        super().__init__(
            'langkah %s pada %#x tidak cocok (di biner: %s, seharusnya: %s)'
            % (step['id'], offset, self.found, self.expected))


def _emit(cb, phase, pct, detail=''):
    if cb:
        cb({'phase': phase, 'pct': int(pct), 'detail': detail})


def _file_sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _decode(name):
    return name.decode('utf-8', 'replace')


def _info_member(names):
    for name in names:
        parts = name.split('/')
        if (len(parts) == 3 and parts[0] == 'Payload'
                and parts[1].endswith('.app') and parts[2] == 'Info.plist'):
            return name
    return None


def look(ipa_path, patch_set=None, directory=None):
    """Inspeksi IPA tanpa mengubah apa pun."""
    ipa_path = os.path.abspath(ipa_path)
    if not os.path.isfile(ipa_path):
        raise PatchError('IPA tidak ada: %s' % ipa_path)
    idx = ziprewrite.read_index(ipa_path)
    names = [_decode(e['name']) for e in idx['entries']]
    info_member = _info_member(names)
    if not info_member:
        raise PatchError('Info.plist tidak ditemukan di dalam IPA')
    app_dir = info_member.rsplit('/', 1)[0]
    raw_plist = ziprewrite.read_member(ipa_path, info_member)
    pl = plistlib.loads(raw_plist)
    exe = pl.get('CFBundleExecutable')
    if not exe:
        raise PatchError('CFBundleExecutable kosong di Info.plist')
    exe_member = app_dir + '/' + exe
    if exe_member not in names:
        raise PatchError('biner %s tidak ada di dalam IPA' % exe_member)

    data = ziprewrite.read_member(ipa_path, exe_member)
    ma = macho.analyze(data)
    arm = macho.find_arm64(ma)
    if arm is None:
        raise PatchError('IPA tidak punya slice arm64 (isi: %s)'
                         % ', '.join(s['arch'] for s in ma['slices']))

    m, kind = (None, None)
    if patch_set:
        m = mf.load_set(patch_set, directory)
        kind = mf.classify(m, arm['sha256'])
    else:
        m, kind = mf.find_set_for_sha(arm['sha256'], directory)

    report = {
        'ipa': ipa_path,
        'size': idx['size'],
        'members': len(names),
        'app_dir': app_dir,
        'app_name': exe,
        'bundle_id': pl.get('CFBundleIdentifier'),
        'info_version': pl.get('CFBundleShortVersionString'),
        'info_member': info_member,
        'exe_member': exe_member,
        'exe_kind': ma['kind'],
        'slices': [{'arch': s['arch'], 'size': s['size'],
                    'sha256': s['sha256'], 'encrypted': s['encrypted']}
                   for s in ma['slices']],
        'arm64_sha256': arm['sha256'],
        'arm64_size': arm['size'],
        'cryptid': arm.get('cryptid'),
        'supported': False,
        'match': kind,
        'patch_set': None,
        'patch_title': None,
        'patch_version': None,
        'features': [],
        'steps_total': 0,
        'steps_pending': 0,
        'steps_applied': 0,
        'steps_mismatch': [],
        'remove_pending': [],
        'add_pending': [],
        'reason': None,
    }

    if not m:
        report['reason'] = ('biner tidak dikenal (sha %s) — bukan IPA MHFU yang '
                            'didukung' % arm['sha256'][:16])
        return report
    report['patch_set'] = m['id']
    report['patch_title'] = m.get('title', m['id'])
    report['patch_version'] = (m.get('version') or {}).get('default')
    used = {step['feature'] for step in m['binary_steps']}
    report['features'] = [f for f in m.get('features', []) if f['id'] in used]
    report['steps_total'] = len(m['binary_steps'])

    base = int(m['slice']['vaddr_base'], 0)
    sl = macho.extract(data, arm)
    for step in m['binary_steps']:
        off = int(step['vaddr'], 0) - base
        exp = bytes.fromhex(step['expect'])
        rep = bytes.fromhex(step['replace'])
        cur = sl[off:off + len(exp)]
        if cur == rep:
            report['steps_applied'] += 1
        elif cur == exp:
            report['steps_pending'] += 1
        else:
            report['steps_mismatch'].append(step['id'])

    present = set(names)
    report['remove_pending'] = sorted(package.resolve_removals(
        m.get('members_remove'), names))
    report['add_pending'] = [item['name'] for item in (m.get('members_add') or [])
                             if item['name'] not in present]

    ok = (kind is not None and not arm.get('encrypted')
          and not report['steps_mismatch'])
    report['supported'] = ok
    if arm.get('encrypted'):
        report['reason'] = ('IPA masih terenkripsi (cryptid=%s) — butuh IPA hasil '
                            'dekripsi' % arm.get('cryptid'))
    elif report['steps_mismatch']:
        report['reason'] = ('biner cocok sebagian; langkah tidak dikenali: %s'
                            % ', '.join(report['steps_mismatch'][:4]))
    return report


def apply_steps(slice_bytes, m, on_step=None):
    """Terapkan langkah biner (3 arah: expect→tulis, replace→lewati, lain→gagal)."""
    base = int(m['slice']['vaddr_base'], 0)
    buf = bytearray(slice_bytes)
    applied, skipped = [], []
    total = len(m['binary_steps'])
    for i, step in enumerate(m['binary_steps']):
        off = int(step['vaddr'], 0) - base
        exp = bytes.fromhex(step['expect'])
        rep = bytes.fromhex(step['replace'])
        if off + len(exp) > len(buf):
            raise PatchError('langkah %s melewati akhir slice' % step['id'])
        cur = bytes(buf[off:off + len(exp)])
        if cur == rep:
            skipped.append(step['id'])
        elif cur == exp:
            buf[off:off + len(rep)] = rep
            applied.append(step['id'])
        else:
            raise StepMismatch(step, int(step['vaddr'], 0), cur, exp)
        if on_step:
            on_step(i + 1, total)
    return bytes(buf), applied, skipped


def patch(ipa_path, out_path, version=None, keep_fat=False, dry_run=False,
          on_event=None, is_cancelled=None, directory=None, patch_set=None,
          force=False):
    """Patch IPA dan tulis hasilnya. Mengembalikan laporan."""
    started = time.monotonic()
    ipa_path = os.path.abspath(ipa_path)
    out_path = os.path.abspath(out_path)
    if out_path == ipa_path:
        raise PatchError('file keluaran tidak boleh sama dengan IPA sumber')
    if os.path.exists(out_path) and not force:
        raise PatchError('file keluaran sudah ada: %s' % out_path)
    out_dir = os.path.dirname(out_path) or '.'
    if not os.path.isdir(out_dir):
        raise PatchError('folder keluaran tidak ada: %s' % out_dir)

    _emit(on_event, 'inspeksi', 1, 'membaca IPA')
    info = look(ipa_path, patch_set=patch_set, directory=directory)
    if not info['supported']:
        raise PatchError(info['reason'] or 'IPA tidak didukung')
    m = mf.load_set(info['patch_set'], directory)

    need = info['size'] + (32 << 20)
    free = shutil.disk_usage(out_dir).free
    if free < need:
        raise PatchError('ruang disk kurang: perlu %.0f MB, tersedia %.0f MB'
                         % (need / 1e6, free / 1e6))

    ver = version or (m.get('version') or {}).get('default') or info['info_version']
    if not VERSION_RE.match(ver or ''):
        raise PatchError('versi %r tidak valid (contoh: 1.00.194)' % ver)
    if ver == info['info_version'] and not info['steps_pending'] \
            and not info['remove_pending'] and not info['add_pending'] \
            and not dry_run:
        raise PatchError('tidak ada yang perlu diubah dan versi masih %s — '
                         'pakai versi lain, mis. 1.00.195' % ver)

    _emit(on_event, 'baca biner', 5, info['exe_member'])
    data = ziprewrite.read_member(ipa_path, info['exe_member'])
    ma = macho.analyze(data)
    arm = macho.find_arm64(ma)
    slice_bytes = macho.extract(data, arm)
    _emit(on_event, 'verifikasi', 8, 'sha slice %s' % arm['sha256'][:16])

    def on_step(done, total):
        if is_cancelled and is_cancelled():
            raise PatchError('dibatalkan pengguna')
        pct = 10 + int(14 * done / max(1, total))
        _emit(on_event, 'langkah biner', pct, '%d/%d langkah' % (done, total))

    new_slice, applied, skipped = apply_steps(slice_bytes, m, on_step)
    got = hashlib.sha256(new_slice).hexdigest()
    if got != m['slice']['result_sha256']:
        raise PatchError('sha biner hasil tidak cocok\n  didapat : %s\n  harapan : %s'
                         % (got, m['slice']['result_sha256']))
    _emit(on_event, 'langkah biner', 24, 'sha biner hasil cocok')

    fat_out = bool(keep_fat and ma['kind'] == 'fat')
    new_exe = macho.replace_slice(data, arm, new_slice) if fat_out else new_slice

    _emit(on_event, 'Info.plist', 25, 'versi %s -> %s' % (info['info_version'], ver))
    raw_plist = ziprewrite.read_member(ipa_path, info['info_member'])
    new_plist = package.patch_info_plist(
        raw_plist, m, ver, marker_suffix=time.strftime('%Y-%m-%d'))

    idx = ziprewrite.read_index(ipa_path)
    names = [_decode(e['name']) for e in idx['entries']]
    removals = package.resolve_removals(m.get('members_remove'), names)
    present = set(names)
    additions = package.resolve_additions(
        m.get('members_add'), present,
        os.path.dirname(os.path.dirname(os.path.abspath(mf.__file__))))

    report = {
        'ipa': ipa_path,
        'out': out_path,
        'version': ver,
        'old_version': info['info_version'],
        'applied': applied,
        'skipped': skipped,
        'removed': sorted(removals),
        'added': [name for name, _ in additions],
        'binary_sha256': got,
        'slice_sha256': m['slice']['result_sha256'],
        'keep_fat': fat_out,
        'exe_kind_in': ma['kind'],
        'exe_kind_out': 'fat' if fat_out else 'thin',
        'patch_set': m['id'],
        'dry_run': bool(dry_run),
    }
    if dry_run:
        report['members'] = len(names) - len(removals) + len(additions)
        report['duration'] = round(time.monotonic() - started, 2)
        _emit(on_event, 'selesai', 100, 'dry run')
        return report

    replacements = {
        info['exe_member'].encode(): new_exe,
        info['info_member'].encode(): new_plist,
    }
    removals_b = {name.encode() for name in removals}
    tmp = out_path + '.part'

    def zip_progress(done, total, wb, tb):
        if is_cancelled and is_cancelled():
            raise PatchError('dibatalkan pengguna')
        pct = 25 + int(67 * (wb / max(1, tb)))
        _emit(on_event, 'tulis IPA', pct,
              '%d/%d member · %.0f/%.0f MB' % (done, total, wb / 1e6, tb / 1e6))

    _emit(on_event, 'tulis IPA', 25, 'mulai menulis')
    try:
        res = ziprewrite.rewrite(ipa_path, tmp, replacements, removals_b,
                                 additions, progress=zip_progress)
        _emit(on_event, 'verifikasi', 93, 'cek ulang biner di IPA hasil')
        back = ziprewrite.read_member(tmp, info['exe_member'])
        back_slice = macho.extract(back, macho.find_arm64(macho.analyze(back)))
        back_sha = hashlib.sha256(back_slice).hexdigest()
        if back_sha != m['slice']['result_sha256']:
            raise PatchError('biner di IPA hasil tidak cocok (sha %s)' % back_sha)
        back_plist = plistlib.loads(ziprewrite.read_member(tmp, info['info_member']))
        if back_plist.get('CFBundleShortVersionString') != ver:
            raise PatchError('versi di IPA hasil tidak sesuai')
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    report['members'] = res['members']
    report['size'] = os.path.getsize(out_path)
    report['duration'] = round(time.monotonic() - started, 2)
    report['output_sha256'] = _file_sha(out_path)
    _emit(on_event, 'selesai', 100, 'IPA siap: %s' % out_path)
    return report
