from __future__ import annotations

import json
from pathlib import Path

from .storage import WarehousePaths


def manifest_status(paths: WarehousePaths) -> list[dict]:
    root = paths.contained("manifests")
    results = []
    for path in sorted(root.rglob("*.json")) if root.exists() else []:
        payload = json.loads(path.read_text(encoding="utf-8"))
        results.append({key: payload.get(key) for key in ("source_id", "dataset_id", "source_version", "created_at", "status", "row_count", "max_observation_date", "manifest_hash")})
    return results
