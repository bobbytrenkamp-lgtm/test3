from __future__ import annotations

from decimal import Decimal

from .schema import normalize_cre_record


def _quarter_index(period: str) -> int:
    if len(period) != 7 or period[4:6] != "-Q" or period[-1] not in "1234":
        raise ValueError("derivation requires canonical quarterly periods")
    return int(period[:4]) * 4 + int(period[-1]) - 1


def derive_rent_growth_yoy(rows: list[dict], *, transformation_version: str = "rent-growth-yoy/1.0.0") -> list[dict]:
    """Derive exact-period YoY growth only within a consistent rent series."""
    output = []
    grouped = {}
    for row in rows:
        if row["metric"] not in {"asking_rent", "effective_rent"} or row["frequency"] != "quarterly":
            continue
        key = (row["geography_type"], row["geography_id"], row["property_type"], row.get("property_subtype"),
               row["metric"], row["unit"], row["methodology"], row["source_name"], row.get("methodology_version"))
        grouped.setdefault(key, {}).setdefault(_quarter_index(row["period"]), []).append(row)
    for series in grouped.values():
        for current_index, current_rows in sorted(series.items()):
            prior_rows = series.get(current_index - 4, [])
            if len(current_rows) != 1 or len(prior_rows) != 1:
                continue
            current, prior = current_rows[0], prior_rows[0]
            if Decimal(prior["value"]) == 0:
                continue
            growth = Decimal(current["value"]) / Decimal(prior["value"]) - 1
            method = "asking_rent_yoy" if current["metric"] == "asking_rent" else "effective_rent_yoy"
            raw = {**current, "metric": "rent_growth_yoy", "value": format(growth, "f"), "unit": "decimal_fraction",
                   "methodology": method, "source_identifier": f"derived:{prior['observation_id']}:{current['observation_id']}",
                   "verification_status": "unverified", "source_period": current["period"],
                   "notes": f"Derived by ({current['observation_id']} / {prior['observation_id']}) - 1; transformation={transformation_version}."}
            output.append(normalize_cre_record(raw, row_number=int(current.get("source_row", 0))))
    return output


def derive_vacancy_from_occupancy(rows: list[dict], *, transformation_version: str = "vacancy-from-occupancy/1.0.0") -> list[dict]:
    output = []
    for row in rows:
        if row["metric"] != "occupancy_rate":
            continue
        if row["methodology"] not in {"physical_occupancy", "economic_occupancy"}:
            continue
        vacancy_method = "physical_vacancy" if row["methodology"] == "physical_occupancy" else "economic_vacancy"
        raw = {**row, "metric": "vacancy_rate", "value": format(Decimal(1) - Decimal(row["value"]), "f"),
               "methodology": vacancy_method, "source_identifier": f"derived:{row['observation_id']}",
               "verification_status": "unverified",
               "notes": f"Derived exactly as 1 - occupancy; transformation={transformation_version}; input={row['observation_id']}."}
        output.append(normalize_cre_record(raw, row_number=int(row.get("source_row", 0))))
    return output


def derive_noi_margin(rows: list[dict], *, transformation_version: str = "noi-margin/1.0.0") -> list[dict]:
    """Derive NOI margin only from an unambiguous same-source revenue/NOI pair."""
    grouped: dict[tuple, dict[str, list[dict]]] = {}
    for row in rows:
        if row["metric"] not in {"same_store_revenue", "same_store_noi"}:
            continue
        key = (row["geography_type"], row["geography_id"], row["period"], row["property_type"],
               row.get("property_subtype"), row["source_name"], row.get("methodology_version"), row["unit"])
        grouped.setdefault(key, {}).setdefault(row["metric"], []).append(row)
    output = []
    for metrics in grouped.values():
        revenue_rows = metrics.get("same_store_revenue", [])
        noi_rows = metrics.get("same_store_noi", [])
        if len(revenue_rows) != 1 or len(noi_rows) != 1:
            continue
        revenue, noi = revenue_rows[0], noi_rows[0]
        if Decimal(revenue["value"]) <= 0:
            continue
        margin = Decimal(noi["value"]) / Decimal(revenue["value"])
        raw = {
            **noi,
            "metric": "noi_margin",
            "value": format(margin, "f"),
            "unit": "decimal_fraction",
            "methodology": "same_store_noi_margin",
            "source_identifier": f"derived:{revenue['observation_id']}:{noi['observation_id']}",
            "verification_status": "unverified",
            "notes": (
                f"Derived exactly as NOI / operating revenue; transformation={transformation_version}; "
                f"inputs={revenue['observation_id']},{noi['observation_id']}."
            ),
        }
        output.append(normalize_cre_record(raw, row_number=int(noi.get("source_row", 0))))
    return output
