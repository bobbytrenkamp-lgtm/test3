from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Iterable

import duckdb

from .catalog import get_source
from .duckdb_engine import sql_literal
from .manifests import file_sha256, new_manifest, write_manifest_atomic
from .schemas import CANONICAL_COLUMNS, DUCKDB_SCHEMA, SCHEMA_VERSION, normalize_observation
from .storage import WarehousePaths


@dataclass(frozen=True)
class IngestResult:
    parquet_path: Path
    manifest_path: Path
    row_count: int
    manifest_hash: str


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    if not result:
        raise ValueError("dataset and version identifiers must contain safe characters")
    return result


def ingest_observations(paths: WarehousePaths, *, source_id: str, dataset_id: str, source_version: str,
                        domain: str, rows: Iterable[dict], batch_size: int = 10_000) -> IngestResult:
    source = get_source(source_id)
    if batch_size < 1 or batch_size > 100_000:
        raise ValueError("batch_size must be between 1 and 100000")
    paths.initialize()
    dataset_slug, version_slug, domain_slug = _slug(dataset_id), _slug(source_version), _slug(domain)
    final_dir = paths.contained(Path("normalized") / domain_slug / f"source={_slug(source_id)}" / f"dataset={dataset_slug}" / f"version={version_slug}")
    manifest_path = paths.contained(Path("manifests") / _slug(source_id) / dataset_slug / f"{version_slug}.json")
    final_path = final_dir / "observations.parquet"
    if final_path.exists() or manifest_path.exists():
        raise FileExistsError("dataset versions are immutable; choose a new source_version")
    final_dir.mkdir(parents=True, exist_ok=True)
    temporary = final_path.with_suffix(".parquet.tmp")
    connection = duckdb.connect(":memory:")
    try:
        connection.execute(f"CREATE TABLE observations ({DUCKDB_SCHEMA}, UNIQUE(observation_id))")
        batch_path = final_dir / ".normalized-batch.jsonl"
        def insert_batch(items):
            with batch_path.open("w", encoding="utf-8", newline="\n") as stream:
                for item in items:
                    stream.write(json.dumps(dict(zip(CANONICAL_COLUMNS, item, strict=True)), separators=(",", ":")) + "\n")
            connection.execute(f"INSERT INTO observations BY NAME SELECT * FROM read_json_auto({sql_literal(str(batch_path))}, format='newline_delimited', hive_partitioning=false)")
            batch_path.unlink(missing_ok=True)
        count, batch = 0, []
        for raw in rows:
            row = normalize_observation(raw)
            if row["source_id"] != source_id or row["source_dataset"] != dataset_id or row["source_version"] != source_version:
                raise ValueError("row source identifiers must match the ingest request")
            batch.append(tuple(row[column] for column in CANONICAL_COLUMNS))
            if len(batch) >= batch_size:
                insert_batch(batch)
                count += len(batch)
                batch.clear()
        if batch:
            insert_batch(batch)
            count += len(batch)
        if count == 0:
            raise ValueError("an analytical dataset cannot be empty")
        stats = connection.execute("SELECT min(observation_date), max(observation_date) FROM observations").fetchone()
        connection.execute(f"COPY observations TO {sql_literal(str(temporary))} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)")
        if connection.execute(f"SELECT count(*) FROM read_parquet({sql_literal(str(temporary))})").fetchone()[0] != count:
            raise RuntimeError("Parquet validation row count mismatch")
        os.replace(temporary, final_path)
        predecessors = []
        if manifest_path.parent.exists():
            for prior_path in manifest_path.parent.glob("*.json"):
                prior = json.loads(prior_path.read_text(encoding="utf-8"))
                if prior.get("status") == "validated" and prior.get("manifest_hash"):
                    predecessors.append(prior)
        predecessor_hash = max(predecessors, key=lambda item: item.get("created_at", ""))["manifest_hash"] if predecessors else None
        manifest = new_manifest(dataset_id=dataset_id, source_id=source_id, source_version=source_version,
                                schema_version=SCHEMA_VERSION, row_count=count,
                                min_observation_date=stats[0].isoformat(), max_observation_date=stats[1].isoformat(),
                                parquet_files=({"path": str(final_path.relative_to(paths.root)).replace("\\", "/"), "sha256": file_sha256(final_path), "bytes": final_path.stat().st_size},),
                                source_spec_hash=source.fingerprint, predecessor_manifest_hash=predecessor_hash)
        write_manifest_atomic(manifest_path, manifest)
        return IngestResult(final_path, manifest_path, count, manifest.content_hash)
    except Exception:
        (final_dir / ".normalized-batch.jsonl").unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        if final_path.exists() and not manifest_path.exists():
            final_path.unlink()
        raise
    finally:
        connection.close()
