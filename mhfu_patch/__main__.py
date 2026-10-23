"""CLI: inspect | patch | serve."""
import argparse
import json
import os
import sys

from . import APP_NAME, __version__, engine

PHASES = {
    'inspect': 'inspecting',
    'read': 'reading',
    'steps': 'patching',
    'plist': 'info.plist',
    'write': 'writing',
    'verify': 'verifying',
    'done': 'done',
}


def _mb(n):
    return (n or 0) / 1e6


def cmd_inspect(args):
    info = engine.look(os.path.expanduser(args.ipa), patch_set=args.patch_set,
                       directory=args.patches)
    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0 if info['supported'] else 2
    print('%s %s' % (APP_NAME, __version__))
    print('IPA        : %s (%.1f MB, %d files)'
          % (info['ipa'], _mb(info['size']), info['members']))
    print('App        : %s (%s) version %s'
          % (info['app_name'], info['bundle_id'], info['info_version']))
    print('Binary     : %s, %d slice(s)' % (info['exe_kind'], len(info['slices'])))
    for sl in info['slices']:
        flag = ' (encrypted)' if sl['encrypted'] else ''
        print('  - %-7s %8.1f MB  sha256 %s%s'
              % (sl['arch'], _mb(sl['size']), sl['sha256'][:16], flag))
    if info['supported']:
        print('Patch set  : %s — %s'
              % (info['patch_set'], info['patch_title']))
        print('Steps      : %d total, %d pending, %d applied'
              % (info['steps_total'], info['steps_pending'],
                 info['steps_applied']))
        if info['remove_pending']:
            print('Remove     : %d files' % len(info['remove_pending']))
        if info['add_pending']:
            print('Add        : %s' % ', '.join(info['add_pending']))
        if (not info['steps_pending'] and not info['remove_pending']
                and not info['add_pending']):
            print('Status     : already fully patched '
                  '(change the version to rebuild)')
        else:
            print('Status     : ready to patch')
        return 0
    print('Status     : NOT SUPPORTED')
    print('  %s' % (info['reason'] or 'unknown reason'))
    return 2


def cmd_patch(args):
    ipa = os.path.expanduser(args.ipa)
    out = os.path.expanduser(args.out)
    state = {'phase': None, 'pct': -10}

    def on_event(ev):
        phase = PHASES.get(ev.get('phase', ''), ev.get('phase', ''))
        pct = ev.get('pct', 0)
        if phase == state['phase'] and pct - state['pct'] < 5:
            return
        state['phase'] = phase
        state['pct'] = pct
        detail = ev.get('detail') or ''
        sys.stdout.write('\r[%3d%%] %-12s %-60s' % (pct, phase, detail[:60]))
        sys.stdout.flush()

    try:
        report = engine.patch(ipa, out, version=args.version,
                              keep_fat=args.keep_fat, dry_run=args.dry_run,
                              on_event=on_event, directory=args.patches,
                              patch_set=args.patch_set, force=args.force)
    except engine.StepMismatch as exc:
        print('\nFAILED: %s' % exc, file=sys.stderr)
        return 3
    except engine.PatchError as exc:
        print('\nFAILED: %s' % exc, file=sys.stderr)
        return 4 if 'disk space' in str(exc) else 2
    print()
    if report.get('dry_run'):
        print('DRY RUN — no file written')
        if report['old_version'] == report['version']:
        print('  version : %s (unchanged)' % report['version'])
    else:
        print('  version : %s -> %s' % (report['old_version'], report['version']))
        print('  steps   : %d applied, %d skipped'
              % (len(report['applied']), len(report['skipped'])))
        print('  package : %d removed, %d added'
              % (len(report['removed']), len(report['added'])))
        print('  files   : %d' % report['members'])
        return 0
    print('DONE in %.1f s' % report['duration'])
    print('  output  : %s (%.1f MB, %d files)'
          % (report['out'], _mb(report['size']), report['members']))
    if report['old_version'] == report['version']:
        print('  version : %s (unchanged)' % report['version'])
    else:
        print('  version : %s -> %s' % (report['old_version'], report['version']))
    print('  binary  : %s, slice sha %s'
          % (report['exe_kind_out'], report['slice_sha256']))
    print('  steps   : %d applied, %d skipped'
          % (len(report['applied']), len(report['skipped'])))
    print('  package : %d removed, %d added'
          % (len(report['removed']), len(report['added'])))
    print('  sha256  : %s' % report.get('output_sha256', ''))
    print('\nInstall with AltStore/Sideloadly (it will re-sign the IPA).')
    return 0


def cmd_serve(args):
    try:
        from . import server
    except ImportError:
        print('the web server needs FastAPI/uvicorn — run ./run.sh, '
              'it creates .venv automatically', file=sys.stderr)
        return 2
    server.serve(host=args.host, port=args.port, open_browser=args.open,
                 patch_dir=args.patches, workdir=args.workdir)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog='mhfu_patch', description=APP_NAME)
    ap.add_argument('--version-info', action='version',
                    version='%s %s' % (APP_NAME, __version__))
    ap.add_argument('--patches', help='patch-set folder (default: patches/)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('inspect', help='inspect an IPA without modifying it')
    p.add_argument('--ipa', required=True)
    p.add_argument('--patch-set')
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser('patch', help='patch an IPA')
    p.add_argument('--ipa', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--version', help='override the app version (default: keep the source version)')
    p.add_argument('--keep-fat', action='store_true',
                   help='keep the FAT binary (default: thin arm64)')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true', help='overwrite the output file')
    p.add_argument('--patch-set')
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser('serve', help='run the local web UI')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--open', action='store_true')
    p.add_argument('--workdir', help='folder for uploaded/output files')
    p.set_defaults(func=cmd_serve)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, 'patches', None):
        args.patches = os.path.abspath(os.path.expanduser(args.patches))
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
