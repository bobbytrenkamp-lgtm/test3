from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json

from test3.research.comparables import analyze_location

from .sales import analyze_sale_comps


SCHEMA_VERSION = "test3-property-opportunity/1.0.0"
POLICY_VERSION = "property-opportunity-screening/1.0.0"
RIGHTS_STATUSES = {"public_open", "user_owned", "licensed_local", "unknown_review_required"}


def _hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decimal(value: object, name: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not result.is_finite() or (positive and result <= 0) or (not positive and result < 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return result


def _source_metadata(value: dict, name: str) -> dict:
    source_name = str(value.get("source_name") or "").strip()
    licensing_notes = str(value.get("licensing_notes") or "").strip()
    rights_status = str(value.get("rights_status") or "").strip()
    if not source_name or not licensing_notes:
        raise ValueError(f"{name} source name and licensing notes are required")
    if rights_status not in RIGHTS_STATUSES:
        raise ValueError(f"{name} rights_status must be one of {sorted(RIGHTS_STATUSES)}")
    return {"sourceName": source_name, "licensingNotes": licensing_notes, "rightsStatus": rights_status,
            "rightsDocumented": rights_status != "unknown_review_required"}


def _eligible_rents(rows: list[dict], *, as_of: date, maximum_age_days: int) -> tuple[list[dict], dict]:
    eligible, excluded = [], {"future_evidence": 0, "stale_evidence": 0, "invalid_date": 0}
    for row in rows:
        try:
            observed = date.fromisoformat(str(row.get("observed_date")))
        except ValueError:
            excluded["invalid_date"] += 1
            continue
        age = (as_of - observed).days
        if age < 0:
            excluded["future_evidence"] += 1
        elif age > maximum_age_days:
            excluded["stale_evidence"] += 1
        else:
            eligible.append(row)
    return eligible, excluded


def _screening_scenarios(subject: dict, sale_benchmark: dict | None) -> dict | None:
    if not sale_benchmark:
        return None
    purchase = _decimal(subject.get("purchase_price"), "purchase_price", positive=True)
    renovation = _decimal(subject.get("renovation_budget", 0), "renovation_budget")
    closing = _decimal(subject.get("closing_costs", 0), "closing_costs")
    holding = _decimal(subject.get("holding_costs", 0), "holding_costs")
    total_basis = purchase + renovation + closing + holding
    values = {
        "downside": Decimal(sale_benchmark["impliedSubjectValueMinimum"]),
        "base": Decimal(sale_benchmark["impliedSubjectValueMedian"]),
        "upside": Decimal(sale_benchmark["impliedSubjectValueMaximum"]),
    }
    cases = {}
    for name, indicated_value in values.items():
        wedge = indicated_value - total_basis
        cases[name] = {"indicatedValue": format(indicated_value, "f"),
                       "estimatedEquityWedge": format(wedge, "f"),
                       "wedgeToBasis": format(wedge / total_basis, "f")}
    return {
        "method": "descriptive_selected_sale_comp_minimum_median_maximum",
        "notAConfidenceInterval": True,
        "purchasePrice": format(purchase, "f"), "renovationBudget": format(renovation, "f"),
        "closingCosts": format(closing, "f"), "holdingCosts": format(holding, "f"),
        "totalEstimatedBasis": format(total_basis, "f"), "cases": cases,
    }


def analyze_property_opportunity(subject: dict, rent_comps: list[dict], sale_comps: list[dict], *,
                                 analysis_as_of: str, source_metadata: dict,
                                 max_distance_miles: float = 15.0, rent_maximum_age_days: int = 365,
                                 sale_maximum_age_days: int = 730, limit: int = 10) -> dict:
    """Build a deterministic research artifact, never a controlling underwriting result."""
    as_of = date.fromisoformat(str(analysis_as_of))
    property_type = str(subject.get("property_type") or "").strip().lower()
    if not property_type:
        raise ValueError("subject property_type is required")
    normalized_subject = {**subject, "property_type": property_type,
                          "latitude": float(subject["latitude"]), "longitude": float(subject["longitude"])}
    if not -90 <= normalized_subject["latitude"] <= 90 or not -180 <= normalized_subject["longitude"] <= 180:
        raise ValueError("subject coordinates are outside their valid range")
    sources = {name: _source_metadata(source_metadata.get(name) or {}, name)
               for name in ("rent_comps", "sale_comps")}
    eligible_rents, rent_date_exclusions = _eligible_rents(
        rent_comps, as_of=as_of, maximum_age_days=rent_maximum_age_days)
    rent_result = analyze_location(normalized_subject, eligible_rents, [],
                                   max_comp_distance_miles=max_distance_miles, limit=limit)
    sale_result = analyze_sale_comps(normalized_subject, sale_comps, analysis_as_of=as_of,
                                     max_distance_miles=max_distance_miles,
                                     maximum_age_days=sale_maximum_age_days, limit=limit)
    rent_rejected = {**rent_result["rejectedComparables"], **rent_date_exclusions}
    rent_benchmark = rent_result["rentBenchmark"]
    gross_rent_proxy = None
    units = subject.get("units")
    if rent_benchmark and rent_benchmark["rentUnit"] == "USD/unit/month" and units not in (None, ""):
        unit_count = _decimal(units, "subject units", positive=True)
        monthly = Decimal(rent_benchmark["median"]) * unit_count
        gross_rent_proxy = {"monthly": format(monthly, "f"), "annual": format(monthly * 12, "f"),
                            "method": "selected_rent_comp_median_times_subject_units",
                            "warning": "Gross potential rent proxy only; excludes vacancy, concessions, expenses and downtime."}
    scenarios = _screening_scenarios(normalized_subject, sale_result["benchmark"])
    components = {
        "rentComparableCount": len(rent_result["rentComparables"]),
        "saleComparableCount": len(sale_result["comparables"]),
        "minimumComparableCount": 3,
        "rentComparableMinimumMet": len(rent_result["rentComparables"]) >= 3,
        "saleComparableMinimumMet": len(sale_result["comparables"]) >= 3,
        "saleUnitsConsistent": len(sale_result["priceUnits"]) <= 1,
        "sourceRightsDocumented": all(item["rightsDocumented"] for item in sources.values()),
        "futureEvidenceExcluded": rent_date_exclusions["future_evidence"] + sale_result["rejected"]["future_evidence"],
        "staleEvidenceExcluded": rent_date_exclusions["stale_evidence"] + sale_result["rejected"]["stale_evidence"],
    }
    core_passes = all(components[name] for name in
                      ("rentComparableMinimumMet", "saleComparableMinimumMet", "saleUnitsConsistent",
                       "sourceRightsDocumented"))
    quality = "high" if core_passes and min(components["rentComparableCount"], components["saleComparableCount"]) >= 5 else (
        "moderate" if core_passes else "low")
    output = {
        "schemaVersion": SCHEMA_VERSION, "policyVersion": POLICY_VERSION,
        "status": "RESEARCH_CANDIDATE_NOT_UNDERWRITING", "analysisAsOf": as_of.isoformat(),
        "subject": normalized_subject, "sources": sources,
        "rentEvidence": {"comparables": rent_result["rentComparables"], "benchmark": rent_benchmark,
                         "rejected": rent_rejected, "grossPotentialRentProxy": gross_rent_proxy},
        "saleEvidence": sale_result, "screeningScenarios": scenarios,
        "quality": {"level": quality, "components": components},
        "governance": {"analystApprovalRequired": True, "eligibleForAutomaticUnderwriting": False,
                       "test2AssumptionsOverwritten": False, "scoreProduced": False},
        "limitations": [
            "Comparable indications are descriptive and are not appraisals, forecasts, offers, or certified market values.",
            "The equity-wedge screen excludes financing, taxes, insurance, operating expenses, sale costs and tax consequences.",
            "Source-rights status is analyst supplied and is not a legal determination by Test3.",
            "No physical-condition or renovation-scope conclusion is inferred from market data.",
            "Selected comparable minimum/median/maximum values are not statistical confidence intervals.",
        ],
    }
    output["analysisInputHash"] = _hash({"subject": normalized_subject, "rentComps": rent_comps,
                                         "saleComps": sale_comps, "analysisAsOf": as_of.isoformat(),
                                         "sources": sources, "policyVersion": POLICY_VERSION,
                                         "maxDistanceMiles": max_distance_miles,
                                         "rentMaximumAgeDays": rent_maximum_age_days,
                                         "saleMaximumAgeDays": sale_maximum_age_days, "limit": limit})
    output["artifactHash"] = _hash(output)
    return output
