from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from .geography import validate_geography
from .temporal import normalize_period

SCHEMA_VERSION = "1.0.0"
CANONICAL_COLUMNS = (
    "observation_id", "source_id", "source_dataset", "source_series", "source_version", "retrieved_at",
    "as_of_date", "geography_type", "geography_id", "state_fips", "county_fips", "cbsa", "city",
    "submarket", "property_type", "property_subtype", "observation_date", "period_type", "metric", "value",
    "unit", "currency", "sample_count", "quality_level", "methodology", "transformation_version",
    "raw_source_reference", "raw_row_hash", "normalized_row_hash",
)
NULLABLE = {"as_of_date", "state_fips", "county_fips", "cbsa", "city", "submarket", "property_type", "property_subtype", "currency", "sample_count", "methodology"}
DUCKDB_SCHEMA = """
observation_id VARCHAR NOT NULL, source_id VARCHAR NOT NULL, source_dataset VARCHAR NOT NULL,
source_series VARCHAR NOT NULL, source_version VARCHAR NOT NULL, retrieved_at TIMESTAMPTZ NOT NULL,
as_of_date DATE, geography_type VARCHAR NOT NULL, geography_id VARCHAR NOT NULL, state_fips VARCHAR,
county_fips VARCHAR, cbsa VARCHAR, city VARCHAR, submarket VARCHAR, property_type VARCHAR,
property_subtype VARCHAR, observation_date DATE NOT NULL, period_type VARCHAR NOT NULL, metric VARCHAR NOT NULL,
value DECIMAL(38,12) NOT NULL, unit VARCHAR NOT NULL, currency VARCHAR, sample_count BIGINT,
quality_level VARCHAR NOT NULL, methodology VARCHAR, transformation_version VARCHAR NOT NULL,
raw_source_reference VARCHAR NOT NULL, raw_row_hash VARCHAR NOT NULL, normalized_row_hash VARCHAR NOT NULL
"""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def sha256_value(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def normalize_observation(raw: dict) -> dict:
    unknown = set(raw) - set(CANONICAL_COLUMNS)
    if unknown:
        raise ValueError(f"unknown observation fields: {sorted(unknown)}")
    row = {column: raw.get(column) for column in CANONICAL_COLUMNS}
    missing = [column for column, value in row.items() if column not in NULLABLE and column not in {"observation_id", "normalized_row_hash"} and (value is None or value == "")]
    if missing:
        raise ValueError(f"missing required observation fields: {missing}")
    period = normalize_period(row["observation_date"], str(row["period_type"]))
    row["observation_date"] = period.observation_date.isoformat()
    row["period_type"] = period.period_type
    validate_geography(row)
    try:
        value = Decimal(str(row["value"]))
    except InvalidOperation as exc:
        raise ValueError("value must be numeric") from exc
    if not value.is_finite():
        raise ValueError("value must be finite")
    row["value"] = format(value, "f")
    if row["sample_count"] is not None and (not isinstance(row["sample_count"], int) or row["sample_count"] < 0):
        raise ValueError("sample_count must be a non-negative integer or null")
    if str(row["quality_level"]) not in {"high", "moderate", "low", "unknown"}:
        raise ValueError("quality_level must be high, moderate, low, or unknown")
    retrieved = row["retrieved_at"]
    if isinstance(retrieved, datetime):
        if retrieved.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        row["retrieved_at"] = retrieved.astimezone(timezone.utc).isoformat()
    else:
        parsed = datetime.fromisoformat(str(retrieved).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        row["retrieved_at"] = parsed.astimezone(timezone.utc).isoformat()
    if row["as_of_date"] is not None:
        row["as_of_date"] = date.fromisoformat(str(row["as_of_date"])).isoformat()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(row["raw_row_hash"])):
        raise ValueError("raw_row_hash must use the sha256:<hex> format")
    hash_payload = {key: value for key, value in row.items() if key not in {"observation_id", "normalized_row_hash"}}
    calculated = "sha256:" + sha256_value(hash_payload)
    if row["normalized_row_hash"] not in (None, "", calculated):
        raise ValueError("normalized_row_hash does not match the canonical row")
    row["normalized_row_hash"] = calculated
    row["observation_id"] = row["observation_id"] or calculated.removeprefix("sha256:")
    return row
