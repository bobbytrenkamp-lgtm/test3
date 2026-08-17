"""CREOS universal entity ID utility (Phase 4, integration boundary only —
see ``docs/creos-ids.md``).

``docs/creos-ids.md`` documented a shared ``CREOS-*-XXXXX`` ID scheme but
marked it "Not implemented." This module implements the generator/
validator side of that scheme so a future MarketSignal -> Underwrite (or
-> SiteIntel) handoff can produce and check real, collision-safe CREOS
IDs. It does NOT touch this app's own identifiers — the warehouse's
market/geography keys, the opportunity engine's property records, etc.
remain the source of truth for everything this app does internally.
Nothing in this repository calls :func:`generate_creos_ulid` yet; it
exists so the capability is available and tested before it is wired into
any real handoff.

Ported in spirit from the CREOS Enterprise repository's hardened,
spec-verified implementation (test4's ``src/domain/ids.ts`` — see that
repo's BUG-005 in ``BUG_TRACKER.md`` for why the timestamp has to be
encoded this specific way, not the more "obvious" byte-array approach).
Ported by hand rather than depending on test4 as a package, since these
are independently deployed applications — keeping the algorithm
identical to the spec-verified original is what matters.

ULID spec: https://github.com/ulid/spec — a 26-character Crockford
base32 string: 10 characters of millisecond timestamp (48 bits) + 16
characters of randomness (80 bits).
"""

from __future__ import annotations

import os
import re
import time

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

MAX_CREOS_ULID_TIMESTAMP_MS = 281_474_976_710_655  # 2**48 - 1

_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_OVERFLOW_PATTERN = re.compile(r"^[0-7]")


def _encode_crockford_int(value: int, length: int) -> str:
    """Canonical ULID timestamp encoding: repeated ``value % 32`` /
    ``value // 32`` in the integer domain, most-significant digit first —
    the algorithm the spec actually defines. A byte-array + generic
    streaming base32 encoder does NOT match this for a 48-bit value (48
    isn't a multiple of 5); that mismatch was test4's BUG-005.
    """
    chars = []
    n = value
    for _ in range(length):
        n, digit = divmod(n, 32)
        chars.append(CROCKFORD_ALPHABET[digit])
    return "".join(reversed(chars))


def _encode_crockford_bytes_exact(data: bytes) -> str:
    """Byte-array streaming encoder — correct here because 80 bits (10
    random bytes) is exactly 16 Crockford digits with no remainder, unlike
    the 48-bit timestamp above.
    """
    bits = 0
    value = 0
    output = []
    for byte in data:
        value = (value << 8) | byte
        bits += 8
        while bits >= 5:
            output.append(CROCKFORD_ALPHABET[(value >> (bits - 5)) & 0x1F])
            bits -= 5
    if bits != 0:
        raise ValueError("_encode_crockford_bytes_exact: input bit length must be a multiple of 5")
    return "".join(output)


def generate_creos_ulid(now_ms: int | None = None) -> str:
    """Generates a fresh CREOS ULID. ``now_ms`` defaults to the current
    time in milliseconds; passing an explicit timestamp is for tests only.

    Same-millisecond ordering is NOT guaranteed to be monotonic — each
    call draws independent randomness for its lower 80 bits (Option A per
    test4's hardening milestone; see that repo's ``AI_CHANGELOG.md``). If
    a true monotonic generator is ever needed here, that is a deliberate
    follow-up, not an assumption baked into this function.
    """
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    if not isinstance(ts, int) or isinstance(ts, bool) or ts < 0 or ts > MAX_CREOS_ULID_TIMESTAMP_MS:
        raise ValueError(
            f"generate_creos_ulid: timestamp {ts} is out of ULID's representable range "
            f"(0 to {MAX_CREOS_ULID_TIMESTAMP_MS})"
        )
    time_part = _encode_crockford_int(ts, 10)
    random_part = _encode_crockford_bytes_exact(os.urandom(10))
    return time_part + random_part


def is_valid_creos_ulid(value: object) -> bool:
    """A syntactically well-formed 26-char Crockford string can still
    encode a timestamp above ``MAX_CREOS_ULID_TIMESTAMP_MS`` unless its
    first character is restricted to '0'-'7' (2**48 only needs 1 of the
    first digit's 5 bits).
    """
    return (
        isinstance(value, str)
        and bool(_ULID_PATTERN.match(value))
        and bool(_OVERFLOW_PATTERN.match(value))
    )


def creos_display_id(prefix: str, ulid: str) -> str:
    """``CREOS-<PREFIX>-<last 5 chars, uppercase>`` — a derived display id
    only, never a second source of truth.
    """
    if not is_valid_creos_ulid(ulid):
        raise ValueError(f"creos_display_id: not a valid CREOS ULID: {ulid!r}")
    return f"CREOS-{prefix}-{ulid[-5:]}"
