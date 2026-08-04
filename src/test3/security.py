from __future__ import annotations

import hashlib
import html
import mimetypes
import re
from pathlib import Path

ALLOWED_TYPES = {
    "application/pdf": {b"%PDF-"},
    "image/png": {b"\x89PNG\r\n\x1a\n"},
    "image/jpeg": {b"\xff\xd8\xff"},
    "text/csv": set(),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {b"PK\x03\x04"},
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sanitize_text(value: str) -> str:
    value = value.replace("\x00", "")
    return html.escape(value, quote=True)


def safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(". ")
    return cleaned[:180] or "upload"


def detect_mime(filename: str, content: bytes) -> str:
    head = content[:16]
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"PK\x03\x04") and b"[Content_Types].xml" in content[:5000]:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    extension = Path(filename).suffix.lower()
    if extension == ".csv":
        try:
            content[:4096].decode("utf-8-sig")
            return "text/csv"
        except UnicodeDecodeError:
            return "application/octet-stream"
    guessed, _ = mimetypes.guess_type(filename)
    return guessed if guessed in ALLOWED_TYPES else "application/octet-stream"


def validate_upload(filename: str, content: bytes, max_bytes: int) -> tuple[str, str]:
    if not content:
        raise ValueError("Empty files are not accepted")
    if len(content) > max_bytes:
        raise ValueError(f"File exceeds the configured {max_bytes}-byte limit")
    mime = detect_mime(filename, content)
    if mime not in ALLOWED_TYPES:
        raise ValueError("Unsupported or unverifiable file type")
    return safe_filename(filename), mime

