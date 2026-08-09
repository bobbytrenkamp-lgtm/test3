from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .duckdb_engine import WarehouseEngine


@dataclass(frozen=True)
class CountyCrosswalk:
    county_fips: str
    county_name: str
    state_fips: str
    state_name: str
    cbsa: str | None
    cbsa_name: str | None
    effective_from: date
    effective_to: date | None
    vintage: str


def validate_crosswalk(row: CountyCrosswalk) -> CountyCrosswalk:
    if len(row.county_fips) != 5 or not row.county_fips.isdigit() or row.county_fips[:2] != row.state_fips:
        raise ValueError("crosswalk requires consistent state and county FIPS")
    if row.cbsa is not None and (len(row.cbsa) != 5 or not row.cbsa.isdigit()):
        raise ValueError("CBSA must be a five-digit code or null")
    if row.effective_to is not None and row.effective_to < row.effective_from:
        raise ValueError("crosswalk effective dates are reversed")
    return row


def lookup_county_cbsa(paths, county_fips: str, on_date: date | None = None) -> dict | None:
    """Return the latest official delineation effective on a date; never infer missing membership."""
    if len(county_fips) != 5 or not county_fips.isdigit():
        raise ValueError("county_fips must contain exactly five digits")
    effective = on_date or date.today()
    rows = WarehouseEngine(paths).query_observations(
        metrics=("county_cbsa_membership",), geography_id=county_fips,
        columns=("observation_id", "observation_date", "county_fips", "state_fips", "cbsa",
                 "source_id", "source_dataset", "source_version", "methodology"),
        limit=1000,
    )
    eligible = [row for row in rows if row["observation_date"] <= effective]
    return max(eligible, key=lambda row: row["observation_date"]) if eligible else None
