"""Unit tests for the pure decode helpers in PM8236_for_OBS.

These functions translate the raw bytes from the meter's serial protocol into
display strings. They have no side effects, so they're easy to pin down with
known input -> output pairs taken straight from the protocol's lookup tables.

Run with:  python -m unittest test_decode
"""

import unittest

import PM8236_for_OBS as pm


class TestDecodeDigit(unittest.TestCase):
    def test_known_digits(self):
        # Seven-segment patterns -> the digit they represent.
        cases = {
            0x5F: "0",
            0x06: "1",
            0x6B: "2",
            0x2F: "3",
            0x36: "4",
            0x3D: "5",
            0x7D: "6",
            0x07: "7",
            0x7F: "8",
            0x3F: "9",
            0x58: "L",
        }
        for raw, expected in cases.items():
            self.assertEqual(pm.decode_digit(raw), expected)

    def test_blank_pattern_is_empty(self):
        # 0x00 is the "blank" segment pattern.
        self.assertEqual(pm.decode_digit(0x00), "")

    def test_unknown_pattern_is_empty(self):
        # A pattern not in the table decodes to nothing.
        self.assertEqual(pm.decode_digit(0x01), "")

    def test_decimal_point_high_bit(self):
        # The high bit (0x80) prefixes a decimal point.
        self.assertEqual(pm.decode_digit(0x80 | 0x06), ".1")
        self.assertEqual(pm.decode_digit(0x80 | 0x5F), ".0")

    def test_decimal_point_alone(self):
        # High bit set with a blank pattern is just the point.
        self.assertEqual(pm.decode_digit(0x80), ".")


class TestDecodeBits(unittest.TestCase):
    ICONS = ["A", "B", "C", "D", "E", "F", "G", "H"]

    def test_no_bits_set(self):
        self.assertEqual(pm.decode_bits(0x00, self.ICONS), "")

    def test_low_bit_is_first_icon(self):
        self.assertEqual(pm.decode_bits(0x01, self.ICONS), "A")

    def test_high_bit_is_last_icon(self):
        self.assertEqual(pm.decode_bits(0x80, self.ICONS), "H")

    def test_multiple_bits_in_lsb_first_order(self):
        # 0x05 = bits 0 and 2 set -> first and third icons.
        self.assertEqual(pm.decode_bits(0x05, self.ICONS), "AC")

    def test_all_bits_set(self):
        self.assertEqual(pm.decode_bits(0xFF, self.ICONS), "ABCDEFGH")

    def test_realistic_units_byte(self):
        # The actual units table for raw_msg[21]; 0x08 selects "V ".
        units = ["u", "m", "A ", "V ", "M", "k", "Ohms ", "Hz "]
        self.assertEqual(pm.decode_bits(0x08, units), "V ")


if __name__ == "__main__":
    unittest.main()
