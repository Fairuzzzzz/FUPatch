#!/usr/bin/env python3
"""Create a native-iPad compatibility experiment from a verified MHFU IPA.

Only Info.plist's UIDeviceFamily changes. The executable must already match
the verified result for the selected device profile.
"""
import argparse
import hashlib
import json
import os
import plistlib
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mhfu_patch import engine, manifest, ziprewrite  # noqa: E402

DEFAULT_PROFILE_ID = 'iphone12-14'


class ExperimentError(RuntimeError):
    pass


def _same_path(left, right):
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right))


def _info_member(names):
    matches = []
    for name in names:
        parts = name.split('/')
        if (len(parts) == 3 and parts[0] == 'Payload'
                and parts[1].endswith('.app') and parts[2] == 'Info.plist'):
            matches.append(name)
    if len(matches) != 1:
        raise ExperimentError(
            'expected exactly one Payload/*.app/Info.plist; found %d'
            % len(matches))
    return matches[0]


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _sha_file_range(path, offset, length):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        fh.seek(offset)
        remaining = length
        while remaining:
            chunk = fh.read(min(1 << 20, remaining))
            if not chunk:
                raise ExperimentError('truncated compressed member data')
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _compressed_payload_sha(path, entry):
    with open(path, 'rb') as fh:
        fh.seek(entry['off'])
        header = fh.read(30)
        if header[:4] != ziprewrite.LH_SIG:
            raise ExperimentError('invalid local header for %r' % entry['name'])
        name_len, extra_len = struct.unpack('<HH', header[26:30])
        data_offset = entry['off'] + 30 + name_len + extra_len
    return _sha_file_range(path, data_offset, entry['csize'])


def _archive_report(source, output):
    before = ziprewrite.read_index(source)
    after = ziprewrite.read_index(output)
    old = {entry['name']: entry for entry in before['entries']}
    new = {entry['name']: entry for entry in after['entries']}
    old_names, new_names = set(old), set(new)
    added = sorted(name.decode('utf-8', 'replace')
                   for name in new_names - old_names)
    removed = sorted(name.decode('utf-8', 'replace')
                     for name in old_names - new_names)
    content_changed = []
    metadata_changed = []

    metadata_fields = (
        'vmade', 'vneed', 'flags', 'method', 'mtime', 'mdate', 'extra',
        'comment', 'dstart', 'iattr', 'eattr',
    )
    for name in sorted(old_names & new_names):
        left, right = old[name], new[name]
        left_payload = _compressed_payload_sha(source, left)
        right_payload = _compressed_payload_sha(output, right)
        content_diff = (
            left['crc'] != right['crc']
            or left['usize'] != right['usize']
            or left['method'] != right['method']
            or left_payload != right_payload
        )
        display_name = name.decode('utf-8', 'replace')
        if content_diff:
            content_changed.append(display_name)
        changed = [
            field for field in metadata_fields
            if left[field] != right[field]
        ]
        if changed:
            metadata_changed.append({
                'member': display_name,
                'fields': changed,
            })

    return {
        'archive_size_before': before['size'],
        'archive_size_after': after['size'],
        'archive_comment_changed': before['comment'] != after['comment'],
        'members_before': len(old),
        'members_after': len(new),
        'added_members': added,
        'removed_members': removed,
        'content_changed_members': content_changed,
        'metadata_changed_members': metadata_changed,
    }


def _check_verified_input(ipa_path, selected_manifest, patch_directory=None,
                          profile_id=DEFAULT_PROFILE_ID):
    info = engine.look(
        ipa_path, profile_id=profile_id, directory=patch_directory)
    expected_sha = manifest.profile_result_sha(
        selected_manifest, profile_id)
    if (not info['supported'] or info['match'] != 'result'
            or info.get('profile') != profile_id
            or info['arm64_sha256'] != expected_sha
            or info['profile_result_sha256'] != expected_sha):
        raise ExperimentError(
            'input is not a verified %s IPA (match=%r, arm64 sha=%s)'
            % (profile_id, info.get('match'), info.get('arm64_sha256')))
    return info


