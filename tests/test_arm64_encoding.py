
"""Tests for ARM64 PC-relative instruction encoding."""

import unittest

from tools.arm64_encoding import (
    encode_branch,
    encode_adrp,
    instruction_bytes,
)


class TestBranchEncoding(unittest.TestCase):

    def test_ui_layout_entry(self):
        self.assertEqual(
            encode_branch(0x1003A35D0, 0x10049E900),
            0x1403ECCC,
        )

    def test_ui_layout_return(self):
        self.assertEqual(
            encode_branch(0x10049E960, 0x1003A35D4),
            0x17FC131D,
        )

    def test_gesture_entry(self):
        self.assertEqual(
            encode_branch(0x1003545D0, 0x10049EA00),
            0x1405290C,
        )

    def test_gesture_return(self):
        self.assertEqual(
            encode_branch(0x10049EA48, 0x1003545D4),
            0x17FAD6E3,
        )

    def test_dlsym_call(self):
        self.assertEqual(
            encode_branch(
                0x10049EA10, 0x100496CF8, link=True
            ),
            0x97FFE0BA,
        )

    def test_class_add_method_call(self):
        self.assertEqual(
            encode_branch(
                0x10049EA3C, 0x1004969EC, link=True
            ),
            0x97FFDFEC,
        )

    def test_zero_displacement(self):
        self.assertEqual(encode_branch(0x1000, 0x1000), 0x14000000)

    def test_positive_boundary(self):
        source = 0x10000000
        target = source + (1 << 27) - 4

        self.assertEqual(
            encode_branch(source, target),
            0x15FFFFFF,
        )

    def test_negative_boundary(self):
        source = 0x10000000
        target = source - (1 << 27)

        self.assertEqual(
            encode_branch(source, target),
            0x16000000,
        )

    def test_unaligned_source(self):
        with self.assertRaises(ValueError):
            encode_branch(0x1001, 0x2000)

    def test_unaligned_target(self):
        with self.assertRaises(ValueError):
            encode_branch(0x1000, 0x2001)

    def test_positive_out_of_range(self):
        with self.assertRaises(ValueError):
            encode_branch(0x10000000, 0x18000000)

    def test_negative_out_of_range(self):
        with self.assertRaises(ValueError):
            encode_branch(0x10000000, 0x07FFFFFC)


class TestADRPEncoding(unittest.TestCase):

    def test_root_view_controller_page(self):
        self.assertEqual(
            encode_adrp(0x10049EA2C, 0x10069D158, 0),
            0xF0000FE0,
        )

    def test_app_delegate_page(self):
        self.assertEqual(
            encode_adrp(0x10049EA44, 0x10069C000, 8),
            0xD0000FE8,
        )

    def test_same_page(self):
        self.assertEqual(
            encode_adrp(0x1000, 0x1FFF, 0),
            0x90000000,
        )

    def test_positive_boundary(self):
        source = 0x100000000
        target = source + ((1 << 20) - 1) * 4096

        self.assertEqual(
            encode_adrp(source, target, 0),
            0xF07FFFE0,
        )

    def test_negative_boundary(self):
        self.assertEqual(
            encode_adrp(0x100000000, 0, 0),
            0x90800000,
        )

    def test_invalid_register(self):
        for register in (-1, 32):
            with self.subTest(register=register):
                with self.assertRaises(ValueError):
                    encode_adrp(0x1000, 0x2000, register)

    def test_unaligned_source(self):
        with self.assertRaises(ValueError):
            encode_adrp(0x1001, 0x2000, 0)

    def test_positive_out_of_range(self):
        with self.assertRaises(ValueError):
            encode_adrp(0, 0x100000000, 0)

    def test_negative_out_of_range(self):
        with self.assertRaises(ValueError):
            encode_adrp(0x100001000, 0, 0)


class TestInstructionBytes(unittest.TestCase):

    def test_little_endian_encoding(self):
        self.assertEqual(
            instruction_bytes(0x1403ECCC),
            bytes.fromhex("ccec0314"),
        )

    def test_zero_instruction(self):
        self.assertEqual(
            instruction_bytes(0),
            b"\x00\x00\x00\x00",
        )


if __name__ == "__main__":
    unittest.main()
