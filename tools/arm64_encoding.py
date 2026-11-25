
"""Utilities for encoding PC-relative ARM64 instructions."""

import struct


def encode_branch(source: int, target: int, link: bool = False) -> int:
    """Encode an unconditional B or BL instruction."""

    if source % 4 or target % 4:
        raise ValueError("Branch addresses must be 4-byte aligned")

    delta = target - source

    if not -(1 << 27) <= delta < (1 << 27):
        raise ValueError("Branch target is out of range")

    opcode = 0x94000000 if link else 0x14000000

    return opcode | ((delta >> 2) & 0x03FFFFFF)


def encode_adrp(source: int, target: int, register: int) -> int:
    """Encode an ADRP instruction targeting a 4 KiB page."""

    if source % 4:
        raise ValueError("Instruction address must be 4-byte aligned")

    if not 0 <= register <= 31:
        raise ValueError("Invalid destination register")

    delta = (target >> 12) - (source >> 12)

    if not -(1 << 20) <= delta < (1 << 20):
        raise ValueError("ADRP target page is out of range")

    imm = delta & 0x1FFFFF
    immlo = imm & 3
    immhi = imm >> 2

    return (
        0x90000000
        | (immlo << 29)
        | (immhi << 5)
        | register
    )


def instruction_bytes(instruction: int) -> bytes:
    """Convert a 32-bit instruction to little-endian bytes."""

    return struct.pack("<I", instruction)
