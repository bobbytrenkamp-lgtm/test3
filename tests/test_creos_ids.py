"""Tests for test3.creos_ids (CREOS universal entity ID utility, Phase 4
integration boundary only — see that module's docstring and
docs/creos-ids.md).

Known-timestamp vectors are the same ones test4 (CREOS Enterprise)
verified independently against the ULID spec's own reference algorithm
(repeated divmod(n, 32), most-significant digit first) — see
test4/src/domain/ids.test.ts and test4/BUG_TRACKER.md's BUG-005.
Re-checking the same vectors here catches this port drifting from the
spec-verified original, not just from itself.

Uses stdlib unittest (not pytest) to match this repository's actual CI
invocation (`python -m unittest discover -s tests`, see
.github/workflows/ci.yml) — pytest is not an installed dependency here.
"""

from __future__ import annotations

import unittest

from test3.creos_ids import (
    MAX_CREOS_ULID_TIMESTAMP_MS,
    creos_display_id,
    generate_creos_ulid,
    is_valid_creos_ulid,
)

KNOWN_TIMESTAMP_VECTORS = [
    (0, "0000000000"),
    (1, "0000000001"),
    (31, "000000000Z"),
    (32, "0000000010"),
    (1000, "00000000Z8"),
    (1_700_000_000_000, "01HF7YAT00"),
    (281_474_976_710_655, "7ZZZZZZZZZ"),  # MAX_CREOS_ULID_TIMESTAMP_MS
]


class GenerateCreosUlidKnownVectorsTests(unittest.TestCase):
    def test_known_timestamp_vectors(self):
        for timestamp, expected_prefix in KNOWN_TIMESTAMP_VECTORS:
            with self.subTest(timestamp=timestamp):
                self.assertEqual(generate_creos_ulid(timestamp)[:10], expected_prefix)

    def test_max_creos_ulid_timestamp_ms_matches_2_48_minus_1(self):
        self.assertEqual(MAX_CREOS_ULID_TIMESTAMP_MS, 2**48 - 1)

    def test_rejects_timestamp_above_max(self):
        with self.assertRaises(ValueError):
            generate_creos_ulid(MAX_CREOS_ULID_TIMESTAMP_MS + 1)

    def test_rejects_negative_timestamp(self):
        with self.assertRaises(ValueError):
            generate_creos_ulid(-1)

    def test_rejects_non_integer_timestamp(self):
        with self.assertRaises(ValueError):
            generate_creos_ulid(1.5)


class GenerateCreosUlidTests(unittest.TestCase):
    def test_produces_26_character_string(self):
        self.assertEqual(len(generate_creos_ulid()), 26)

    def test_5000_calls_are_all_unique(self):
        ids = {generate_creos_ulid() for _ in range(5000)}
        self.assertEqual(len(ids), 5000)


class IsValidCreosUlidTests(unittest.TestCase):
    def test_accepts_freshly_generated(self):
        self.assertTrue(is_valid_creos_ulid(generate_creos_ulid()))

    def test_rejects_too_short(self):
        self.assertFalse(is_valid_creos_ulid("01ARZ3NDEK"))

    def test_rejects_lowercase(self):
        self.assertFalse(is_valid_creos_ulid("01arz3ndektsv4rrffq69g5fav"))

    def test_rejects_excluded_letters(self):
        # I, L, O, U are excluded from the Crockford alphabet.
        self.assertFalse(is_valid_creos_ulid("0IARZ3NDEKTSV4RRFFQ69G5FAV"))

    def test_rejects_non_string(self):
        self.assertFalse(is_valid_creos_ulid(12345))

    def test_accepts_in_range_first_char(self):
        for first_char in ("0", "1", "7"):
            with self.subTest(first_char=first_char):
                candidate = first_char + "1ARZ3NDEKTSV4RRFFQ69G5FAV"[:25]
                self.assertEqual(len(candidate), 26)
                self.assertTrue(is_valid_creos_ulid(candidate))

    def test_rejects_overflow_first_char(self):
        for first_char in ("8", "9", "A", "H", "Z"):
            with self.subTest(first_char=first_char):
                candidate = first_char + "1ARZ3NDEKTSV4RRFFQ69G5FAV"[:25]
                self.assertEqual(len(candidate), 26)
                self.assertFalse(is_valid_creos_ulid(candidate))


class CreosDisplayIdTests(unittest.TestCase):
    def test_formats_prefix_and_last_five_chars(self):
        ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        self.assertEqual(creos_display_id("PROP", ulid), "CREOS-PROP-G5FAV")

    def test_raises_on_invalid_ulid(self):
        with self.assertRaises(ValueError):
            creos_display_id("PROP", "not-a-ulid")


if __name__ == "__main__":
    unittest.main()
