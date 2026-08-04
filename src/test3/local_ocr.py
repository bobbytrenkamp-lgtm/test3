from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


@dataclass(frozen=True)
class OcrResult:
    text: str
    words: list[dict]
    engine: str


def validate_image(content: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Image pixel count exceeds the safety limit")
            image.verify()
            return width, height, image.format or "unknown"
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError(f"Image could not be decoded: {error}") from error


def available() -> bool:
    return shutil.which("tesseract") is not None


def extract(content: bytes, suffix: str, timeout_seconds: int = 120) -> OcrResult:
    executable = shutil.which("tesseract")
    if not executable:
        raise RuntimeError("Local Tesseract OCR is not installed")
    validate_image(content)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / f"source{suffix}"
        source.write_bytes(content)
        completed = subprocess.run([executable, str(source), "stdout", "--psm", "6", "tsv"], capture_output=True, text=True, timeout=timeout_seconds, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Local Tesseract OCR failed with exit code {completed.returncode}")
    words, lines = [], {}
    for row in csv.DictReader(io.StringIO(completed.stdout), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = max(0.0, min(1.0, float(row["conf"]) / 100))
            word = {"text": text, "confidence": confidence, "bbox": (int(row["left"]), int(row["top"]), int(row["left"]) + int(row["width"]), int(row["top"]) + int(row["height"]))}
            words.append(word)
            lines.setdefault((row["block_num"], row["par_num"], row["line_num"]), []).append(text)
        except (KeyError, TypeError, ValueError):
            continue
    return OcrResult("\n".join(" ".join(value) for value in lines.values()), words, "tesseract-local/5")

