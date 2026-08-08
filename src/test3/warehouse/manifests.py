from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class DatasetManifest:
    manifest_version: str
    dataset_id: str
    source_id: str
    source_version: str
    schema_version: str
    created_at: str
    status: str
    row_count: int
    min_observation_date: str | None
    max_observation_date: str | None
    parquet_files: tuple[dict, ...]
    source_spec_hash: str
    predecessor_manifest_hash: str | None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(canonical_json(asdict(self)).encode()).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest_atomic(path: Path, manifest: DatasetManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"immutable manifest already exists: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({**asdict(manifest), "manifest_hash": manifest.content_hash}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def new_manifest(**kwargs) -> DatasetManifest:
    return DatasetManifest(manifest_version="1.0.0", created_at=datetime.now(timezone.utc).isoformat(), status="validated", **kwargs)
