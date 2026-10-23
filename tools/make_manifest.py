#!/usr/bin/env python3
"""Developer tool: build a patch manifest from a binary pair + IPA.

Example:
  python3 tools/make_manifest.py \
      --original-ipa "original.ipa" \
      --final-bin ../re_mhfu/mh_unite_c194 \
      --intermediate-bin ../re_mhfu/mh_unite_base186 \
      --patched-ipa ../MHFU_load194.ipa \
      --id mhfu-ios-1.00.194 --version 1.00.194 \
      --out patches/mhfu-1.00.194.json
"""
import argparse
import hashlib
import json
import os
import plistlib
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FEATURES = [
    ('ui-scale', 'UI scale & render constants', [
        0x1003531b0, 0x1003581c4, 0x10035f534, 0x10035f5d0, 0x10035f7a8,
        0x10035f878, 0x100369584, 0x1005c7848]),
    ('safe-area', 'Safe area, right HUD, submit button', [
        0x100000c1d, 0x1001f56d1, 0x100208abd, 0x100208d31, 0x100208e1d,
        0x10021938d, 0x10021944d, 0x10021950d, 0x1002195cd, 0x10037d441,
        0x10037d501, 0x10037d5c1, 0x10037d681, 0x1003e2a69, 0x10049e4b4]),
    ('analog', 'Analog rect & radius', [
        0x1003bd495, 0x1003bd520, 0x1003bd67c, 0x1003bd754]),
    ('loading', 'Loading text/background & map', [
        0x100441b58, 0x1004420dc, 0x100442240, 0x100462a78, 0x100462f14]),
    ('coating', 'Coating frame aligned with the bar (A/B)', [
        0x100391ee8, 0x100391f28, 0x100391f64, 0x10049e8cc]),
]
CORE_TITLE = 'Patch core (constants & helpers)'
BASE = 0x100000000
GAP = 32


def diff_ranges(old, new):
    if len(old) != len(new):
        raise SystemExit('binary size mismatch: %d vs %d' % (len(old), len(new)))
    runs = []
    i, n = 0, len(old)
    while i < n:
        if old[i] != new[i]:
            j = i
            while j + 1 < n and old[j + 1] != new[j + 1]:
                j += 1
            runs.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    merged = []
    for start, end in runs:
        if merged and start - merged[-1][1] <= GAP:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def feature_for(addr):
    best, best_dist = None, None
    for fid, _title, addrs in FEATURES:
        for a in addrs:
            dist = abs(a - addr)
            if best_dist is None or dist < best_dist:
                best, best_dist = fid, dist
    return best if best_dist is not None and best_dist <= 64 else 'core'


