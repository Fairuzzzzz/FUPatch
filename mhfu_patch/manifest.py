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


def default_profile(m):
    """Return the manifest's default device profile, if it has one."""
    profiles = m.get('profiles') or []
    for profile in profiles:
        if profile.get('default'):
            return profile
    return profiles[0] if profiles else None


def select_profile(m, profile_id=None):
    """Return a profile by id, or the default profile when id is omitted."""
    profiles = m.get('profiles') or []
    if not profiles:
        if profile_id:
            raise ManifestError('profile %r not found' % profile_id)
        return None
    if profile_id:
        for profile in profiles:
            if profile.get('id') == profile_id:
                return profile
        raise ManifestError('profile %r not found' % profile_id)
    profile = default_profile(m)
    if profile is None:
        raise ManifestError('manifest has no default profile')
    return profile


def profile_steps(m, profile=None):
    """Base steps with profile replacements, followed by extra profile steps."""
    if isinstance(profile, str):
        profile = select_profile(m, profile)
    if profile is None:
        profile = default_profile(m)
    steps = [dict(step) for step in m['binary_steps']]
    if profile:
        overrides = {
            item.get('id'): item.get('replace')
            for item in (profile.get('overrides') or [])
        }
        if overrides:
            for index, step in enumerate(steps):
                if step['id'] in overrides:
                    step = dict(step)
                    step['replace'] = overrides[step['id']]
                    steps[index] = step
        steps.extend(profile.get('steps') or [])
    return steps


def profile_result_sha(m, profile=None):
    """The expected result sha for the selected profile."""
    if isinstance(profile, str):
        profile = select_profile(m, profile)
    if profile is None:
        profile = default_profile(m)
    if profile and profile.get('result_sha256'):
        return profile['result_sha256'].lower()
    return m['slice']['result_sha256'].lower()


def find_profile_for_sha(m, sha):
    """Return the profile whose result binary has this sha."""
    sha = (sha or '').lower()
    for profile in m.get('profiles') or []:
        if (profile.get('result_sha256') or '').lower() == sha:
            return profile
    return None


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
    if not isinstance(result, str) or len(result) != 64:
        raise ManifestError('result_sha256 is not a sha256')
    try:
        int(result, 16)
    except ValueError:
        raise ManifestError('result_sha256 is not hexadecimal')
    base = int(sl['vaddr_base'], 0)
    known_features = {f.get('id') for f in m.get('features', [])}
    spans = []
    all_ids = set()
    for step in m['binary_steps']:
        for key in ('id', 'vaddr', 'expect', 'replace'):
            if key not in step:
                raise ManifestError('step missing key %r' % key)
        if step['id'] in all_ids:
            raise ManifestError('duplicate step id %s' % step['id'])
        all_ids.add(step['id'])
        if known_features and step.get('feature') not in known_features:
            raise ManifestError('step %s: unknown feature %r'
                                % (step['id'], step.get('feature')))
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
    base_by_id = {step['id']: step for step in m['binary_steps']}

    profiles = m.get('profiles')
    if profiles is None:
        return
    if not isinstance(profiles, list):
        raise ManifestError('profiles must be a list')
    profile_ids = set()
    default_count = 0
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ManifestError('profile must be an object')
        for key in ('id', 'label', 'result_sha256'):
            if not profile.get(key):
                raise ManifestError('profile missing key %r' % key)
        pid = profile['id']
        if pid in profile_ids:
            raise ManifestError('duplicate profile id %s' % pid)
        profile_ids.add(pid)
        presult = profile['result_sha256']
        if not isinstance(presult, str) or len(presult) != 64:
            raise ManifestError('profile %s: result_sha256 is not a sha256' % pid)
        try:
            int(presult, 16)
        except ValueError:
            raise ManifestError('profile %s: result_sha256 is not hexadecimal' % pid)
        overrides = profile.get('overrides', [])
        if not isinstance(overrides, list):
            raise ManifestError('profile %s: overrides must be a list' % pid)
        seen_overrides = set()
        for override in overrides:
            if not isinstance(override, dict):
                raise ManifestError('profile %s: override must be an object' % pid)
            for key in ('id', 'replace'):
                if key not in override:
                    raise ManifestError(
                        'profile %s override missing key %r' % (pid, key))
            oid = override['id']
            if oid not in base_by_id:
                raise ManifestError(
                    'profile %s: override target %r is not a base step'
                    % (pid, oid))
            if oid in seen_overrides:
                raise ManifestError(
                    'profile %s: duplicate override for %s' % (pid, oid))
            seen_overrides.add(oid)
            rep = bytes.fromhex(override['replace'])
            expected_len = len(base_by_id[oid]['replace']) // 2
            if len(rep) != expected_len:
                raise ManifestError(
                    'profile %s: override %s has wrong length' % (pid, oid))

        steps = profile.get('steps', [])
        if not isinstance(steps, list):
            raise ManifestError('profile %s: steps must be a list' % pid)
        pspans = []
        for step in steps:
            for key in ('id', 'vaddr', 'expect', 'replace'):
                if key not in step:
                    raise ManifestError('profile %s step missing key %r' % (pid, key))
            if step['id'] in all_ids:
                raise ManifestError('duplicate step id %s' % step['id'])
            all_ids.add(step['id'])
            if known_features and step.get('feature') not in known_features:
                raise ManifestError('step %s: unknown feature %r'
                                    % (step['id'], step.get('feature')))
            exp = bytes.fromhex(step['expect'])
            rep = bytes.fromhex(step['replace'])
            if len(exp) != len(rep):
                raise ManifestError('step %s: expect/replace length mismatch'
                                    % step['id'])
            start = int(step['vaddr'], 0) - base
            if start < 0:
                raise ManifestError('step %s: vaddr outside the slice'
                                    % step['id'])
            pspans.append((start, start + len(exp), step['id']))
        pspans.sort()
        for (a0, a1, aid), (b0, b1, bid) in zip(pspans, pspans[1:]):
            if b0 < a1:
                raise ManifestError('profile %s steps %s and %s overlap'
                                    % (pid, aid, bid))
        # Extra profile steps must not sit on a base step; base constants are
        # changed through ``overrides`` so the base step still verifies.
        for a0, a1, aid in pspans:
            for b0, b1, bid in spans:
                if a0 < b1 and b0 < a1:
                    raise ManifestError(
                        'profile %s step %s overlaps base step %s'
                        % (pid, aid, bid))
        if profile.get('default'):
            default_count += 1
            if steps or overrides:
                raise ManifestError(
                    'default profile %s must not override anything' % pid)
            if presult.lower() != result.lower():
                raise ManifestError(
                    'default profile %s must keep the base result sha' % pid)
    if default_count != 1:
        raise ManifestError('manifest must define exactly one default profile')


def sha_sets(m):
    sl = m['slice']
    results = [sl['result_sha256'].lower()]
    for profile in m.get('profiles') or []:
        value = (profile.get('result_sha256') or '').lower()
        if value and value not in results:
            results.append(value)
    return {
        'source': [s.lower() for s in sl.get('source_sha256', [])],
        'intermediate': [s.lower() for s in sl.get('intermediate_sha256', [])],
        'result': results,
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
