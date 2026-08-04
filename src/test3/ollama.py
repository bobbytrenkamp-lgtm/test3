from __future__ import annotations

from urllib.parse import urlparse


class LocalModelUnavailable(RuntimeError):
    pass


def validate_local_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Only loopback local-model endpoints are permitted")
    return url.rstrip("/")


def status(url: str) -> dict:
    validate_local_endpoint(url)
    return {"available": False, "provider": "ollama-local", "endpoint": url, "message": "Optional local model not probed automatically. Deterministic processing remains active."}

