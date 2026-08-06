from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import DECIMAL_METRICS, PROPERTY_TYPES, RATE_METRICS, REQUIRED_MARKET_COLUMNS, finite_decimal, iso_date, validate_county_fips

MAX_MARKET_PANEL_BYTES = 16 * 1024 * 1024
MAX_MARKET_PANEL_ROWS = 100_000


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def parse_market_panel(content: bytes) -> tuple[dict, list[dict], list[dict]]:
    if len(content) > MAX_MARKET_PANEL_BYTES:
        raise ValueError("Market panel exceeds the 16 MiB safety limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Market panel must be UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    normalized_headers = [header.strip() for header in headers]
    if len(normalized_headers) != len(set(normalized_headers)):
        raise ValueError("Market panel contains duplicate column names")
    missing = sorted(REQUIRED_MARKET_COLUMNS - set(normalized_headers))
    if missing:
        raise ValueError(f"Market panel is missing required columns: {', '.join(missing)}")
    if any(header.startswith("=") for header in normalized_headers):
        raise ValueError("Spreadsheet formulas are not allowed")
    rows, errors = [], []
    for row_number, source_row in enumerate(reader, 2):
        if row_number > MAX_MARKET_PANEL_ROWS + 1:
            raise ValueError("Market panel exceeds the row safety limit")
        row = {str(key).strip(): (value.strip() if isinstance(value, str) else value) for key, value in source_row.items()}
        row_errors = []
        try:
            if any(str(value or "").lstrip().startswith(("=", "+", "@")) for value in source_row.values()):
                raise ValueError("row contains a prohibited spreadsheet formula")
            row["period"] = iso_date(row.get("period"), "period")
            row["source_date"] = iso_date(row.get("source_date"), "source_date")
            row["county_fips"] = validate_county_fips(row.get("county_fips"))
            if row.get("property_type") not in PROPERTY_TYPES:
                raise ValueError("property_type is unsupported")
            if not all(row.get(field) for field in ("market_id", "market_name", "source", "source_reference", "usage_rights")):
                raise ValueError("market/source identity fields cannot be blank")
            present_metrics = []
            for metric in DECIMAL_METRICS:
                value = row.get(metric)
                if value not in (None, ""):
                    if str(value).startswith("="):
                        raise ValueError(f"{metric} contains a prohibited formula")
                    row[metric] = finite_decimal(value, metric, metric in RATE_METRICS)
                    present_metrics.append(metric)
            if not present_metrics:
                raise ValueError("row contains no supported metric")
        except ValueError as error:
            row_errors.append(str(error))
        row_hash = canonical_hash(source_row)
        if row_errors:
            errors.append({"row": row_number, "errors": row_errors, "originalRowHash": row_hash})
            continue
        row["source_row"] = row_number
        row["original_row_hash"] = row_hash
        rows.append(row)
    metadata = {
        "schemaVersion": "test3-market-panel/1.0", "fileSha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content), "rowCount": len(rows), "invalidRowCount": len(errors),
        "headers": normalized_headers, "parsedAt": datetime.now(timezone.utc).isoformat(),
    }
    return metadata, rows, errors


def rows_to_observations(snapshot_id: str, organization_id: str, rows: list[dict], created_at: str) -> list[dict]:
    observations = []
    for row in rows:
        geography_type = row.get("geography_type") or ("submarket" if row.get("submarket") else "market" if row.get("market_id") else "county")
        geography_id = row.get("geography_id") or row.get("submarket") or row.get("market_id") or row.get("county_fips")
        for metric in sorted(DECIMAL_METRICS):
            if row.get(metric) in (None, ""):
                continue
            observations.append({
                "organization_id": organization_id, "snapshot_id": snapshot_id, "metric": metric,
                "value": row[metric], "unit": "decimal_fraction" if metric in RATE_METRICS else ("USD" if metric in {"effective_rent", "asking_rent"} else "count_or_level"),
                "currency": "USD" if metric in {"effective_rent", "asking_rent"} else None,
                "observation_date": row["period"], "effective_date": None, "geography_type": geography_type,
                "geography_id": geography_id, "county_fips": row.get("county_fips"), "cbsa": row.get("cbsa"),
                "submarket": row.get("submarket"), "property_type": row.get("property_type"), "property_subtype": row.get("property_subtype"),
                "source_label": row["source"], "source_reference": row["source_reference"],
                "sample_count": int(float(row["lease_comp_count"])) if metric != "lease_comp_count" and row.get("lease_comp_count") not in (None, "") else None,
                "quality_level": "moderate", "methodology_notes": row.get("notes") or "Analyst-controlled market panel import.",
                "original_field_name": metric, "transformation_version": "market-panel/1.0", "original_row_hash": row["original_row_hash"],
                "source_row": row["source_row"], "validation_errors_json": "[]", "created_at": created_at,
            })
    return observations
