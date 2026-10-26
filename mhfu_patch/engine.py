"""Patch engine: inspect an IPA, apply binary steps, write a new IPA."""
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
            'step %s at %#x does not match (found: %s, expected: %s)'
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


def look(ipa_path, patch_set=None, directory=None, profile_id=None):
    """Inspect an IPA without modifying anything."""
    ipa_path = os.path.abspath(ipa_path)
    if not os.path.isfile(ipa_path):
        raise PatchError('IPA not found: %s' % ipa_path)
    idx = ziprewrite.read_index(ipa_path)
    names = [_decode(e['name']) for e in idx['entries']]
    info_member = _info_member(names)
    if not info_member:
        raise PatchError('Info.plist not found inside the IPA')
    app_dir = info_member.rsplit('/', 1)[0]
    raw_plist = ziprewrite.read_member(ipa_path, info_member)
    pl = plistlib.loads(raw_plist)
    exe = pl.get('CFBundleExecutable')
    if not exe:
        raise PatchError('CFBundleExecutable is missing from Info.plist')
    exe_member = app_dir + '/' + exe
    if exe_member not in names:
        raise PatchError('executable %s not found inside the IPA' % exe_member)

    data = ziprewrite.read_member(ipa_path, exe_member)
    ma = macho.analyze(data)
    arm = macho.find_arm64(ma)
    if arm is None:
        raise PatchError('IPA has no arm64 slice (found: %s)'
                         % ', '.join(s['arch'] for s in ma['slices']))

    m, kind = (None, None)
    if patch_set:
        m = mf.load_set(patch_set, directory)
        kind = mf.classify(m, arm['sha256'])
    else:
        m, kind = mf.find_set_for_sha(arm['sha256'], directory)

    profile = None
    if m:
        try:
            if profile_id:
                profile = mf.select_profile(m, profile_id)
            elif kind == 'result':
                profile = (mf.find_profile_for_sha(m, arm['sha256'])
                           or mf.select_profile(m, None))
            else:
                profile = mf.select_profile(m, None)
        except mf.ManifestError as exc:
            raise PatchError(str(exc))

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
        'profile': profile.get('id') if profile else None,
        'profile_label': profile.get('label') if profile else None,
        'profile_note': profile.get('note') if profile else None,
        'profile_default': bool(profile and profile.get('default')),
        'profile_result_sha256': (
            mf.profile_result_sha(m, profile) if m else None),
        'profiles': [
            {
                'id': item.get('id'),
                'label': item.get('label'),
                'note': item.get('note'),
                'default': bool(item.get('default')),
                'result_sha256': item.get('result_sha256'),
            }
            for item in ((m.get('profiles') or []) if m else [])
        ],
        'patch_set': None,
        'patch_title': None,
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
        report['reason'] = ('unknown binary (sha %s) — not a supported MHFU IPA'
                            % arm['sha256'][:16])
        return report
    report['patch_set'] = m['id']
    report['patch_title'] = m.get('title', m['id'])
    steps = mf.profile_steps(m, profile)
    used = {step['feature'] for step in steps}
    report['features'] = [f for f in m.get('features', []) if f['id'] in used]
    report['steps_total'] = len(steps)

    base = int(m['slice']['vaddr_base'], 0)
    sl = bytearray(macho.extract(data, arm))
    for step in steps:
        off = int(step['vaddr'], 0) - base
        exp = bytes.fromhex(step['expect'])
        rep = bytes.fromhex(step['replace'])
        cur = bytes(sl[off:off + len(exp)])
        if cur == rep:
            report['steps_applied'] += 1
        elif cur == exp:
            report['steps_pending'] += 1
            sl[off:off + len(rep)] = rep
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
        report['reason'] = ('IPA is still encrypted (cryptid=%s) — a decrypted IPA is '
                            'required' % arm.get('cryptid'))
    elif report['steps_mismatch']:
        report['reason'] = ('binary partially matches; unrecognized steps: %s'
                            % ', '.join(report['steps_mismatch'][:4]))
    return report


def suggest_output(ipa_path):
    """Output path that is still free, next to the source IPA."""
    folder = os.path.dirname(os.path.abspath(ipa_path)) or '.'
    name = 'MHFU_patched'
    candidate = os.path.join(folder, name + '.ipa')
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, '%s-%d.ipa' % (name, n))
        n += 1
    return candidate


