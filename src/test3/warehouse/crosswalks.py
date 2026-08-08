from __future__ import annotations

from dataclasses import dataclass
from datetime import date


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
