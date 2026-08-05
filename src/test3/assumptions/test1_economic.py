from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAX_JSON_BYTES = 64 * 1024 * 1024
FRED_METRICS = {"CPIAUCSL": "inflation", "UNRATE": "unemployment_rate", "DGS10": "treasury_rate"}


def _load(path: Path) -> tuple[dict, str]:
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"Missing or oversized Test1 economic file: {path.name}")
    content = path.read_bytes()
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError(f"Test1 economic file must contain an object: {path.name}")
    return value, hashlib.sha256(content).hexdigest()


def load_test1_economic(economy_dir: Path, county_fips: str) -> tuple[dict, list[dict]]:
    if len(county_fips) != 5 or not county_fips.isdigit():
        raise ValueError("An approved five-digit county FIPS is required")
    metadata, metadata_hash = _load(economy_dir / "economic_metadata.json")
    county, county_hash = _load(economy_dir / "census_county.json")
    fred, fred_hash = _load(economy_dir / "fred_data.json")
    county_record = (county.get("counties") or {}).get(county_fips)
    if not isinstance(county_record, dict):
        raise ValueError("Approved county FIPS is not covered by the Test1 snapshot")
    rows = []
    for item in county_record.get("history") or []:
        period = str(item.get("year") or item.get("date") or "")
        if len(period) == 4:
            period += "-01-01"
        for field in ("population", "households", "median_household_income", "unemployment_rate"):
            if item.get(field) is not None:
                rows.append({"metric": field, "value": str(item[field]), "observation_date": period, "geography_type": "county", "geography_id": county_fips, "county_fips": county_fips, "source_label": "Test1 Census snapshot", "source_reference": "data/economy/census_county.json", "original_field_name": field})
    for series_id, metric in FRED_METRICS.items():
        series = (fred.get("series") or {}).get(series_id) or {}
        for observation in series.get("observations") or []:
            if isinstance(observation, list) and len(observation) >= 2 and observation[1] not in (None, "."):
                value = str(observation[1])
                if metric in ("inflation", "unemployment_rate", "treasury_rate"):
                    value = str(float(value) / 100)
                rows.append({"metric": metric, "value": value, "observation_date": str(observation[0]), "geography_type": "national", "geography_id": "US", "county_fips": None, "source_label": f"Test1 FRED {series_id}", "source_reference": "data/economy/fred_data.json", "original_field_name": series_id})
    snapshot = {"sourceVersion": str(metadata.get("schema_version") or metadata.get("schemaVersion") or "unknown"), "asOfDate": metadata.get("generated_at") or metadata.get("as_of"), "fileHashes": {"economic_metadata.json": metadata_hash, "census_county.json": county_hash, "fred_data.json": fred_hash}, "freshnessState": "stale" if metadata.get("stale") else "unknown", "coverage": {"countyFips": county_fips, "rowCount": len(rows)}}
    return snapshot, rows
