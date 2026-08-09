from __future__ import annotations

import hashlib
import json
from pathlib import Path

from test3.warehouse.manifests import file_sha256


FEATURE_MANIFEST_VERSION = "1.0.0"


def feature_manifest_hash(payload: dict) -> str:
    body = json.dumps({key: value for key, value in payload.items() if key != "manifest_hash"},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def write_feature_manifest(path: Path, payload: dict) -> dict:
    if path.exists():
        raise FileExistsError(f"immutable feature manifest already exists: {path}")
    complete = {**payload, "manifest_hash": feature_manifest_hash(payload)}
    path.write_text(json.dumps(complete, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return complete


def verify_feature_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable feature manifest: {path}") from exc
    if payload.get("manifest_version") != FEATURE_MANIFEST_VERSION or payload.get("manifest_hash") != feature_manifest_hash(payload):
        raise ValueError(f"feature manifest integrity failure: {path}")
    for item in payload.get("files", []):
        target = path.parent / item["name"]
        if not target.is_file() or target.stat().st_size != item["bytes"] or file_sha256(target) != item["sha256"]:
            raise ValueError(f"feature Parquet integrity failure: {target}")
    return payload


def feature_file_entry(path: Path) -> dict:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": file_sha256(path)}