def slice_sha(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_arm64(ipa_path):
    sys.path.insert(0, ROOT)
    from mhfu_patch import macho
    with zipfile.ZipFile(ipa_path) as zf:
        info = None
        for name in zf.namelist():
            if name.endswith('.app/Info.plist') and name.count('/') == 2:
                import plistlib
                pl = plistlib.loads(zf.read(name))
                exe = pl.get('CFBundleExecutable')
                info = (name.rsplit('/', 1)[0] + '/' + exe, pl, name)
                break
        if not info:
            raise SystemExit('Info.plist not found in %s' % ipa_path)
        data = zf.read(info[0])
    ma = macho.analyze(data)
    arm = macho.find_arm64(ma)
    if arm is None:
        raise SystemExit('no arm64 slice found')
    return macho.extract(data, arm), info[1]


def zip_crcs(path):
    with zipfile.ZipFile(path) as zf:
        return {i.filename: (i.CRC, i.file_size) for i in zf.infolist()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--original-ipa', required=True)
    ap.add_argument('--final-bin', required=True)
    ap.add_argument('--intermediate-bin')
    ap.add_argument('--patched-ipa', help='tested build IPA (for the package delta)')
    ap.add_argument('--id', default='mhfu-ios-1.00.194')
    ap.add_argument('--title', default='MHFU iOS — safe area, analog, loading/map, '
                                      'coating frame')
    ap.add_argument('--version', default='1.00.194')
    ap.add_argument('--out', default=os.path.join(ROOT, 'patches', 'mhfu-1.00.194.json'))
    args = ap.parse_args()

    old, plist = read_arm64(args.original_ipa)
    with open(args.final_bin, 'rb') as fh:
        new = fh.read()
    old_sha = hashlib.sha256(old).hexdigest()
    new_sha = hashlib.sha256(new).hexdigest()
    ranges = diff_ranges(old, new)
    steps = []
    for n, (start, end) in enumerate(ranges, 1):
        fid = feature_for(start + BASE)
        steps.append({
            'id': '%s.%02d' % (fid, n),
            'feature': fid,
            'vaddr': hex(start + BASE),
            'expect': old[start:end].hex(),
            'replace': new[start:end].hex(),
        })
    print('steps: %d ranges, %d bytes' % (len(steps), sum(len(s['replace']) // 2
                                                            for s in steps)))

    manifest = {
        'schema': 1,
        'id': args.id,
        'title': args.title,
        'app': {
            'bundle_id': plist.get('CFBundleIdentifier'),
            'executable': plist.get('CFBundleExecutable'),
        },
        'slice': {
            'arch': 'arm64',
            'vaddr_base': hex(BASE),
            'source_sha256': [old_sha],
            'intermediate_sha256': [],
            'result_sha256': new_sha,
        },
        'features': [{'id': fid, 'title': title}
                     for fid, title, _ in FEATURES] + [
                         {'id': 'core', 'title': CORE_TITLE}],
        'binary_steps': steps,
        'members_remove': {},
        'members_add': [],
        'info_changes': {'set': {}, 'remove': []},
        'version': {'default': args.version, 'marker_key': 'MHFUPatch'},
    }
    if args.intermediate_bin:
        manifest['slice']['intermediate_sha256'].append(
            slice_sha(args.intermediate_bin))

    if args.patched_ipa:
        a = zip_crcs(args.original_ipa)
        b = zip_crcs(args.patched_ipa)
        only_a = sorted(set(a) - set(b))
        only_b = sorted(set(b) - set(a))
        changed = sorted(n for n in set(a) & set(b) if a[n][0] != b[n][0])
        exe = plist.get('CFBundleExecutable')
        expect = {n for n in changed if n.endswith('.app/Info.plist')
                  or n.endswith('.app/' + exe)}
        if set(changed) != expect:
            raise SystemExit('member berubah tak terduga: %s'
                             % sorted(set(changed) - expect))
        manifest['members_remove'] = {
            'exact': only_a,
            'globs': ['Payload/*.app/LaunchImage*.png',
                      'Payload/*.app/_CodeSignature/*'],
        }
        assets = os.path.join(ROOT, 'assets')
        os.makedirs(assets, exist_ok=True)
        with zipfile.ZipFile(args.patched_ipa) as zf:
            for name in only_b:
                data = zf.read(name)
                fixture = os.path.join(assets, os.path.basename(name))
                with open(fixture, 'wb') as fh:
                    fh.write(data)
                manifest['members_add'].append({
                    'name': name,
                    'source': 'assets/' + os.path.basename(name),
                })
                print('fixture: %s (%d B)' % (fixture, len(data)))
        with zipfile.ZipFile(args.original_ipa) as zf:
            p_old = plistlib.loads(zf.read(
                [n for n in a if n.endswith('.app/Info.plist')][0]))
        with zipfile.ZipFile(args.patched_ipa) as zf:
            p_new = plistlib.loads(zf.read(
                [n for n in b if n.endswith('.app/Info.plist')][0]))
        version_keys = {'CFBundleShortVersionString', 'CFBundleVersion'}
        sets = {k: venum for k, venum in p_new.items()
                if k not in p_old and k not in version_keys}
        sets.update({k: venum for k, venum in p_new.items()
                     if k in p_old and p_old[k] != venum and k not in version_keys})
        removes = [k for k in p_old if k not in p_new]
        manifest['info_changes'] = {'set': sets, 'remove': removes}
        print('info.plist: set %d keys, remove %d keys' % (len(sets), len(removes)))
        print('members: remove %d, add %d' % (len(only_a), len(only_b)))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    index_path = os.path.join(os.path.dirname(args.out), 'index.json')
    with open(index_path, 'w', encoding='utf-8') as fh:
        json.dump({'schema': 1, 'default': args.id, 'sets': [
            {'id': args.id, 'file': os.path.basename(args.out),
             'title': args.title}]}, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    print('wrote: %s' % args.out)
    print('wrote: %s' % index_path)


if __name__ == '__main__':
    main()
