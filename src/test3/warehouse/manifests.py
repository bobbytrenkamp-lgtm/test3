from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from .catalog import get_source
from .storage import WarehousePaths


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


class ManifestIntegrityError(ValueError):
    """Raised before analytical reads when a dataset manifest is not trustworthy."""


def verify_manifest(paths: WarehousePaths, manifest_path: Path) -> dict:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestIntegrityError(f"unreadable manifest: {manifest_path}") from exc
    recorded_hash = payload.pop("manifest_hash", None)
    calculated_hash = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    if recorded_hash != calculated_hash:
        raise ManifestIntegrityError(f"manifest hash mismatch: {manifest_path}")
    required = {field.name for field in DatasetManifest.__dataclass_fields__.values()}
    if set(payload) != required:
        raise ManifestIntegrityError(f"manifest schema mismatch: {manifest_path}")
    if payload["status"] != "validated" or payload["manifest_version"] != "1.0.0":
        raise ManifestIntegrityError(f"manifest is not a supported validated snapshot: {manifest_path}")
    if payload["source_spec_hash"] != get_source(payload["source_id"]).fingerprint:
        raise ManifestIntegrityError(f"source catalog fingerprint mismatch: {manifest_path}")
    if not payload["parquet_files"]:
        raise ManifestIntegrityError(f"manifest contains no Parquet files: {manifest_path}")
    resolved_files = []
    for entry in payload["parquet_files"]:
        file_path = paths.contained(entry["path"])
        if not file_path.is_file() or file_path.stat().st_size != entry["bytes"] or file_sha256(file_path) != entry["sha256"]:
            raise ManifestIntegrityError(f"Parquet content mismatch: {file_path}")
        resolved_files.append(file_path)
    return {**payload, "manifest_hash": recorded_hash, "resolved_files": tuple(resolved_files)}


def verified_manifests(paths: WarehousePaths) -> list[dict]:
    root = paths.contained("manifests")
    return [verify_manifest(paths, path) for path in sorted(root.rglob("*.json"))] if root.exists() else []


def active_manifests(paths: WarehousePaths) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for manifest in verified_manifests(paths):
        key = (manifest["source_id"], manifest["dataset_id"])
        if key not in latest or manifest["created_at"] > latest[key]["created_at"]:
            latest[key] = manifest
    return [latest[key] for key in sorted(latest)]
