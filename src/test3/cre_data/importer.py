from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from test3.warehouse.ingestion import ingest_observations
from test3.warehouse.storage import WarehousePaths

from .mappings import ImportMappingTemplate
from .schema import parse_cre_csv, parse_cre_file
from .verification import verify_observations
from .geography import market_definitions


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    if not result:
        raise ValueError("dataset/version must contain safe characters")
    return result


@dataclass(frozen=True)
class CREImportResult:
    dataset_id: str
    source_version: str
    observations: int
    model_eligible: int
    invalid_rows: int
    raw_sha256: str
    manifest_hash: str
    parquet_path: Path
    verification_path: Path


def _canonical(row: dict, dataset_id: str, source_version: str) -> dict:
    quality = "high" if row["confidence"] >= .85 else "moderate" if row["confidence"] >= .65 else "low"
    methodology = json.dumps({"methodology": row["methodology"], "vintage": row["vintage"],
                              "release_date": row["release_date"], "verification_status": row["verification_status"],
                              "confidence": row["confidence"], "target_classification": row["target_classification"],
                              "notes": row["notes"]}, sort_keys=True, separators=(",", ":"))
    return {
        "observation_id": row["observation_id"], "source_id": "user_import", "source_dataset": dataset_id,
        "source_series": f"{row['property_type']}:{row['metric']}:{row['methodology']}", "source_version": source_version,
        "retrieved_at": row["retrieved_at"], "as_of_date": row["release_date"] or row["retrieved_at"][:10],
        "geography_type": row["geography_type"], "geography_id": row["geography_id"], "state_fips": row["state_fips"],
        "county_fips": row["county_fips"], "cbsa": row["cbsa"], "city": None, "submarket": row["submarket"],
        "property_type": row["property_type"], "property_subtype": row["property_subtype"],
        "observation_date": row["period"], "period_type": row["frequency"], "metric": row["metric"],
        "value": row["value"], "unit": row["unit"], "currency": row["currency"], "sample_count": row["sample_count"],
        "quality_level": quality, "methodology": methodology, "transformation_version": "cre-history-import/1.0.0",
        "raw_source_reference": row["source_identifier"], "raw_row_hash": row["raw_row_hash"], "normalized_row_hash": None,
    }


def import_cre_csv(paths: WarehousePaths, content: bytes, *, dataset_id: str, source_version: str,
                   evaluated_at: str | None = None, analyst_review_confirmed: bool = False) -> CREImportResult:
    rows, errors, file_metadata = parse_cre_csv(content)
    if not rows:
        raise ValueError("CRE target file contains no structurally valid observations")
    definitions = market_definitions(paths)
    governed_ids = frozenset(item["market_id"] for item in definitions) if definitions else None
    verification = verify_observations(rows, evaluated_at=evaluated_at,
                                       analyst_review_confirmed=analyst_review_confirmed,
                                       governed_market_ids=governed_ids)
    publishable = [row for row in verification["observations"] if row["verification_status"] != "rejected" and
                   "duplicate_observation" not in row["verification_findings"]]
    if not publishable:
        raise ValueError("CRE target file contains no publishable observations")
    paths.initialize(); dataset_slug, version_slug = _slug(dataset_id), _slug(source_version)
    raw_dir = paths.contained(Path("raw") / "user_imports" / f"dataset={dataset_slug}" / f"version={version_slug}")
    verification_dir = paths.contained(Path("verification") / "cre" / f"dataset={dataset_slug}" / f"version={version_slug}")
    raw_path = raw_dir / f"{file_metadata['sha256']}.csv"
    verification_path = verification_dir / "verification.json"
    if raw_path.exists() or verification_path.exists():
        raise FileExistsError("CRE target dataset versions are immutable")
    raw_dir.mkdir(parents=True, exist_ok=True); verification_dir.mkdir(parents=True, exist_ok=True)
    temporary_raw = raw_path.with_suffix(".csv.tmp")
    temporary_raw.write_bytes(content); os.replace(temporary_raw, raw_path)
    canonical = [_canonical(row, dataset_id, source_version) for row in publishable]
    try:
        ingested = ingest_observations(paths, source_id="user_import", dataset_id=dataset_id,
                                       source_version=source_version, domain="cre_market", rows=canonical)
        report = {"schema_version": "test3-cre-verification/1.0.0", "created_at": datetime.now(timezone.utc).isoformat(),
                  "dataset_id": dataset_id, "source_version": source_version, "raw_snapshot": {"path": str(raw_path.relative_to(paths.root)).replace("\\", "/"), **file_metadata},
                  "summary": verification["summary"], "invalid_rows": errors, "findings": verification["findings"],
                  "observations": verification["observations"], "warehouse_manifest_hash": ingested.manifest_hash}
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        temporary_report = verification_path.with_suffix(".json.tmp")
        temporary_report.write_text(payload, encoding="utf-8"); os.replace(temporary_report, verification_path)
    except Exception:
        # Raw evidence is intentionally retained when later normalization/publication fails.
        # A failed attempt must never destroy the source bytes needed for diagnosis.
        raise
    return CREImportResult(dataset_id, source_version, len(canonical), verification["summary"]["model_eligible"],
                           len(errors), file_metadata["sha256"], ingested.manifest_hash, ingested.parquet_path, verification_path)