def create_experiment(ipa_path, out_path, patch_directory=None,
                      profile_id=DEFAULT_PROFILE_ID):
    """Write and verify a plist-only native-iPad experiment."""
    ipa_path = os.path.abspath(ipa_path)
    out_path = os.path.abspath(out_path)
    if not os.path.isfile(ipa_path):
        raise ExperimentError('input IPA not found: %s' % ipa_path)
    if _same_path(ipa_path, out_path):
        raise ExperimentError('output file must differ from the source IPA')
    if os.path.exists(out_path):
        raise ExperimentError('output file already exists: %s' % out_path)
    out_dir = os.path.dirname(out_path) or '.'
    if not os.path.isdir(out_dir):
        raise ExperimentError('output folder does not exist: %s' % out_dir)
    tmp_path = out_path + '.part'
    if os.path.exists(tmp_path):
        raise ExperimentError('temporary output already exists: %s' % tmp_path)

    selected_manifest = manifest.load_set('mhfu-ios', patch_directory)
    source_info = _check_verified_input(
        ipa_path, selected_manifest, patch_directory, profile_id)
    index = ziprewrite.read_index(ipa_path)
    names = ziprewrite.names(index)
    plist_name = _info_member(names)
    original_plist_bytes = ziprewrite.read_member(ipa_path, plist_name)
    original_plist = plistlib.loads(original_plist_bytes)
    if original_plist.get('UIDeviceFamily') != [1]:
        raise ExperimentError(
            'expected input UIDeviceFamily [1], found %r'
            % original_plist.get('UIDeviceFamily'))
    exe_member = (plist_name.rsplit('/', 1)[0] + '/'
                  + original_plist['CFBundleExecutable'])
    source_executable_sha = _sha256(
        ziprewrite.read_member(ipa_path, exe_member))

    modified_plist = dict(original_plist)
    modified_plist['UIDeviceFamily'] = [1, 2]
    replacement = plistlib.dumps(
        modified_plist, fmt=plistlib.FMT_BINARY, sort_keys=True)
    replacements = {plist_name.encode('utf-8'): replacement}

    try:
        ziprewrite.rewrite(ipa_path, tmp_path, replacements=replacements)
        with zipfile.ZipFile(tmp_path) as zf:
            corrupt_member = zf.testzip()
            if corrupt_member is not None:
                raise ExperimentError(
                    'output ZIP CRC check failed for %r' % corrupt_member)
            output_plist = plistlib.loads(zf.read(plist_name))
            output_executable = zf.read(exe_member)

        if output_plist.get('UIDeviceFamily') != [1, 2]:
            raise ExperimentError('output UIDeviceFamily is not [1, 2]')
        expected_plist = dict(original_plist)
        expected_plist['UIDeviceFamily'] = [1, 2]
        if output_plist != expected_plist:
            raise ExperimentError(
                'output Info.plist has unexpected changes beyond UIDeviceFamily')

        executable_sha = _sha256(output_executable)
        if executable_sha != source_executable_sha:
            raise ExperimentError(
                'output executable SHA-256 differs from verified input')

        output_info = _check_verified_input(
            tmp_path, selected_manifest, patch_directory, profile_id)
        if output_info['arm64_sha256'] != source_info['arm64_sha256']:
            raise ExperimentError('verified arm64 slice SHA-256 changed')

        archive = _archive_report(ipa_path, tmp_path)
        expected_info_path = plist_name
        unexpected_content_changes = [
            name for name in archive['content_changed_members']
            if name != expected_info_path
        ]
        if (archive['added_members'] or archive['removed_members']
                or unexpected_content_changes
                or archive['archive_comment_changed']):
            raise ExperimentError(
                'archive content changed unexpectedly: %s'
                % json.dumps(archive, sort_keys=True))

        # os.rename does not replace an existing destination on Windows.
        # The temporary is in the same directory, so publication is atomic.
        os.rename(tmp_path, out_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return {
        'input': ipa_path,
        'output': out_path,
        'profile': profile_id,
        'uid_device_family_before': [1],
        'uid_device_family_after': [1, 2],
        'executable_sha256_before': source_executable_sha,
        'executable_sha256_after': executable_sha,
        'info_plist_changed_only_uid_device_family': True,
        'archive_differences': archive,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ipa', required=True, help='verified patched input IPA')
    parser.add_argument('--out', required=True, help='new experimental output IPA')
    parser.add_argument(
        '--patches', help='patch manifest directory (defaults to repository patches)')
    parser.add_argument(
        '--profile', default=DEFAULT_PROFILE_ID,
        help='verified profile used to build the input (default: %(default)s)')
    args = parser.parse_args(argv)
    try:
        report = create_experiment(
            args.ipa, args.out, args.patches, args.profile)
    except (ExperimentError, engine.PatchError, manifest.ManifestError,
            ziprewrite.ZipError, OSError, ValueError) as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
