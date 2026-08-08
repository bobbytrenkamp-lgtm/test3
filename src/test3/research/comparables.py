from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from math import asin, cos, radians, sin, sqrt
from statistics import median

MAX_ROWS = 10_000
POI_CATEGORIES = {"school", "shopping_center", "grocery", "downtown", "transit", "park", "hospital"}
DEFAULT_THRESHOLDS_MILES = {"school": 1.5, "shopping_center": 3.0, "grocery": 2.0, "downtown": 10.0, "transit": 1.0, "park": 2.0, "hospital": 5.0}


def _coordinate(value: object, name: str, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not low <= result <= high:
        raise ValueError(f"{name} is outside its valid range")
    return result


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1 = _coordinate(lat1, "latitude", -90, 90), _coordinate(lon1, "longitude", -180, 180)
    lat2, lon2 = _coordinate(lat2, "latitude", -90, 90), _coordinate(lon2, "longitude", -180, 180)
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 3958.7613 * 2 * asin(sqrt(value))


def parse_csv_records(text: str, kind: str) -> list[dict]:
    if len(text.encode()) > 8 * 1024 * 1024:
        raise ValueError("location dataset exceeds 8 MiB")
    reader = csv.DictReader(StringIO(text))
    required = ({"address", "latitude", "longitude", "property_type", "asking_rent", "rent_unit", "observed_date", "source_reference"}
                if kind == "comps" else {"name", "category", "latitude", "longitude", "source_reference"})
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise ValueError(f"{kind} CSV is missing required columns: {sorted(required - set(reader.fieldnames or []))}")
    rows = []
    for number, row in enumerate(reader, 2):
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"{kind} CSV exceeds {MAX_ROWS} rows")
        clean = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
        blank = sorted(field for field in required if not clean.get(field))
        if blank:
            raise ValueError(f"{kind} CSV row {number} has blank required fields: {blank}")
        clean["source_row"] = number
        rows.append(clean)
    return rows


def _optional_number(value: object, name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric when provided") from exc
    return result


def analyze_location(subject: dict, comps: list[dict], pois: list[dict], *, max_comp_distance_miles: float = 15.0,
                     thresholds: dict[str, float] | None = None, limit: int = 10) -> dict:
    latitude = _coordinate(subject.get("latitude"), "subject latitude", -90, 90)
    longitude = _coordinate(subject.get("longitude"), "subject longitude", -180, 180)
    property_type = str(subject.get("property_type") or "").strip().lower()
    if not property_type:
        raise ValueError("subject property_type is required")
    if not 0 < max_comp_distance_miles <= 250:
        raise ValueError("max_comp_distance_miles must be greater than zero and no more than 250")
    subject_units = _optional_number(subject.get("units"), "subject units")
    subject_year = _optional_number(subject.get("year_built"), "subject year_built")
    ranked = []
    rejected = {"property_type_mismatch": 0, "outside_radius": 0, "invalid": 0}
    for row in comps[:MAX_ROWS]:
        try:
            if str(row.get("property_type") or "").strip().lower() != property_type:
                rejected["property_type_mismatch"] += 1
                continue
            distance = distance_miles(latitude, longitude, row.get("latitude"), row.get("longitude"))
            if distance > max_comp_distance_miles:
                rejected["outside_radius"] += 1
                continue
            rent = Decimal(str(row.get("asking_rent")))
            if not rent.is_finite() or rent <= 0:
                raise ValueError("rent must be positive")
            date.fromisoformat(str(row.get("observed_date")))
            factors = [("distance", max(0.0, 1 - distance / max_comp_distance_miles), 0.5)]
            comp_units = _optional_number(row.get("units"), "comp units")
            if subject_units and comp_units and subject_units > 0 and comp_units > 0:
                factors.append(("unit_count", min(subject_units, comp_units) / max(subject_units, comp_units), 0.25))
            comp_year = _optional_number(row.get("year_built"), "comp year_built")
            if subject_year and comp_year:
                factors.append(("year_built", max(0.0, 1 - abs(subject_year - comp_year) / 50), 0.25))
            score = sum(value * weight for _, value, weight in factors) / sum(weight for _, _, weight in factors)
            ranked.append({"address": str(row.get("address")), "distanceMiles": round(distance, 3),
                           "askingRent": format(rent, "f"), "rentUnit": str(row.get("rent_unit")),
                           "observedDate": str(row.get("observed_date")), "units": comp_units, "yearBuilt": comp_year,
                           "similarityScore": round(score, 6), "scoreComponents": {name: round(value, 6) for name, value, _ in factors},
                           "sourceReference": str(row.get("source_reference")), "sourceRow": row.get("source_row")})
        except (ValueError, InvalidOperation):
            rejected["invalid"] += 1
    ranked.sort(key=lambda row: (-row["similarityScore"], row["distanceMiles"], row["address"]))
    selected = ranked[:max(1, min(limit, 50))]
    units = sorted({row["rentUnit"] for row in selected})
    rents = [Decimal(row["askingRent"]) for row in selected]
    benchmark = None if not rents or len(units) != 1 else {"count": len(rents), "rentUnit": units[0], "minimum": format(min(rents), "f"),
                                                            "median": format(median(rents), "f"), "maximum": format(max(rents), "f")}
    thresholds = {**DEFAULT_THRESHOLDS_MILES, **(thresholds or {})}
    nearest = {}
    for row in pois[:MAX_ROWS]:
        category = str(row.get("category") or "").strip().lower()
        if category not in POI_CATEGORIES:
            continue
        try:
            distance = distance_miles(latitude, longitude, row.get("latitude"), row.get("longitude"))
        except ValueError:
            continue
        candidate = {"name": str(row.get("name")), "category": category, "distanceMiles": round(distance, 3),
                     "sourceReference": str(row.get("source_reference")), "sourceRow": row.get("source_row")}
        if category not in nearest or distance < nearest[category]["distanceMiles"]:
            nearest[category] = candidate
    positives, considerations = [], []
    for category, threshold in thresholds.items():
        item = nearest.get(category)
        label = category.replace("_", " ")
        if item and item["distanceMiles"] <= threshold:
            positives.append({"factor": label, "statement": f"Nearest {label} is {item['distanceMiles']:.1f} miles away.", "evidence": item})
        elif item:
            considerations.append({"factor": label, "statement": f"Nearest identified {label} is {item['distanceMiles']:.1f} miles away, beyond the {threshold:.1f}-mile analyst threshold.", "evidence": item})
        else:
            considerations.append({"factor": label, "statement": f"No {label} was present in the imported POI coverage; absence is not proof that none exists.", "evidence": None})
    return {"subject": {"address": subject.get("address"), "latitude": latitude, "longitude": longitude, "propertyType": property_type},
            "rentComparables": selected, "rentBenchmark": benchmark, "rejectedComparables": rejected,
            "areaPositives": positives, "areaConsiderations": considerations, "nearestByCategory": nearest,
            "methodology": {"distanceMethod": "haversine", "maxCompDistanceMiles": max_comp_distance_miles,
                            "similarity": "Available-factor weighted score: distance 50%, unit count 25%, year built 25%.",
                            "warning": "Descriptive evidence only. Proximity is not a quality, safety, school-performance, or causal assessment."}}
