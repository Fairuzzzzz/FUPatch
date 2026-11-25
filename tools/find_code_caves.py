
"""Find zero-filled code-cave candidates in a binary.

Zero-filled regions are candidates only. Executable permissions,
section boundaries, and references must be verified separately.
"""

import argparse
import re
from pathlib import Path


def find_code_caves(
    data: bytes,
    start: int,
    end: int,
    min_size: int = 64,
    alignment: int = 4,
    base: int = 0x100000000,
) -> list[tuple[int, int]]:

    if not 0 <= start < end <= len(data):
        raise ValueError("Invalid search range")

    if min_size < 1:
        raise ValueError("Minimum size must be positive")

    if alignment < 1:
        raise ValueError("Alignment must be positive")

    candidates = []

    for match in re.finditer(rb"\x00+", data[start:end]):
        offset = start + match.start()
        address = base + offset

        padding = (-address) % alignment
        offset += padding

        size = len(match.group()) - padding
        size -= size % alignment

        if size >= min_size:
            candidates.append((offset, size))

    return candidates


def parse_int(value: str) -> int:
    return int(value, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "binary",
        type=Path,
        help="Path to the executable",
    )

    parser.add_argument(
        "--start",
        type=parse_int,
        default=0,
        help="Starting file offset (inclusive)",
    )

    parser.add_argument(
        "--end",
        type=parse_int,
        default=None,
        help="Ending file offset (exclusive)",
    )

    parser.add_argument(
        "--min-size",
        type=parse_int,
        default=64,
        help="Minimum candidate size in bytes",
    )

    parser.add_argument(
        "--alignment",
        type=parse_int,
        default=4,
        help="Required address and size alignment",
    )

    parser.add_argument(
        "--base",
        type=parse_int,
        default=0x100000000,
        help="Assumed virtual address base",
    )

    args = parser.parse_args()

    try:
        data = args.binary.read_bytes()

        end = (
            args.end if args.end is not None
            else len(data)
        )

        candidates = find_code_caves(
            data=data,
            start=args.start,
            end=end,
            min_size=args.min_size,
            alignment=args.alignment,
            base=args.base,
        )

    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Binary: {args.binary}")
    print(f"Search range: {args.start:#x} - {end:#x}")
    print(f"Minimum size: {args.min_size} bytes")
    print(f"Alignment: {args.alignment} bytes")
    print()

    for offset, size in candidates:
        address = args.base + offset

        print(
            f"Address: {address:#x} | "
            f"Offset: {offset:#x} | "
            f"Size: {size} bytes"
        )

    print()
    print(f"Candidates found: {len(candidates)}")
    print("Candidates require independent verification.")


if __name__ == "__main__":
    main()
