"""CLI: inspect | patch | serve."""
import argparse
import json
import os
import sys

from . import APP_NAME, __version__, engine
from . import manifest as mf
from . import server


def _mb(n):
    return (n or 0) / 1e6


def cmd_inspect(args):
    info = engine.look(os.path.expanduser(args.ipa), patch_set=args.patch_set,
                       directory=args.patches)
    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0 if info['supported'] else 2
    print('%s %s' % (APP_NAME, __version__))
    print('IPA        : %s (%.1f MB, %d member)'
          % (info['ipa'], _mb(info['size']), info['members']))
    print('App        : %s (%s) versi %s'
          % (info['app_name'], info['bundle_id'], info['info_version']))
    print('Biner      : %s, %d slice' % (info['exe_kind'], len(info['slices'])))
    for sl in info['slices']:
        flag = ' (terenkripsi)' if sl['encrypted'] else ''
        print('  - %-7s %8.1f MB  sha256 %s%s'
              % (sl['arch'], _mb(sl['size']), sl['sha256'][:16], flag))
    if info['supported']:
        print('Patch set  : %s — %s'
              % (info['patch_set'], info['patch_title']))
        print('Langkah    : %d total, %d belum, %d sudah'
              % (info['steps_total'], info['steps_pending'],
                 info['steps_applied']))
        if info['remove_pending']:
            print('Hapus      : %d member' % len(info['remove_pending']))
        if info['add_pending']:
            print('Tambah     : %s' % ', '.join(info['add_pending']))
        if (not info['steps_pending'] and not info['remove_pending']
                and not info['add_pending']):
            print('Status     : sudah dipatch lengkap '
                  '(ganti nomor versi untuk membangun ulang)')
        else:
            print('Status     : siap dipatch')
        return 0
    print('Status     : TIDAK DIDUKUNG')
    print('  %s' % (info['reason'] or 'alasan tidak diketahui'))
    return 2


def cmd_patch(args):
    ipa = os.path.expanduser(args.ipa)
    out = os.path.expanduser(args.out)
    state = {'phase': None, 'pct': -10}

    def on_event(ev):
        phase, pct = ev.get('phase'), ev.get('pct', 0)
        if phase == state['phase'] and pct - state['pct'] < 5:
            return
        state['phase'] = phase
        state['pct'] = pct
        detail = ev.get('detail') or ''
        sys.stdout.write('\r[%3d%%] %-14s %-58s' % (pct, phase, detail[:58]))
        sys.stdout.flush()

    try:
        report = engine.patch(ipa, out, version=args.version,
                              keep_fat=args.keep_fat, dry_run=args.dry_run,
                              on_event=on_event, directory=args.patches,
                              patch_set=args.patch_set, force=args.force)
    except engine.StepMismatch as exc:
        print('\nGAGAL: %s' % exc, file=sys.stderr)
        return 3
    except engine.PatchError as exc:
        print('\nGAGAL: %s' % exc, file=sys.stderr)
        return 4 if 'ruang disk' in str(exc) else 2
    print()
    if report.get('dry_run'):
        print('DRY RUN — tidak ada file ditulis')
        print('  versi    : %s -> %s' % (report['old_version'], report['version']))
        print('  langkah  : %d diterapkan, %d dilewati'
              % (len(report['applied']), len(report['skipped'])))
        print('  hapus    : %d member' % len(report['removed']))
        print('  tambah   : %s' % (', '.join(report['added']) or '-'))
        print('  member   : %d' % report['members'])
        return 0
    print('SELESAI dalam %.1f s' % report['duration'])
    print('  hasil    : %s (%.1f MB, %d member)'
          % (report['out'], _mb(report['size']), report['members']))
    print('  versi    : %s -> %s' % (report['old_version'], report['version']))
    print('  biner    : %s, sha slice %s'
          % (report['exe_kind_out'], report['slice_sha256']))
    print('  langkah  : %d diterapkan, %d dilewati'
          % (len(report['applied']), len(report['skipped'])))
    print('  paket    : %d member dihapus, %d ditambah'
          % (len(report['removed']), len(report['added'])))
    print('  sha IPA  : %s' % report.get('output_sha256', ''))
    print('\nPasang lewat AltStore/Sideloadly (akan ditandatangani ulang).')
    return 0


def cmd_serve(args):
    server.serve(host=args.host, port=args.port, open_browser=args.open,
                 patch_dir=args.patches)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog='mhfu_patch', description=APP_NAME)
    ap.add_argument('--version-info', action='version',
                    version='%s %s' % (APP_NAME, __version__))
    ap.add_argument('--patches', help='folder patch set (default: patches/)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('inspect', help='periksa IPA tanpa mengubah')
    p.add_argument('--ipa', required=True)
    p.add_argument('--patch-set')
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser('patch', help='patch IPA')
    p.add_argument('--ipa', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--version', help='versi baru (default: dari patch set)')
    p.add_argument('--keep-fat', action='store_true',
                   help='pertahankan biner FAT (default: thin arm64)')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true', help='timpa file keluaran')
    p.add_argument('--patch-set')
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser('serve', help='jalankan UI web lokal')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--open', action='store_true')
    p.set_defaults(func=cmd_serve)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, 'patches', None):
        args.patches = os.path.abspath(os.path.expanduser(args.patches))
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
