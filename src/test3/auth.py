from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

ITERATIONS = 310_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# A fixed non-user hash makes unknown-account checks perform the same PBKDF2 work.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-user-password", salt=b"test3-dummy-salt")


def session_token() -> str:
    return secrets.token_urlsafe(32)


class SigninLimiter:
    """Process-local abuse control for the deliberately loopback-only server."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 300, lock_seconds: int = 900):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lock_seconds = lock_seconds
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def allowed(self, key: str, timestamp: float | None = None) -> bool:
        current = time.monotonic() if timestamp is None else timestamp
        with self._lock:
            return self._locked_until.get(key, 0) <= current

    def failure(self, key: str, timestamp: float | None = None) -> None:
        current = time.monotonic() if timestamp is None else timestamp
        with self._lock:
            recent = [item for item in self._failures.get(key, []) if current - item <= self.window_seconds]
            recent.append(current)
            self._failures[key] = recent
            if len(recent) >= self.max_failures:
                self._locked_until[key] = current + self.lock_seconds

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

