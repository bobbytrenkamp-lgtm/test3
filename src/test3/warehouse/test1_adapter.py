from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from test3.assumptions.test1_economic import load_test1_economic

from .ingestion import ingest_observations
from .sources.base import RawSnapshot, canonical_row


UNITS = {"population": "persons", "households": "households", "median_household_income": "USD_current",
         "unemployment_rate": "decimal_fraction", "inflation": "decimal_fraction", "treasury_rate": "decimal_fraction"}


def ingest_test1_economic(paths, economy_dir: Path, county_fips: str):
    metadata, rows = load_test1_economic(economy_dir, county_fips)
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    version = f"{metadata['sourceVersion']}-{digest[:16]}"
    raw_dir = paths.contained(Path("raw/test1/test1_economic") / version)
    raw_dir.mkdir(parents=True, exist_ok=False)
    evidence = raw_dir / "snapshot-metadata.json"
    evidence.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    retrieved = datetime.now(timezone.utc).isoformat()
    snapshot = RawSnapshot("test1_local", "test1_economic", version, evidence, evidence, retrieved,
                           evidence.as_uri(), evidence.as_uri(), 200, "application/json", evidence.stat().st_size,
                           hashlib.sha256(evidence.read_bytes()).hexdigest(), {"county_fips": county_fips})
    def normalized():
        for number, row in enumerate(rows, 1):
            period_type = "annual" if len(row["observation_date"]) == 4 or row["observation_date"].endswith("-01-01") and row["metric"] in {"population", "households", "median_household_income"} else "irregular"
            yield canonical_row(snapshot, series=row["original_field_name"], geography_type=row["geography_type"],
                                geography_id=row["geography_id"], observation_date=row["observation_date"][:4] if period_type == "annual" else row["observation_date"],
                                period_type=period_type, metric=row["metric"], value=row["value"], unit=UNITS[row["metric"]],
                                source_row=number, county_fips=row.get("county_fips"), state_fips=(row.get("county_fips") or "")[:2] or None,
                                raw=row, methodology="Contract-validated Test1 normalized economic export; Test1 remains authoritative.")
    return ingest_observations(paths, source_id="test1_local", dataset_id="test1_economic", source_version=version,
                               domain="demographics", rows=normalized())
