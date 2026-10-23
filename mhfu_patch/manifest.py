"""Patch manifest: loading, validation, and slice sha matching."""
import json
import os

DEFAULT_PATCH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'patches')


class ManifestError(ValueError):
    pass


def patch_dir(directory=None):
    return directory or DEFAULT_PATCH_DIR


def load_index(directory=None):
    path = os.path.join(patch_dir(directory), 'index.json')
    with open(path, 'r', encoding='utf-8') as fh:
        idx = json.load(fh)
    for item in idx.get('sets', []):
        item.setdefault('file', item['id'] + '.json')
    return idx


def load_set(set_id=None, directory=None):
    idx = load_index(directory)
    if set_id is None:
        set_id = idx.get('default')
    for item in idx.get('sets', []):
        if item['id'] == set_id:
            with open(os.path.join(patch_dir(directory), item['file']), 'r',
                      encoding='utf-8') as fh:
                manifest = json.load(fh)
            validate(manifest)
            return manifest
    raise ManifestError('patch set %r not found in index' % set_id)


def validate(m):
    need = ('schema', 'id', 'slice', 'binary_steps')
    for key in need:
        if key not in m:
            raise ManifestError('manifest missing key %r' % key)
    if m['schema'] != 1:
        raise ManifestError('unsupported manifest schema: %r' % m['schema'])
    sl = m['slice']
    for key in ('vaddr_base', 'result_sha256'):
        if key not in sl:
            raise ManifestError('manifest missing slice.%s' % key)
    int(sl['vaddr_base'], 0)
    result = sl['result_sha256']
    if len(result) != 64:
        raise ManifestError('result_sha256 is not a sha256')
    base = int(sl['vaddr_base'], 0)
    spans = []
    for step in m['binary_steps']:
        for key in ('id', 'vaddr', 'expect', 'replace'):
            if key not in step:
                raise ManifestError('step missing key %r' % key)
        exp = bytes.fromhex(step['expect'])
        rep = bytes.fromhex(step['replace'])
        if len(exp) != len(rep):
            raise ManifestError('step %s: expect/replace length mismatch' % step['id'])
        start = int(step['vaddr'], 0) - base
        if start < 0:
            raise ManifestError('step %s: vaddr outside the slice' % step['id'])
        spans.append((start, start + len(exp), step['id']))
    spans.sort()
    for (a0, a1, aid), (b0, b1, bid) in zip(spans, spans[1:]):
        if b0 < a1:
            raise ManifestError('steps %s and %s overlap' % (aid, bid))


def sha_sets(m):
    sl = m['slice']
    return {
        'source': [s.lower() for s in sl.get('source_sha256', [])],
        'intermediate': [s.lower() for s in sl.get('intermediate_sha256', [])],
        'result': [sl['result_sha256'].lower()],
    }


def classify(m, sha):
    sha = (sha or '').lower()
    for kind, values in sha_sets(m).items():
        if sha in values:
            return kind
    return None


def find_set_for_sha(sha, directory=None):
    """Find the patch set that recognises this slice sha."""
    idx = load_index(directory)
    for item in idx.get('sets', []):
        try:
            m = load_set(item['id'], directory)
        except ManifestError:
            continue
        kind = classify(m, sha)
        if kind:
            return m, kind
    return None, None


def feature_titles(m):
    return {f['id']: f.get('title', f['id']) for f in m.get('features', [])}
