"""Package changes: remove/add members, rewrite Info.plist."""
import fnmatch
import os
import plistlib


class PackageError(ValueError):
    pass


def resolve_removals(spec, names):
    """Member names to remove according to the spec (exact + glob)."""
    spec = spec or {}
    exact = set(spec.get('exact', []))
    globs = spec.get('globs', [])
    out = set()
    for name in names:
        if name in exact:
            out.add(name)
            continue
        for pattern in globs:
            if fnmatch.fnmatchcase(name, pattern):
                out.add(name)
                break
    return out


def resolve_additions(spec, names, base_dir):
    """Members to add, together with their contents."""
    out = []
    for item in spec or []:
        name = item.get('name')
        if not name:
            raise PackageError('members_add entry has no name')
        if name in names:
            continue
        data = item.get('data')
        if data is None:
            source = item.get('source')
            if not source:
                raise PackageError('member %s has no source/data' % name)
            path = source if os.path.isabs(source) else os.path.join(base_dir, source)
            if not os.path.exists(path):
                raise PackageError('fixture not found: %s' % path)
            with open(path, 'rb') as fh:
                data = fh.read()
        if isinstance(data, str):
            data = data.encode('utf-8')
        out.append((name, data))
    return out


def patch_info_plist(raw, manifest, version, marker_suffix=None):
    pl = plistlib.loads(raw)
    changes = manifest.get('info_changes') or {}
    for key in changes.get('remove', []):
        pl.pop(key, None)
    for key, value in (changes.get('set') or {}).items():
        pl[key] = value
    pl['CFBundleShortVersionString'] = version
    pl['CFBundleVersion'] = version
    marker_key = (manifest.get('version') or {}).get('marker_key')
    if marker_key:
        marker = manifest['id']
        if marker_suffix:
            marker += ' ' + marker_suffix
        pl[marker_key] = marker
    return plistlib.dumps(pl, fmt=plistlib.FMT_BINARY, sort_keys=True)
