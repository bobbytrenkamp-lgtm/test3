from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from statistics import median

from test3.research.comparables import distance_miles


MAX_ROWS = 10_000
PRICE_UNITS = {"USD/property", "USD/unit", "USD/sf"}
REQUIRED_COLUMNS = {
    "address", "latitude", "longitude", "property_type", "sale_price",
    "price_unit", "sale_date", "source_reference",
}


def parse_sale_comps(text: str) -> list[dict]:
    if len(text.encode()) > 8 * 1024 * 1024:
        raise ValueError("sale-comparable CSV exceeds 8 MiB")
    reader = csv.DictReader(StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"sale-comparable CSV is missing required columns: {sorted(missing)}")
    rows = []
    for number, row in enumerate(reader, 2):
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"sale-comparable CSV exceeds {MAX_ROWS} rows")
        clean = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
        blank = sorted(field for field in REQUIRED_COLUMNS if not clean.get(field))
        if blank:
            raise ValueError(f"sale-comparable CSV row {number} has blank required fields: {blank}")
        clean["source_row"] = number
        rows.append(clean)
    return rows


def _optional_positive(value: object, name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric when provided") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be positive when provided")
    return result


def _implied_subject_value(value: Decimal, unit: str, subject: dict) -> Decimal | None:
    if unit == "USD/property":
        return value
    if unit == "USD/unit":
        units = _optional_positive(subject.get("units"), "subject units")
        return value * units if units else None
    area = _optional_positive(subject.get("rentable_sf"), "subject rentable_sf")
    return value * area if area else None


def analyze_sale_comps(subject: dict, rows: list[dict], *, analysis_as_of: date,
                       max_distance_miles: float = 15.0, maximum_age_days: int = 730,
                       limit: int = 10) -> dict:
    if not 0 < max_distance_miles <= 250:
        raise ValueError("maximum sale-comp distance must be greater than zero and no more than 250 miles")
    if not 30 <= maximum_age_days <= 3650:
        raise ValueError("maximum sale-comp age must be between 30 and 3650 days")
    property_type = str(subject.get("property_type") or "").strip().lower()
    latitude, longitude = float(subject["latitude"]), float(subject["longitude"])
    subject_units = _optional_positive(subject.get("units"), "subject units")
    subject_year = _optional_positive(subject.get("year_built"), "subject year_built")
    ranked = []
    rejected = {"property_type_mismatch": 0, "outside_radius": 0, "future_evidence": 0,
                "stale_evidence": 0, "invalid": 0}
    for row in rows[:MAX_ROWS]:
        try:
            if str(row.get("property_type") or "").strip().lower() != property_type:
                rejected["property_type_mismatch"] += 1
                continue
            observed = date.fromisoformat(str(row.get("sale_date")))
            age = (analysis_as_of - observed).days
            if age < 0:
                rejected["future_evidence"] += 1
                continue
            if age > maximum_age_days:
                rejected["stale_evidence"] += 1
                continue
            distance = distance_miles(latitude, longitude, row.get("latitude"), row.get("longitude"))
            if distance > max_distance_miles:
                rejected["outside_radius"] += 1
                continue
            price = _optional_positive(row.get("sale_price"), "sale price")
            unit = str(row.get("price_unit"))
            if price is None or unit not in PRICE_UNITS:
                raise ValueError("sale price and governed price unit are required")
            factors = [("distance", max(0.0, 1 - distance / max_distance_miles), 0.4),
                       ("recency", max(0.0, 1 - age / maximum_age_days), 0.2)]
            comp_units = _optional_positive(row.get("units"), "comp units")
            if subject_units and comp_units:
                factors.append(("unit_count", float(min(subject_units, comp_units) / max(subject_units, comp_units)), 0.2))
            comp_year = _optional_positive(row.get("year_built"), "comp year_built")
            if subject_year and comp_year:
                factors.append(("year_built", max(0.0, 1 - float(abs(subject_year - comp_year)) / 50), 0.2))
            score = sum(value * weight for _, value, weight in factors) / sum(weight for _, _, weight in factors)
            implied = _implied_subject_value(price, unit, subject)
            ranked.append({
                "address": str(row.get("address")), "distanceMiles": round(distance, 3),
                "salePrice": format(price, "f"), "priceUnit": unit, "saleDate": observed.isoformat(),
                "units": format(comp_units, "f") if comp_units else None,
                "yearBuilt": format(comp_year, "f") if comp_year else None,
                "similarityScore": round(score, 6),
                "scoreComponents": {name: round(value, 6) for name, value, _ in factors},
                "impliedSubjectValue": format(implied, "f") if implied is not None else None,
                "sourceReference": str(row.get("source_reference")), "sourceRow": row.get("source_row"),
            })
        except (KeyError, TypeError, ValueError, InvalidOperation):
            rejected["invalid"] += 1
    ranked.sort(key=lambda row: (-row["similarityScore"], row["distanceMiles"], row["address"]))
    selected = ranked[:max(1, min(limit, 50))]
    price_units = sorted({row["priceUnit"] for row in selected})
    implied_values = [Decimal(row["impliedSubjectValue"]) for row in selected if row["impliedSubjectValue"]]
    benchmark = None
    if selected and len(price_units) == 1 and len(implied_values) == len(selected):
        source_values = [Decimal(row["salePrice"]) for row in selected]
        benchmark = {
            "count": len(selected), "priceUnit": price_units[0],
            "sourceMinimum": format(min(source_values), "f"),
            "sourceMedian": format(median(source_values), "f"),
            "sourceMaximum": format(max(source_values), "f"),
            "impliedSubjectValueMinimum": format(min(implied_values), "f"),
            "impliedSubjectValueMedian": format(median(implied_values), "f"),
            "impliedSubjectValueMaximum": format(max(implied_values), "f"),
        }
    return {"comparables": selected, "benchmark": benchmark, "rejected": rejected,
            "priceUnits": price_units,
            "methodology": "Available-factor score: distance 40%, recency 20%, unit count 20%, year built 20%; missing optional factors are renormalized."}
