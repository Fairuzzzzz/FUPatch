"""Utilitas bersama untuk tes."""
import os
import plistlib
import struct
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

GOLDEN = os.environ.get('MHFU_GOLDEN', os.path.join(PARENT, 're_mhfu'))
ORIG_BIN = os.path.join(GOLDEN, 'mh_unite_original_arm64')
BASE186 = os.path.join(GOLDEN, 'mh_unite_base186')
FINAL = os.path.join(GOLDEN, 'mh_unite_c194')
ORIGINAL_IPA = os.environ.get(
    'MHFU_ORIGINAL_IPA',
    os.path.join(PARENT, 'MONSTER_HUNTER_FREEDOM_UNITE_for_iOS__CAPCOM___v1.00.11_'
                          'iPhone4_Univ_os60_-Widow.rc334d_902.ipa'))
PATCHED_IPA = os.environ.get('MHFU_PATCHED_IPA',
                             os.path.join(PARENT, 'MHFU_load194.ipa'))
RESULT_SHA = '25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4'


def have(*paths):
    return all(os.path.exists(p) for p in paths)


def make_synthetic_ipa(dst, exe_bytes, version='1.00.11', app='MH Unite'):
    pl = {
        'CFBundleExecutable': app,
        'CFBundleIdentifier': 'test.mhfu.local',
        'CFBundleName': app,
        'CFBundleShortVersionString': version,
        'CFBundleVersion': version,
        'UILaunchImageFile': 'LaunchImage',
    }
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('Payload/%s.app/Info.plist' % app,
                    plistlib.dumps(pl, fmt=plistlib.FMT_BINARY))
        zf.writestr('Payload/%s.app/%s' % (app, app), exe_bytes)
        zf.writestr('Payload/%s.app/data.bin' % app, b'harga' * 500)
        zf.writestr('Payload/%s.app/LaunchImage.png' % app, b'png-lama')
        zf.writestr('Payload/%s.app/_CodeSignature/CodeResources' % app, b'crc')
        zf.writestr('iTunesMetadata.plist', b'<plist/>')
    return dst


def arm64_stub(size=8192):
    """Mach-O arm64 minimal dengan sha yang tidak dikenal manifest."""
    head = struct.pack('<IIIIIIII', 0xFEEDFACF, 0x0100000C, 0, 2, 0, 0, 0, 0)
    return head + b'\0' * (size - len(head))


def member_map(path):
    with zipfile.ZipFile(path) as zf:
        return {i.filename: (i.CRC, i.file_size) for i in zf.infolist()}
