from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from math import isfinite

from test3.research.comparables import distance_miles


MAX_ROWS = 10_000
MAX_BYTES = 8 * 1024 * 1024
CATEGORIES = {
    "school", "shopping_center", "grocery", "downtown", "transit",
    "park", "healthcare", "employment_center",
}
DEFAULT_THRESHOLDS_MILES = {
    "school": 1.5,
    "shopping_center": 3.0,
    "grocery": 2.0,
    "downtown": 10.0,
    "transit": 1.0,
    "park": 2.0,
    "healthcare": 5.0,
    "employment_center": 10.0,
}
REQUIRED_COLUMNS = {
    "name", "category", "latitude", "longitude", "evidence_date", "source_reference",
}


def parse_location_evidence(text: str) -> list[dict]:
    if len(text.encode()) > MAX_BYTES:
        raise ValueError("location-evidence CSV exceeds 8 MiB")
    reader = csv.DictReader(StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"location-evidence CSV is missing required columns: {sorted(missing)}")
    rows = []
    for number, row in enumerate(reader, 2):
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"location-evidence CSV exceeds {MAX_ROWS} rows")
        clean = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
        blank = sorted(field for field in REQUIRED_COLUMNS if not clean.get(field))
        if blank:
            raise ValueError(f"location-evidence CSV row {number} has blank required fields: {blank}")
        clean["source_row"] = number
        rows.append(clean)
    return rows


def _period(value: object, name: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def analyze_location_evidence(subject: dict, rows: list[dict], *, analysis_as_of: date,
                              thresholds: dict[str, float] | None = None,
                              maximum_age_days: int = 3650) -> dict:
    if not 30 <= maximum_age_days <= 7300:
        raise ValueError("location-evidence maximum age must be between 30 and 7300 days")
    latitude, longitude = float(subject["latitude"]), float(subject["longitude"])
    if not isfinite(latitude) or not isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("subject coordinates are outside their valid range")
    governed_thresholds = {**DEFAULT_THRESHOLDS_MILES, **(thresholds or {})}
    if set(governed_thresholds) != CATEGORIES:
        raise ValueError("location thresholds must contain only governed categories")
    if any(not 0 < float(value) <= 250 for value in governed_thresholds.values()):
        raise ValueError("location thresholds must be greater than zero and no more than 250 miles")
    nearest: dict[str, dict] = {}
    rejected = {
        "unsupported_category": 0,
        "future_evidence": 0,
        "stale_evidence": 0,
        "not_yet_effective": 0,
        "expired": 0,
        "invalid": 0,
    }
    for row in rows[:MAX_ROWS]:
        try:
            category = str(row.get("category") or "").strip().lower()
            if category not in CATEGORIES:
                rejected["unsupported_category"] += 1
                continue
            observed = _period(row.get("evidence_date"), "evidence_date")
            if observed is None:
                raise ValueError("evidence_date is required")
            age = (analysis_as_of - observed).days
            if age < 0:
                rejected["future_evidence"] += 1
                continue
            if age > maximum_age_days:
                rejected["stale_evidence"] += 1
                continue
            effective_from = _period(row.get("effective_from"), "effective_from")
            effective_to = _period(row.get("effective_to"), "effective_to")
            if effective_from and effective_to and effective_from > effective_to:
                raise ValueError("effective_from cannot be after effective_to")
            if effective_from and effective_from > analysis_as_of:
                rejected["not_yet_effective"] += 1
                continue
            if effective_to and effective_to < analysis_as_of:
                rejected["expired"] += 1
                continue
            distance = distance_miles(latitude, longitude, row.get("latitude"), row.get("longitude"))
            candidate = {
                "name": str(row.get("name")),
                "category": category,
                "distanceMiles": round(distance, 3),
                "evidenceDate": observed.isoformat(),
                "effectiveFrom": effective_from.isoformat() if effective_from else None,
                "effectiveTo": effective_to.isoformat() if effective_to else None,
                "sourceReference": str(row.get("source_reference")),
                "sourceRow": row.get("source_row"),
            }
            current = nearest.get(category)
            if current is None or (candidate["distanceMiles"], candidate["name"]) < (
                    current["distanceMiles"], current["name"]):
                nearest[category] = candidate
        except (KeyError, TypeError, ValueError):
            rejected["invalid"] += 1

    findings = []
    for category in sorted(CATEGORIES):
        threshold = float(governed_thresholds[category])
        evidence = nearest.get(category)
        if evidence is None:
            state = "coverage_missing"
            statement = f"No {category.replace('_', ' ')} appears in the imported evidence coverage; this is not evidence of absence."
        elif evidence["distanceMiles"] <= threshold:
            state = "within_analyst_threshold"
            statement = f"Nearest identified {category.replace('_', ' ')} is {evidence['distanceMiles']:.1f} straight-line miles away."
        else:
            state = "beyond_analyst_threshold"
            statement = (f"Nearest identified {category.replace('_', ' ')} is {evidence['distanceMiles']:.1f} straight-line miles away, "
                         f"beyond the {threshold:.1f}-mile analyst threshold.")
        findings.append({"category": category, "state": state, "analystThresholdMiles": threshold,
                         "statement": statement, "evidence": evidence})
    return {
        "findings": findings,
        "nearestByCategory": nearest,
        "rejected": rejected,
        "methodology": {
            "distanceMethod": "haversine_straight_line",
            "travelTimeAvailable": False,
            "thresholdPolicy": "analyst-configured descriptive thresholds",
            "prohibitedInferences": [
                "school_quality", "crime_or_safety", "protected_class_demographics",
                "neighborhood_desirability", "causal_investment_performance",
            ],
            "warning": "Proximity is factual context, not a quality, safety, desirability, accessibility, or investment-performance conclusion.",
        },
    }
