
"""Build the experimental Phase 14 MHFU iPad executable patch.

This developer tool requires macOS and Xcode command-line tools.
It does not modify the input executable or package an IPA.
"""

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

try:
    from .arm64_encoding import encode_branch, instruction_bytes
except ImportError:
    from arm64_encoding import encode_branch, instruction_bytes


BASE = 0x100000000

SOURCE_SHA256 = (
    "25ff0f7ea91f58b2e1531080d9a9c55e"
    "9363f7a66031b1da89abf193826f92b4"
)

RESULT_SHA256 = (
    "ff26548f0e32f240e01c30e2e172bd00"
    "5087b43ea1a517527bc84668339be10e"
)

UI_LAYOUT_HOOK = 0x1003A35D0
UI_LAYOUT_CAVE = 0x10049E900
UI_LAYOUT_SIZE = 200

GESTURE_HOOK = 0x1003545D0
GESTURE_CAVE = 0x10049EA00
GESTURE_SIZE = 156

ASM_DIR = Path(__file__).resolve().parent / "asm"

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
LC_SEGMENT_64 = 0x19
MH_OBJECT = 0x1


class BuildError(RuntimeError):
    """Raised when patch generation or validation fails."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text_section(data: bytes) -> bytes:
    """Extract relocation-free __TEXT,__text from an ARM64 object."""

    if len(data) < 32:
        raise BuildError("Truncated Mach-O header")

    magic, cpu, _, filetype, ncmds, sizeofcmds, _, _ = (
        struct.unpack_from("<8I", data, 0)
    )

    if magic != MH_MAGIC_64:
        raise BuildError("Expected a little-endian 64-bit Mach-O")

    if cpu != CPU_TYPE_ARM64:
        raise BuildError("Expected ARM64 architecture")

    if filetype != MH_OBJECT:
        raise BuildError("Expected a Mach-O object file")

    commands_end = 32 + sizeofcmds

    if commands_end > len(data):
        raise BuildError("Truncated load commands")

    offset = 32
    sections = []

    for _ in range(ncmds):

        if offset + 8 > commands_end:
            raise BuildError("Truncated load command")

        cmd, cmdsize = struct.unpack_from("<II", data, offset)

        if cmdsize < 8 or offset + cmdsize > commands_end:
            raise BuildError("Invalid load command size")

        if cmd == LC_SEGMENT_64:

            if cmdsize < 72:
                raise BuildError("Truncated segment command")

            nsects = struct.unpack_from(
                "<I", data, offset + 64
            )[0]

            if 72 + nsects * 80 > cmdsize:
                raise BuildError("Truncated section table")

            for i in range(nsects):

                section = offset + 72 + i * 80

                sectname = data[section:section + 16]
                segname = data[section + 16:section + 32]

                sectname = sectname.rstrip(b"\x00")
                segname = segname.rstrip(b"\x00")

                if sectname != b"__text" or segname != b"__TEXT":
                    continue

                size = struct.unpack_from(
                    "<Q", data, section + 40
                )[0]

                fileoff = struct.unpack_from(
                    "<I", data, section + 48
                )[0]

                nreloc = struct.unpack_from(
                    "<I", data, section + 60
                )[0]

                if nreloc:
                    raise BuildError(
                        "Assembly contains unresolved relocations"
                    )

                if fileoff + size > len(data):
                    raise BuildError("Truncated text section")

                sections.append(
                    data[fileoff:fileoff + size]
                )

        offset += cmdsize

    if len(sections) != 1:
        raise BuildError("Expected exactly one __TEXT,__text section")

    return sections[0]


def assemble(source: Path) -> bytes:
    """Compile an assembly source and return its machine-code bytes."""

    if not source.is_file():
        raise BuildError(f"Assembly source not found: {source}")

    with tempfile.TemporaryDirectory(
        prefix="mhfu-ipad-"
    ) as directory:

        obj = Path(directory) / "helper.o"

        command = [
            "xcrun",
            "clang",
            "-arch",
            "arm64",
            "-c",
            str(source),
            "-o",
            str(obj),
        ]

        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BuildError(
                f"Assembly failed: {source.name}"
            ) from exc

        return extract_text_section(obj.read_bytes())


def make_step(
    step_id: str,
    address: int,
    expected: bytes,
    replacement: bytes,
) -> dict:

    if len(expected) != len(replacement):
        raise BuildError("Patch lengths do not match")

    return {
        "id": step_id,
        "vaddr": f"0x{address:X}",
        "expect": expected.hex(),
        "replace": replacement.hex(),
    }


def build_steps(
    ui_layout: bytes,
    gesture: bytes,
) -> list[dict]:
    """Construct the six verified binary patch steps."""

    if UI_LAYOUT_CAVE + len(ui_layout) > GESTURE_CAVE:
        raise BuildError("UI layout helper overlaps gesture helper")

    if len(ui_layout) != UI_LAYOUT_SIZE:
        raise BuildError("Unexpected UI layout helper size")

    if len(gesture) != GESTURE_SIZE:
        raise BuildError("Unexpected gesture helper size")

    ui_layout_branch = instruction_bytes(
        encode_branch(UI_LAYOUT_HOOK, UI_LAYOUT_CAVE)
    )

    gesture_branch = instruction_bytes(
        encode_branch(GESTURE_HOOK, GESTURE_CAVE)
    )

    return [
        make_step(
            "ipad.ui_layout.hook",
            UI_LAYOUT_HOOK,
            bytes.fromhex("880080b9"),
            ui_layout_branch,
        ),
        make_step(
            "ipad.ui_layout.cave",
            UI_LAYOUT_CAVE,
            bytes(UI_LAYOUT_SIZE),
            ui_layout,
        ),
        make_step(
            "ipad.gesture.hook",
            GESTURE_HOOK,
            bytes.fromhex("481a0090"),
            gesture_branch,
        ),
        make_step(
            "ipad.gesture.cave",
            GESTURE_CAVE,
            bytes(GESTURE_SIZE),
            gesture,
        ),
        make_step(
            "ipad.loading.glyph_dimension", 0x100441CC4,
            bytes.fromhex("0110271e"), bytes.fromhex("0190261e"),  # fmov s1, #20
        ),
        # This instruction is inside the common safe-area.34 replacement.
        make_step(
            "ipad.loading.horizontal_origin", 0x10049E628,
            bytes.fromhex("7302090b"), bytes.fromhex("7302094b"),  # sub w19, w19, w9
        ),
    ]


def apply_steps(
    source: bytes,
    steps: list[dict],
) -> bytes:
    """Apply fixed-size replacements with strict byte verification."""

    data = bytearray(source)
    occupied = []

    for step in steps:

        address = int(step["vaddr"], 0)
        offset = address - BASE

        expected = bytes.fromhex(step["expect"])
        replacement = bytes.fromhex(step["replace"])

        if not expected or len(expected) != len(replacement):
            raise BuildError(f"Invalid patch: {step['id']}")

        end = offset + len(expected)

        if offset < 0 or end > len(data):
            raise BuildError(
                f"Patch outside executable: {step['id']}"
            )

        for previous_start, previous_end in occupied:

            if offset < previous_end and end > previous_start:
                raise BuildError(
                    f"Overlapping patch: {step['id']}"
                )

        occupied.append((offset, end))

        actual = bytes(data[offset:end])

        if actual != expected:
            raise BuildError(
                f"Original bytes mismatch: {step['id']}\n"
                f"Address: {address:#x}\n"
                f"Expected: {expected.hex()}\n"
                f"Actual:   {actual.hex()}"
            )

        data[offset:end] = replacement

    return bytes(data)


def build_patch(source: bytes) -> tuple[bytes, list[dict]]:
    """Build the Phase 14 executable from the verified common baseline."""

    actual_sha = sha256(source)

    if actual_sha != SOURCE_SHA256:
        raise BuildError(
            "Unsupported baseline executable\n"
            f"Expected: {SOURCE_SHA256}\n"
            f"Actual:   {actual_sha}"
        )

    ui_layout = assemble(ASM_DIR / "ui_layout_hook.s")
    gesture = assemble(ASM_DIR / "gesture_hook.s")

    steps = build_steps(ui_layout, gesture)
    result = apply_steps(source, steps)

    actual_sha = sha256(result)

    if actual_sha != RESULT_SHA256:
        raise BuildError(
            "Result does not match the expected Phase 14 executable\n"
            f"Expected: {RESULT_SHA256}\n"
            f"Actual:   {actual_sha}"
        )

    return result, steps


def main():

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "source",
        type=Path,
        help="Verified baseline ARM64 executable",
    )

    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="New patched executable",
    )

    parser.add_argument(
        "--steps",
        type=Path,
        help="Optional JSON output containing binary patch steps",
    )

    args = parser.parse_args()

    try:

        paths = [args.source.resolve(), args.out.resolve()]

        if args.steps is not None:
            paths.append(args.steps.resolve())

        if len(paths) != len(set(paths)):
            raise BuildError("Input and output paths must differ")

        outputs = [args.out]

        if args.steps is not None:
            outputs.append(args.steps)

        for path in outputs:

            if path.exists():
                raise BuildError(f"Output already exists: {path}")

            if not path.parent.is_dir():
                raise BuildError(
                    f"Output directory does not exist: {path.parent}"
                )

        source = args.source.read_bytes()

        print("Source SHA-256:", sha256(source))

        result, steps = build_patch(source)

        with args.out.open("xb") as file:
            file.write(result)

        args.out.chmod(args.source.stat().st_mode & 0o777)

        if args.steps is not None:

            with args.steps.open("x", encoding="utf-8") as file:
                json.dump(steps, file, indent=2)
                file.write("\n")

    except (BuildError, OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print()
    print("Combined patch reproduced successfully")
    print("UI layout helper:", UI_LAYOUT_SIZE, "bytes")
    print("Gesture helper:", GESTURE_SIZE, "bytes")
    print("Binary patch steps:", len(steps))
    print("Output SHA-256:", sha256(result))
    print("Output:", args.out.resolve())

    if args.steps is not None:
        print("Patch steps:", args.steps.resolve())


if __name__ == "__main__":
    main()
