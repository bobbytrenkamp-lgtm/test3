from __future__ import annotations

from datetime import date


FALLBACKS = (
    ("exact_submarket_property_subtype", 1.0, 1.0),
    ("exact_market_property_subtype", .9, 1.0),
    ("exact_market_property_type", .9, .85),
    ("cbsa_property_type", .75, .85),
    ("state_property_type", .55, .85),
    ("national_property_type", .35, .85),
)


def select_fallback(observations: list[dict], deal: dict, context: dict) -> tuple[str, list[dict], float, float]:
    property_type = deal.get("property_type")
    subtype = context.get("property_subtype")
    checks = (
        lambda row: subtype and context.get("submarket") and row.get("submarket") == context["submarket"] and row.get("property_subtype") == subtype,
        lambda row: subtype and context.get("market_id") and row.get("geography_id") == context["market_id"] and row.get("property_subtype") == subtype,
        lambda row: context.get("market_id") and row.get("geography_id") == context["market_id"] and row.get("property_type") == property_type,
        lambda row: context.get("cbsa") and row.get("cbsa") == context["cbsa"] and row.get("property_type") == property_type,
        lambda row: context.get("state_fips") and str(row.get("county_fips") or "").startswith(str(context["state_fips"])) and row.get("property_type") == property_type,
        lambda row: row.get("property_type") == property_type,
    )
    for (level, geography_score, property_score), check in zip(FALLBACKS, checks):
        matched = [row for row in observations if check(row)]
        if matched:
            return level, matched, geography_score, property_score
    return "unavailable", [], 0.0, 0.0


def freshness_score(latest_date: str | None, as_of: date | None = None) -> float:
    if not latest_date:
        return 0.0
    age = ((as_of or date.today()) - date.fromisoformat(latest_date)).days
    return 1.0 if age <= 120 else .75 if age <= 365 else .4 if age <= 730 else .1