def apply_steps(slice_bytes, m, on_step=None, profile=None):
    """Apply base steps plus the selected profile overrides."""
    base = int(m['slice']['vaddr_base'], 0)
    buf = bytearray(slice_bytes)
    applied, skipped = [], []
    steps = mf.profile_steps(m, profile)
    total = len(steps)
    for i, step in enumerate(steps):
        off = int(step['vaddr'], 0) - base
        exp = bytes.fromhex(step['expect'])
        rep = bytes.fromhex(step['replace'])
        if off + len(exp) > len(buf):
            raise PatchError('step %s runs past the end of the slice' % step['id'])
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
          force=False, profile=None):
    """Patch the IPA and write the result. Returns a report."""
    started = time.monotonic()
    ipa_path = os.path.abspath(ipa_path)
    out_path = os.path.abspath(out_path)
    if out_path == ipa_path:
        raise PatchError('output file must differ from the source IPA')
    if os.path.exists(out_path) and not force:
        raise PatchError('output file already exists: %s' % out_path)
    out_dir = os.path.dirname(out_path) or '.'
    if not os.path.isdir(out_dir):
        raise PatchError('output folder does not exist: %s' % out_dir)

    _emit(on_event, 'inspect', 1, 'reading IPA')
    info = look(ipa_path, patch_set=patch_set, directory=directory,
                profile_id=profile)
    if not info['supported']:
        raise PatchError(info['reason'] or 'unsupported IPA')
    m = mf.load_set(info['patch_set'], directory)
    selected = mf.select_profile(m, profile) if profile else mf.select_profile(
        m, info.get('profile'))

    need = info['size'] + (32 << 20)
    free = shutil.disk_usage(out_dir).free
    if free < need:
        raise PatchError('not enough disk space: need %.0f MB, %.0f MB free'
                         % (need / 1e6, free / 1e6))

    ver = version or info['info_version']
    if not ver:
        raise PatchError('source Info.plist has no version — pass --version')
    if not VERSION_RE.match(ver):
        raise PatchError('invalid version %r' % ver)
    already = (not info['steps_pending'] and not info['remove_pending']
               and not info['add_pending'])
    if already and ver == info['info_version'] and not dry_run:
        raise PatchError('this IPA is already patched')

    _emit(on_event, 'read', 5, info['exe_member'])
    data = ziprewrite.read_member(ipa_path, info['exe_member'])
    ma = macho.analyze(data)
    arm = macho.find_arm64(ma)
    slice_bytes = macho.extract(data, arm)
    _emit(on_event, 'verify', 8, 'slice sha %s' % arm['sha256'][:16])

    def on_step(done, total):
        if is_cancelled and is_cancelled():
            raise PatchError('cancelled by user')
        pct = 10 + int(14 * done / max(1, total))
        _emit(on_event, 'steps', pct, '%d/%d' % (done, total))

    new_slice, applied, skipped = apply_steps(
        slice_bytes, m, on_step, profile=selected)
    got = hashlib.sha256(new_slice).hexdigest()
    result_sha = mf.profile_result_sha(m, selected)
    if got != result_sha:
        raise PatchError('resulting binary sha mismatch\n  got     : %s\n  expected: %s'
                         % (got, result_sha))
    _emit(on_event, 'steps', 24, 'binary sha ok')

    fat_out = bool(keep_fat and ma['kind'] == 'fat')
    new_exe = macho.replace_slice(data, arm, new_slice) if fat_out else new_slice

    _emit(on_event, 'plist', 25, 'version %s -> %s' % (info['info_version'], ver))
    raw_plist = ziprewrite.read_member(ipa_path, info['info_member'])
    new_plist = package.patch_info_plist(raw_plist, m, ver)

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
        'slice_sha256': result_sha,
        'profile': selected.get('id') if selected else None,
        'profile_label': selected.get('label') if selected else None,
        'profile_note': selected.get('note') if selected else None,
        'profile_result_sha256': result_sha,
        'keep_fat': fat_out,
        'exe_kind_in': ma['kind'],
        'exe_kind_out': 'fat' if fat_out else 'thin',
        'patch_set': m['id'],
        'dry_run': bool(dry_run),
    }
    if dry_run:
        report['members'] = len(names) - len(removals) + len(additions)
        report['duration'] = round(time.monotonic() - started, 2)
        _emit(on_event, 'done', 100, 'dry run')
        return report

    replacements = {
        info['exe_member'].encode(): new_exe,
        info['info_member'].encode(): new_plist,
    }
    removals_b = {name.encode() for name in removals}
    tmp = out_path + '.part'

    def zip_progress(done, total, wb, tb):
        if is_cancelled and is_cancelled():
            raise PatchError('cancelled by user')
        pct = 25 + int(67 * (wb / max(1, tb)))
        _emit(on_event, 'write', pct,
              '%d/%d files · %.0f/%.0f MB' % (done, total, wb / 1e6, tb / 1e6))

    _emit(on_event, 'write', 25, 'starting')
    try:
        res = ziprewrite.rewrite(ipa_path, tmp, replacements, removals_b,
                                 additions, progress=zip_progress)
        _emit(on_event, 'verify', 93, 're-checking binary in output')
        back = ziprewrite.read_member(tmp, info['exe_member'])
        back_slice = macho.extract(back, macho.find_arm64(macho.analyze(back)))
        back_sha = hashlib.sha256(back_slice).hexdigest()
        if back_sha != result_sha:
            raise PatchError('binary in output does not match (sha %s)' % back_sha)
        back_plist = plistlib.loads(ziprewrite.read_member(tmp, info['info_member']))
        if back_plist.get('CFBundleShortVersionString') != ver:
            raise PatchError('output version mismatch')
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    report['members'] = res['members']
    report['size'] = os.path.getsize(out_path)
    report['duration'] = round(time.monotonic() - started, 2)
    report['output_sha256'] = _file_sha(out_path)
    _emit(on_event, 'done', 100, 'ok')
    return report
