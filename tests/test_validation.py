import unittest

from app import validation
from app.validation import ValidationError


class CleanTextTests(unittest.TestCase):
    def test_drops_control_characters(self):
        self.assertEqual(validation.clean_text("a\x00b\x07c\x1bd\x7f"), "abcd")

    def test_drops_invisible_format_characters(self):
        # zero-width space, word joiner, soft hyphen, BOM, right-to-left override, bidi isolate
        self.assertEqual(validation.clean_text("a​b⁠c­d﻿e‮f⁦g"), "abcdefg")

    def test_keeps_emoji_joined_with_zero_width_joiner(self):
        self.assertEqual(validation.clean_text("dev \U0001f469‍\U0001f4bb"), "dev \U0001f469‍\U0001f4bb")

    def test_drops_lone_surrogates(self):
        self.assertEqual(validation.clean_text("a\ud800b\udfffc"), "abc")

    def test_normalises_to_nfc(self):
        self.assertEqual(validation.clean_text("Stéfania"), "Stéfania")

    def test_single_line_collapses_whitespace(self):
        self.assertEqual(validation.clean_text("  a \t b\n c  d  "), "a b c d")

    def test_multiline_keeps_line_breaks(self):
        self.assertEqual(validation.clean_text("  a  \r\nb\tc\rd  ", multiline=True), "a\nb\tc\nd")

    def test_multiline_keeps_at_most_one_blank_line(self):
        self.assertEqual(validation.clean_text("a\n\n\n\n\nb\n \n \n c", multiline=True), "a\n\nb\n\n c")

    def test_leaves_html_alone(self):
        self.assertEqual(validation.clean_text("<script>alert(1)</script> & <3"), "<script>alert(1)</script> & <3")


class DisplayNameTests(unittest.TestCase):
    def test_returns_cleaned_name(self):
        self.assertEqual(validation.display_name({"display_name": "  Duna​  Bianca "}), "Duna Bianca")

    def test_length_limit_applies_after_cleaning(self):
        name = "x" * validation.NAME_MAX_LENGTH
        self.assertEqual(validation.display_name({"display_name": f"​ {name} \x00"}), name)
        with self.assertRaisesRegex(ValidationError, "at most 32"):
            validation.display_name({"display_name": name + "y"})

    def test_rejects_missing_empty_or_non_text(self):
        cases = [(None, "required"), ({}, "required"), ({"display_name": None}, "required"),
                 ({"display_name": 5}, "must be text"), ({"display_name": ["a"]}, "must be text"),
                 ({"display_name": " ​\t"}, "must not be empty")]
        for data, message in cases:
            with self.subTest(data=data), self.assertRaisesRegex(ValidationError, message):
                validation.display_name(data)


class MessageContentTests(unittest.TestCase):
    def test_accepts_up_to_the_limit(self):
        text = "x" * validation.MESSAGE_MAX_LENGTH
        self.assertEqual(validation.message_content({"content": text}), text)
        with self.assertRaises(ValidationError):
            validation.message_content({"content": text + "x"})

    def test_keeps_line_breaks(self):
        self.assertEqual(validation.message_content({"content": "line one\nline two"}), "line one\nline two")


class LoginIdTests(unittest.TestCase):
    def test_trims_and_lowercases(self):
        self.assertEqual(validation.login_id({"id": "  AB12CD34EF56 "}), "ab12cd34ef56")

    def test_rejects_malformed_ids(self):
        for value in [None, 123, "", "abc", "ab12cd34ef5", "ab12cd34ef567", "gh12cd34ef56", "ab12 cd34ef5"]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validation.login_id({"id": value})
        with self.assertRaises(ValidationError):
            validation.login_id("ab12cd34ef56")


class RoomIdTests(unittest.TestCase):
    def test_accepts_positive_sqlite_integers(self):
        for value in [1, 42, validation.SQLITE_INTEGER_MAX]:
            self.assertEqual(validation.room_id({"room_id": value}), value)

    def test_rejects_everything_else(self):
        for value in [None, 0, -1, True, False, 1.0, "1", [1], validation.SQLITE_INTEGER_MAX + 1]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validation.room_id({"room_id": value})
        for data in [None, [], "1", 1]:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                validation.room_id(data)
