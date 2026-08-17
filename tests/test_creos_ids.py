"""Tests for test3.creos_ids (CREOS universal entity ID utility, Phase 4
integration boundary only — see that module's docstring and
docs/creos-ids.md).

Known-timestamp vectors are the same ones test4 (CREOS Enterprise)
verified independently against the ULID spec's own reference algorithm
(repeated divmod(n, 32), most-significant digit first) — see
test4/src/domain/ids.test.ts and test4/BUG_TRACKER.md's BUG-005.
Re-checking the same vectors here catches this port drifting from the
spec-verified original, not just from itself.
"""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize("timestamp,expected_prefix", KNOWN_TIMESTAMP_VECTORS)
def test_generate_creos_ulid_known_timestamp_vectors(timestamp, expected_prefix):
    assert generate_creos_ulid(timestamp)[:10] == expected_prefix


def test_max_creos_ulid_timestamp_ms_matches_2_48_minus_1():
    assert MAX_CREOS_ULID_TIMESTAMP_MS == 2**48 - 1


def test_generate_creos_ulid_rejects_timestamp_above_max():
    with pytest.raises(ValueError):
        generate_creos_ulid(MAX_CREOS_ULID_TIMESTAMP_MS + 1)


def test_generate_creos_ulid_rejects_negative_timestamp():
    with pytest.raises(ValueError):
        generate_creos_ulid(-1)


def test_generate_creos_ulid_rejects_non_integer_timestamp():
    with pytest.raises(ValueError):
        generate_creos_ulid(1.5)


def test_generate_creos_ulid_produces_26_character_string():
    assert len(generate_creos_ulid()) == 26


def test_generate_creos_ulid_5000_calls_are_all_unique():
    ids = {generate_creos_ulid() for _ in range(5000)}
    assert len(ids) == 5000


def test_is_valid_creos_ulid_accepts_freshly_generated():
    assert is_valid_creos_ulid(generate_creos_ulid())


def test_is_valid_creos_ulid_rejects_too_short():
    assert not is_valid_creos_ulid("01ARZ3NDEK")


def test_is_valid_creos_ulid_rejects_lowercase():
    assert not is_valid_creos_ulid("01arz3ndektsv4rrffq69g5fav")


def test_is_valid_creos_ulid_rejects_excluded_letters():
    # I, L, O, U are excluded from the Crockford alphabet.
    assert not is_valid_creos_ulid("0IARZ3NDEKTSV4RRFFQ69G5FAV")


def test_is_valid_creos_ulid_rejects_non_string():
    assert not is_valid_creos_ulid(12345)


@pytest.mark.parametrize("first_char", ["0", "1", "7"])
def test_is_valid_creos_ulid_accepts_in_range_first_char(first_char):
    candidate = first_char + "1ARZ3NDEKTSV4RRFFQ69G5FAV"[:25]
    assert len(candidate) == 26
    assert is_valid_creos_ulid(candidate)


@pytest.mark.parametrize("first_char", ["8", "9", "A", "H", "Z"])
def test_is_valid_creos_ulid_rejects_overflow_first_char(first_char):
    candidate = first_char + "1ARZ3NDEKTSV4RRFFQ69G5FAV"[:25]
    assert len(candidate) == 26
    assert not is_valid_creos_ulid(candidate)


def test_creos_display_id_formats_prefix_and_last_five_chars():
    ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert creos_display_id("PROP", ulid) == "CREOS-PROP-G5FAV"


def test_creos_display_id_raises_on_invalid_ulid():
    with pytest.raises(ValueError):
        creos_display_id("PROP", "not-a-ulid")
