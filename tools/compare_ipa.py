#!/usr/bin/env python3
"""Compare two IPAs by member set, member CRC/size and Info.plist content.

The browser engine writes Info.plist as XML while the Python engine writes
binary, so that member is compared by parsed content instead of CRC. Every
other member must match exactly (name, CRC, uncompressed size).
"""
import hashlib
import plistlib
import sys
import zipfile

EXEMPT_CRC = {"Info.plist"}


def _exe(zf):
    info = None
    for name in zf.namelist():
        parts = name.split("/")
        if len(parts) == 3 and parts[0] == "Payload" and parts[2] == "Info.plist":
            info = name
            break
    if info is None:
        raise SystemExit("Info.plist not found")
    plist = plistlib.loads(zf.read(info))
    app = info.rsplit("/", 1)[0]
    return app + "/" + plist["CFBundleExecutable"], plist


def main(left, right):
    za, zb = zipfile.ZipFile(left), zipfile.ZipFile(right)
    ia = {i.filename: i for i in za.infolist()}
    ib = {i.filename: i for i in zb.infolist()}
    problems = []

    missing = sorted(set(ia) - set(ib))
    extra = sorted(set(ib) - set(ia))
    if missing:
        problems.append("only in %s: %s" % (left, missing[:8]))
    if extra:
        problems.append("only in %s: %s" % (right, extra[:8]))

    common = sorted(set(ia) & set(ib))
    crc_diffs = [n for n in common if ia[n].CRC != ib[n].CRC]
    size_diffs = [n for n in common if ia[n].file_size != ib[n].file_size]
    unexpected_crc = [n for n in crc_diffs if not n.endswith(tuple(EXEMPT_CRC))]
    unexpected_size = [n for n in size_diffs if not n.endswith(tuple(EXEMPT_CRC))]
    if unexpected_crc:
        problems.append("CRC differs: %s" % unexpected_crc[:8])
    if unexpected_size:
        problems.append("size differs: %s" % unexpected_size[:8])

    ea, pa = _exe(za)
    eb, pb = _exe(zb)
    da, db = za.read(ea), zb.read(eb)
    sha_a = hashlib.sha256(da).hexdigest()
    sha_b = hashlib.sha256(db).hexdigest()
    if sha_a != sha_b:
        problems.append("executable differs: %s != %s" % (sha_a[:16], sha_b[:16]))
    if ea != eb:
        problems.append("executable name differs: %s != %s" % (ea, eb))

    plist_diffs = []
    for key in sorted(set(pa) | set(pb)):
        if pa.get(key) != pb.get(key):
            plist_diffs.append(key)
    if plist_diffs:
        problems.append("Info.plist keys differ: %s" % plist_diffs[:8])

    print("members   : %d / %d" % (len(ia), len(ib)))
    print("executable: %s" % ea)
    print("binary sha: %s" % sha_a)
    print("crc diffs : %s" % (crc_diffs if crc_diffs else "none"))
    print("plist keys: %s" % ("identical" if not plist_diffs else plist_diffs))
    if problems:
        print("\nMISMATCH")
        for problem in problems:
            print("  - " + problem)
        return 1
    print("\nOK: identical content (member set, CRC, executable, Info.plist)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: compare_ipa.py <a.ipa> <b.ipa>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
