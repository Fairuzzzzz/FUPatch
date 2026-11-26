
"""Regression tests for the reproducible iPad patch builder."""

import hashlib
import struct
import unittest
from unittest.mock import patch

from tools.build_ipad_patch import (
    BASE,
    SOURCE_SHA256,
    RESULT_SHA256,
    UI_LAYOUT_HOOK,
    UI_LAYOUT_CAVE,
    UI_LAYOUT_SIZE,
    GESTURE_HOOK,
    GESTURE_CAVE,
    GESTURE_SIZE,
    BuildError,
    sha256,
    make_step,
    build_steps,
    apply_steps,
    build_patch,
    extract_text_section,
)


class TestHashing(unittest.TestCase):

    def test_sha256(self):
        data = b"MHFU"
        self.assertEqual(
            sha256(data),
            hashlib.sha256(data).hexdigest(),
        )

    def test_known_hash_lengths(self):
        self.assertEqual(len(SOURCE_SHA256), 64)
        self.assertEqual(len(RESULT_SHA256), 64)

    def test_source_and_result_hashes_differ(self):
        self.assertNotEqual(SOURCE_SHA256, RESULT_SHA256)


class TestMakeStep(unittest.TestCase):

    def test_valid_step(self):
        step = make_step(
            "test.patch",
            BASE + 4,
            b"\x00\x00",
            b"\x01\x02",
        )

        self.assertEqual(step["id"], "test.patch")
        self.assertEqual(step["vaddr"], "0x100000004")
        self.assertEqual(step["expect"], "0000")
        self.assertEqual(step["replace"], "0102")

    def test_mismatched_lengths(self):
        with self.assertRaises(BuildError):
            make_step(
                "test.patch",
                BASE,
                b"\x00",
                b"\x01\x02",
            )


class TestBuildSteps(unittest.TestCase):

    def setUp(self):
        self.ui_layout = bytes([0xAA]) * UI_LAYOUT_SIZE
        self.gesture = bytes([0xBB]) * GESTURE_SIZE

        self.steps = build_steps(
            self.ui_layout,
            self.gesture,
        )

    def test_step_count(self):
        self.assertEqual(len(self.steps), 6)

    def test_ui_layout_hook(self):
        step = self.steps[0]

        self.assertEqual(
            int(step["vaddr"], 0),
            UI_LAYOUT_HOOK,
        )
        self.assertEqual(step["expect"], "880080b9")
        self.assertEqual(step["replace"], "ccec0314")

    def test_ui_layout_cave(self):
        step = self.steps[1]

        self.assertEqual(
            int(step["vaddr"], 0),
            UI_LAYOUT_CAVE,
        )
        self.assertEqual(
            bytes.fromhex(step["expect"]),
            bytes(UI_LAYOUT_SIZE),
        )
        self.assertEqual(
            bytes.fromhex(step["replace"]),
            self.ui_layout,
        )

    def test_gesture_hook(self):
        step = self.steps[2]

        self.assertEqual(
            int(step["vaddr"], 0),
            GESTURE_HOOK,
        )
        self.assertEqual(step["expect"], "481a0090")
        self.assertEqual(step["replace"], "0c290514")

    def test_gesture_cave(self):
        step = self.steps[3]

        self.assertEqual(
            int(step["vaddr"], 0),
            GESTURE_CAVE,
        )
        self.assertEqual(
            bytes.fromhex(step["expect"]),
            bytes(GESTURE_SIZE),
        )
        self.assertEqual(
            bytes.fromhex(step["replace"]),
            self.gesture,
        )

    def test_total_patch_size(self):
        total = sum(
            len(bytes.fromhex(step["replace"]))
            for step in self.steps
        )

        self.assertEqual(total, 372)

    def test_loading_instructions(self):
        dimension, origin = self.steps[4:]
        self.assertEqual(dimension["vaddr"], "0x100441CC4")
        self.assertEqual(origin["vaddr"], "0x10049E628")
        source = bytearray(0x49E630)
        source[0x441CC4:0x441CC8] = bytes.fromhex("0110271e")
        source[0x49E620:] = bytes.fromhex("13814079 697e0253 7302090b ad8efe17")
        result = apply_steps(source, [dimension, origin])
        self.assertEqual(result[0x441CC4:0x441CC8], bytes.fromhex("0190261e"))
        self.assertEqual(result[0x49E620:], bytes.fromhex("13814079 697e0253 7302094b ad8efe17"))
        self.assertEqual(len(result), len(source))
        for offset in (0x441CC4, 0x49E628):
            with self.subTest(offset=offset):
                bad = source.copy()
                bad[offset] ^= 1
                with self.assertRaisesRegex(BuildError, "Original bytes mismatch"):
                    apply_steps(bad, [dimension, origin])
        self.assertEqual(self.steps, build_steps(self.ui_layout, self.gesture))

    def test_layout_must_fit_before_gesture(self):
        with self.assertRaisesRegex(BuildError, "overlaps gesture"):
            build_steps(bytes(GESTURE_CAVE - UI_LAYOUT_CAVE + 4), self.gesture)

    def test_invalid_ui_layout_size(self):
        with self.assertRaises(BuildError):
            build_steps(b"\x00", self.gesture)

    def test_invalid_gesture_size(self):
        with self.assertRaises(BuildError):
            build_steps(self.ui_layout, b"\x00")


