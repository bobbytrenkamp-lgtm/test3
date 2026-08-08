from __future__ import annotations

from .manifests import verified_manifests
from .storage import WarehousePaths


def manifest_status(paths: WarehousePaths) -> list[dict]:
    results = []
    for payload in verified_manifests(paths):
        result = {key: payload.get(key) for key in ("source_id", "dataset_id", "source_version", "created_at", "status", "row_count", "max_observation_date", "manifest_hash")}
        result["integrity"] = "verified"
        results.append(result)
    return results
