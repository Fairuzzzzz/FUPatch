"""Exercise the assembled iPad helpers with Xcode and synthetic layout records."""

import hashlib
import shutil
import struct
import unittest

from tools import build_ipad_patch as builder


def signed(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def trace_layout(code, compact, geometry):
    """Follow only the helper's w8 instructions. Reject other register effects."""
    pc = builder.UI_LAYOUT_CAVE
    records = {4: geometry, 20: compact}
    w8 = equal = None
    for _ in range(len(code) // 4):
        offset = pc - builder.UI_LAYOUT_CAVE
        if not 0 <= offset <= len(code) - 4:
            raise AssertionError(f"Branch outside layout helper: {pc:#x}")
        word, = struct.unpack_from("<I", code, offset)
        if word == 0xB9800088:  # ldrsw x8, [x4]
            w8, = struct.unpack_from("<i", geometry)
        elif word & 0xFFC0001F in (0xB9400008, 0xB9000008):  # ldr/str w8
            record = records[(word >> 5) & 31]
            field = ((word >> 10) & 0xfff) * 4
            if word & (1 << 22):
                w8, = struct.unpack_from("<I", record, field)
            else:
                struct.pack_into("<I", record, field, w8)
        elif word & 0xFF8003FF == 0x7100011F:  # cmp w8, #imm
            imm = (word >> 10) & 0xfff
            equal = w8 == (imm << (12 if word & (1 << 22) else 0))
        elif word & 0xFFE0001F == 0x52A00008:  # movz w8, #imm, lsl #16
            w8 = ((word >> 5) & 0xffff) << 16
        elif word & 0xFF00001E == 0x54000000:  # b.eq / b.ne
            if equal == (word & 1 == 0):
                pc += signed((word >> 5) & 0x7ffff, 19) * 4
                continue
        elif word & 0xFC000000 == 0x14000000:  # b
            pc += signed(word & 0x3ffffff, 26) * 4
            if pc == builder.UI_LAYOUT_HOOK + 4:
                return w8
            continue
        else:
            raise AssertionError(f"Unexpected instruction {word:#010x} at {pc:#x}")
        pc += 4
    raise AssertionError("Layout helper did not return")


@unittest.skipUnless(shutil.which("xcrun"), "requires the Xcode assembler")
class AssembledHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = builder.assemble(builder.ASM_DIR / "ui_layout_hook.s")

    def check_layout(self, signature, geometry_writes=(), compact_writes=()):
        compact = bytearray(range(0x40))
        geometry = bytearray(range(0x80))
        struct.pack_into("<4I", compact, 0, *signature[:4])
        struct.pack_into("<I", geometry, 0, signature[4])
        expected_geometry = geometry.copy()
        expected_compact = compact.copy()
        for field, value in geometry_writes:
            struct.pack_into("<f", expected_geometry, field, value)
        for field, value in compact_writes:
            struct.pack_into("<f", expected_compact, field, value)

        # A second conversion sees the already-corrected records.
        for _ in range(2):
            self.assertEqual(trace_layout(self.layout, compact, geometry),
                             signed(signature[4], 32))
            self.assertEqual(geometry, expected_geometry)
            self.assertEqual(compact, expected_compact)

    def test_hamburger(self):
        dimensions = ((0x20, 76.5), (0x24, 121.5))
        self.check_layout((8, 527, 527, 1, 99),
                          ((0x10, 12.5), *dimensions), dimensions)

    def test_shared_buttons(self):
        for index in (25, 26, 27, 35):
            with self.subTest(index=index):
                self.check_layout((0x8000, 556, 556, index, 105),
                                  ((0x24, 128), (0x54, 128)), ((0x24, 128),))

    def test_near_misses(self):
        for signature in ((8, 527, 527, 1, 99), (0x8000, 556, 556, 35, 105)):
            for field in range(5):
                miss = list(signature)
                miss[field] |= 0x80000000
                with self.subTest(signature=miss):
                    self.check_layout(miss)
        for index in (*range(25), *range(28, 35), 36, 0xffffffff):
            with self.subTest(index=index):
                self.check_layout((0x8000, 556, 556, index, 105))

    def test_gesture_method_is_only_phase12_difference(self):
        gesture = builder.assemble(builder.ASM_DIR / "gesture_hook.s")
        self.assertEqual(gesture[0x4c:0x54], bytes.fromhex("800180d2 c0035fd6"))
        phase12 = gesture[:0x4c] + bytes.fromhex("000180d2") + gesture[0x50:]
        self.assertEqual(hashlib.sha256(phase12).hexdigest(),
                         "eaa800a4ad8515cb842caef71c2ec291bfc3ae707df20771362ba3621da23bac")