class TestApplySteps(unittest.TestCase):

    def test_valid_replacement(self):
        source = bytes(16)

        steps = [
            make_step(
                "test.patch",
                BASE + 4,
                bytes(4),
                b"\x01\x02\x03\x04",
            )
        ]

        result = apply_steps(source, steps)

        self.assertEqual(
            result[4:8],
            b"\x01\x02\x03\x04",
        )
        self.assertEqual(len(result), len(source))

    def test_preserves_unrelated_bytes(self):
        source = bytes(range(16))

        steps = [
            make_step(
                "test.patch",
                BASE + 4,
                source[4:8],
                b"\xff" * 4,
            )
        ]

        result = apply_steps(source, steps)

        self.assertEqual(result[:4], source[:4])
        self.assertEqual(result[8:], source[8:])

    def test_source_remains_unchanged(self):
        source = bytearray(16)

        steps = [
            make_step(
                "test.patch",
                BASE,
                bytes(4),
                b"\xff" * 4,
            )
        ]

        apply_steps(source, steps)

        self.assertEqual(source, bytearray(16))

    def test_original_bytes_mismatch(self):
        steps = [
            make_step(
                "test.patch",
                BASE,
                b"\xff",
                b"\x01",
            )
        ]

        with self.assertRaises(BuildError):
            apply_steps(bytes(16), steps)

    def test_negative_offset(self):
        steps = [
            make_step(
                "test.patch",
                BASE - 1,
                b"\x00",
                b"\x01",
            )
        ]

        with self.assertRaises(BuildError):
            apply_steps(bytes(16), steps)

    def test_outside_executable(self):
        steps = [
            make_step(
                "test.patch",
                BASE + 15,
                bytes(4),
                b"\xff" * 4,
            )
        ]

        with self.assertRaises(BuildError):
            apply_steps(bytes(16), steps)

    def test_overlapping_steps(self):
        steps = [
            make_step(
                "first",
                BASE,
                bytes(4),
                b"\xff" * 4,
            ),
            make_step(
                "second",
                BASE + 2,
                bytes(4),
                b"\xaa" * 4,
            ),
        ]

        with self.assertRaises(BuildError):
            apply_steps(bytes(16), steps)

    def test_adjacent_steps(self):
        steps = [
            make_step(
                "first",
                BASE,
                bytes(4),
                b"\xaa" * 4,
            ),
            make_step(
                "second",
                BASE + 4,
                bytes(4),
                b"\xbb" * 4,
            ),
        ]

        result = apply_steps(bytes(8), steps)

        self.assertEqual(
            result,
            b"\xaa" * 4 + b"\xbb" * 4,
        )

    def test_empty_replacement(self):
        steps = [
            make_step(
                "empty",
                BASE,
                b"",
                b"",
            )
        ]

        with self.assertRaises(BuildError):
            apply_steps(bytes(16), steps)

    def test_malformed_step_lengths(self):
        steps = [{
            "id": "malformed",
            "vaddr": hex(BASE),
            "expect": "00",
            "replace": "0102",
        }]

        with self.assertRaises(BuildError):
            apply_steps(bytes(16), steps)