def import_cre_file(paths: WarehousePaths, content: bytes, *, suffix: str, dataset_id: str, source_version: str,
                    mapping: ImportMappingTemplate | None = None, evaluated_at: str | None = None,
                    analyst_review_confirmed: bool = False) -> CREImportResult:
    rows, errors, file_metadata = parse_cre_file(content, suffix=suffix, mapping=mapping)
    if not rows:
        raise ValueError("CRE target file contains no structurally valid observations")
    definitions = market_definitions(paths)
    governed_ids = frozenset(item["market_id"] for item in definitions) if definitions else None
    verification = verify_observations(rows, evaluated_at=evaluated_at,
                                       analyst_review_confirmed=analyst_review_confirmed,
                                       governed_market_ids=governed_ids)
    publishable = [row for row in verification["observations"] if row["verification_status"] != "rejected" and
                   "duplicate_observation" not in row["verification_findings"]]
    if not publishable:
        raise ValueError("CRE target file contains no publishable observations")
    paths.initialize(); dataset_slug, version_slug = _slug(dataset_id), _slug(source_version)
    raw_dir = paths.contained(Path("raw") / "user_imports" / f"dataset={dataset_slug}" / f"version={version_slug}")
    verification_dir = paths.contained(Path("verification") / "cre" / f"dataset={dataset_slug}" / f"version={version_slug}")
    raw_path = raw_dir / f"{file_metadata['sha256']}{suffix.lower()}"
    verification_path = verification_dir / "verification.json"
    if raw_path.exists() or verification_path.exists():
        raise FileExistsError("CRE target dataset versions are immutable")
    raw_dir.mkdir(parents=True, exist_ok=True); verification_dir.mkdir(parents=True, exist_ok=True)
    temporary_raw = raw_path.with_suffix(raw_path.suffix + ".tmp")
    temporary_raw.write_bytes(content); os.replace(temporary_raw, raw_path)
    canonical = [_canonical(row, dataset_id, source_version) for row in publishable]
    ingested = ingest_observations(paths, source_id="user_import", dataset_id=dataset_id,
                                   source_version=source_version, domain="cre_market", rows=canonical)
    report = {"schema_version": "test3-cre-verification/1.0.0", "created_at": datetime.now(timezone.utc).isoformat(),
              "dataset_id": dataset_id, "source_version": source_version,
              "raw_snapshot": {"path": str(raw_path.relative_to(paths.root)).replace("\\", "/"), **file_metadata},
              "summary": verification["summary"], "invalid_rows": errors, "findings": verification["findings"],
              "observations": verification["observations"], "warehouse_manifest_hash": ingested.manifest_hash}
    temporary_report = verification_path.with_suffix(".json.tmp")
    temporary_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary_report, verification_path)
    return CREImportResult(dataset_id, source_version, len(canonical), verification["summary"]["model_eligible"],
                           len(errors), file_metadata["sha256"], ingested.manifest_hash, ingested.parquet_path, verification_path)


def cre_status(paths: WarehousePaths) -> list[dict]:
    root = paths.contained(Path("verification") / "cre")
    output = []
    for path in sorted(root.glob("dataset=*/version=*/verification.json")) if root.exists() else ():
        payload = json.loads(path.read_text(encoding="utf-8"))
        output.append({"dataset_id": payload["dataset_id"], "source_version": payload["source_version"],
                       "created_at": payload["created_at"], **payload["summary"],
                       "earliest": min((row["period"] for row in payload["observations"]), default=None),
                       "latest": max((row["period"] for row in payload["observations"]), default=None),
                       "markets": len({row["geography_id"] for row in payload["observations"]}),
                       "property_types": sorted({row["property_type"] for row in payload["observations"]}),
                       "metrics": sorted({row["metric"] for row in payload["observations"]})})
    return output
