from __future__ import annotations

import re

GEOGRAPHY_TYPES = {"national", "state", "county", "cbsa", "place", "zip", "city", "submarket", "market", "property"}


def validate_geography(row: dict) -> None:
    kind = row.get("geography_type")
    if kind not in GEOGRAPHY_TYPES:
        raise ValueError(f"unsupported geography_type: {kind!r}")
    if not str(row.get("geography_id") or "").strip():
        raise ValueError("geography_id is required")
    for field, width in (("state_fips", 2), ("county_fips", 5)):
        value = row.get(field)
        if value is not None and not re.fullmatch(rf"\d{{{width}}}", str(value)):
            raise ValueError(f"{field} must contain exactly {width} digits")
    cbsa = row.get("cbsa")
    if cbsa is not None and not re.fullmatch(r"\d{5}", str(cbsa)):
        raise ValueError("cbsa must contain exactly 5 digits")