class TestMachOExtraction(unittest.TestCase):

    @staticmethod
    def make_object(payload, nreloc=0):
        """Construct a minimal synthetic ARM64 Mach-O object."""

        cmdsize = 72 + 80
        fileoff = 32 + cmdsize

        header = struct.pack(
            "<8I",
            0xFEEDFACF,
            0x0100000C,
            0,
            1,
            1,
            cmdsize,
            0,
            0,
        )

        segment = bytearray(72)

        struct.pack_into("<II", segment, 0, 0x19, cmdsize)
        struct.pack_into("<I", segment, 64, 1)

        section = bytearray(80)

        section[:16] = b"__text".ljust(16, b"\x00")
        section[16:32] = b"__TEXT".ljust(16, b"\x00")

        struct.pack_into("<Q", section, 40, len(payload))
        struct.pack_into("<I", section, 48, fileoff)
        struct.pack_into("<I", section, 60, nreloc)

        return header + segment + section + payload

    def test_valid_text_extraction(self):
        payload = bytes.fromhex("000180d2c0035fd6")
        obj = self.make_object(payload)

        self.assertEqual(
            extract_text_section(obj),
            payload,
        )

    def test_truncated_header(self):
        with self.assertRaises(BuildError):
            extract_text_section(bytes(8))

    def test_invalid_magic(self):
        obj = bytearray(self.make_object(bytes(4)))
        struct.pack_into("<I", obj, 0, 0)

        with self.assertRaises(BuildError):
            extract_text_section(obj)

    def test_wrong_architecture(self):
        obj = bytearray(self.make_object(bytes(4)))
        struct.pack_into("<I", obj, 4, 0x01000007)

        with self.assertRaises(BuildError):
            extract_text_section(obj)

    def test_wrong_file_type(self):
        obj = bytearray(self.make_object(bytes(4)))
        struct.pack_into("<I", obj, 12, 2)

        with self.assertRaises(BuildError):
            extract_text_section(obj)

    def test_unresolved_relocations(self):
        obj = self.make_object(bytes(4), nreloc=1)

        with self.assertRaises(BuildError):
            extract_text_section(obj)

    def test_truncated_payload(self):
        obj = self.make_object(bytes(16))[:-1]

        with self.assertRaises(BuildError):
            extract_text_section(obj)

    def test_truncated_commands(self):
        obj = self.make_object(bytes(16))[:40]

        with self.assertRaises(BuildError):
            extract_text_section(obj)


class TestBuildPatch(unittest.TestCase):

    def test_unsupported_baseline(self):
        with patch(
            "tools.build_ipad_patch.assemble"
        ) as mock_assemble:

            with self.assertRaisesRegex(
                BuildError,
                "Unsupported baseline",
            ):
                build_patch(b"invalid executable")

            mock_assemble.assert_not_called()

    def test_result_hash_mismatch(self):

        with patch(
            "tools.build_ipad_patch.sha256",
            side_effect=[
                SOURCE_SHA256,
                "0" * 64,
            ],
        ), patch(
            "tools.build_ipad_patch.assemble",
            side_effect=[
                bytes(UI_LAYOUT_SIZE),
                bytes(GESTURE_SIZE),
            ],
        ), patch(
            "tools.build_ipad_patch.apply_steps",
            return_value=b"incorrect result",
        ):

            with self.assertRaisesRegex(
                BuildError,
                "Result does not match",
            ):
                build_patch(b"synthetic baseline")

    def test_successful_build(self):
        expected = b"synthetic patched executable"

        with patch(
            "tools.build_ipad_patch.sha256",
            side_effect=[
                SOURCE_SHA256,
                RESULT_SHA256,
            ],
        ), patch(
            "tools.build_ipad_patch.assemble",
            side_effect=[
                bytes(UI_LAYOUT_SIZE),
                bytes(GESTURE_SIZE),
            ],
        ), patch(
            "tools.build_ipad_patch.apply_steps",
            return_value=expected,
        ):

            result, steps = build_patch(
                b"synthetic baseline"
            )

        self.assertEqual(result, expected)
        self.assertEqual(len(steps), 6)


if __name__ == "__main__":
    unittest.main()
