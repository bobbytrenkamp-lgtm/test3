from __future__ import annotations

from decimal import Decimal

from test3.cre_data.geography import market_definitions
from test3.cre_data.versions import verification_reports
from test3.features.registry import FEATURE_REGISTRY
from test3.research.specifications import MODEL_SPECIFICATIONS, ModelSpecification
from test3.research.target_panel import target_readiness_for_specification
from test3.warehouse.storage import WarehousePaths


def analyst_attestation_status(paths: WarehousePaths, *, source_name_contains: str = "Mid-America") -> dict:
    rows = [row for report in verification_reports(paths) for row in report.get("observations", [])
            if source_name_contains.casefold() in str(row.get("source_name", "")).casefold()]
    approved = [row for row in rows if row.get("verification_status") == "analyst_verified"]
    return {
        "status": "APPROVED" if approved else ("AWAITING_ANALYST_ATTESTATION" if rows else "NO_CANDIDATE_DATA"),
        "candidate_observations": len(rows),
        "approved_observations": len(approved),
        "markets": len({row.get("geography_id") for row in rows}),
        "periods": len({row.get("period") for row in rows}),
        "human_attestation_required": True,
    }


def market_definition_coverage(paths: WarehousePaths, *, source_name_contains: str = "Mid-America") -> list[dict]:
    rows = [row for report in verification_reports(paths) for row in report.get("observations", [])
            if source_name_contains.casefold() in str(row.get("source_name", "")).casefold()
            and row.get("property_type") == "multifamily"]
    definitions = market_definitions(paths)
    output = []
    for market in sorted({str(row["geography_id"]) for row in rows}):
        matches = [item for item in definitions if item.get("market_id") == market
                   and item.get("property_type") == "multifamily"]
        approved = [item for item in matches if item.get("review_status") == "analyst_approved"]
        valid = len(approved) == 1
        definition = approved[0] if valid else (matches[-1] if matches else None)
        weight_sum = (sum((Decimal(str(item["weight"])) for item in definition["counties"]), Decimal("0"))
                      if definition else None)
        reason = None
        if not matches:
            reason = "missing governed market definition"
        elif not approved:
            reason = "market definition is not analyst approved"
        elif len(approved) > 1:
            reason = "multiple approved definitions require effective-period resolution"
        elif weight_sum != Decimal("1"):
            reason = "county weights do not total exactly 1.0"
        output.append({
            "source_market": market,
            "definition_status": definition.get("review_status") if definition else "missing",
            "market_definition_id": definition.get("market_id") if definition else None,
            "market_definition_version": definition.get("definition_version") if definition else None,
            "counties": len(definition.get("counties", ())) if definition else 0,
            "weight_sum": format(weight_sum, "f") if weight_sum is not None else None,
            "feature_eligible": bool(valid and weight_sum == Decimal("1")),
            "reason_if_excluded": reason,
            "definition_hash": definition.get("sha256") if definition else None,
        })
    return output


def _native_frequencies(feature_name: str, seen: frozenset[str] = frozenset()) -> set[str]:
    if feature_name in seen:
        return set()
    spec = FEATURE_REGISTRY.get(feature_name)
    if spec is None:
        return set()
    if spec.input_metrics:
        # Source definitions with only annual support are annual-native. Macro
        # period aggregations preserve their public source frequency explicitly.
        if spec.transformation in {"period_mean_broadcast", "period_end_broadcast"}:
            return {"daily_or_monthly"}
        return {"annual"} if spec.frequencies == ("annual",) else {"annual"}
    native = set()
    for parent in spec.input_features:
        native.update(_native_frequencies(parent, seen | {feature_name}))
    return native


def feature_compatibility(specification: ModelSpecification) -> list[dict]:
    output = []
    for name in specification.features:
        feature = FEATURE_REGISTRY.get(name)
        eligible = feature is not None and specification.frequency in feature.frequencies
        native = sorted(_native_frequencies(name)) if feature else []
        transformation = feature.transformation if feature else None
        if eligible and "annual" in native and specification.frequency == "quarterly":
            transformation = f"{transformation}; annual carry-forward with original availability retained"
        output.append({
            "feature": name,
            "native_frequency": ",".join(native) or "unknown",
            "model_frequency": specification.frequency,
            "transformation": transformation,
            "release_lag": "source as_of_date; conservative retrieval-date fallback",
            "eligible": eligible,
            "reason": None if eligible else "feature is not registered for model frequency",
        })
    return output


def milestone7_status(paths: WarehousePaths) -> dict:
    attestation = analyst_attestation_status(paths)
    coverage = market_definition_coverage(paths)
    approved_definitions = sum(item["feature_eligible"] for item in coverage)
    decisions = []
    for name in sorted(MODEL_SPECIFICATIONS):
        spec = MODEL_SPECIFICATIONS[name]
        if spec.target != "rent_growth_yoy" or spec.property_type != "multifamily":
            continue
        readiness = target_readiness_for_specification(paths, spec)
        compatibility = feature_compatibility(spec)
        blockers = list(readiness["reasons"])
        if attestation["status"] != "APPROVED":
            blockers.insert(0, attestation["status"])
        if approved_definitions == 0:
            blockers.append("no analyst-approved MAA market definitions")
        blockers.extend(item["reason"] for item in compatibility if not item["eligible"])
        decisions.append({
            "model_specification": name,
            "purpose": spec.purpose,
            "status": "NOT_EVALUATED_PREREQUISITE_GATE",
            "promotion_status": "not_promoted",
            "blockers": list(dict.fromkeys(blockers)),
            "readiness": readiness,
            "feature_compatibility": compatibility,
            "walk_forward": None,
            "baselines": None,
            "market_holdout": None,
            "stability": None,
            "independent_cross_check": None,
        })
    return {
        "milestone": 7,
        "target": "multifamily rent_growth_yoy quarterly",
        "attestation": attestation,
        "market_definition_coverage": coverage,
        "models": decisions,
        "validated_forecast_available": False,
        "forecast_message": "No validated forecast is currently available.",
        "overall_status": "AWAITING_ANALYST_ATTESTATION" if attestation["status"] != "APPROVED"
                          else "AWAITING_GOVERNED_MARKET_DEFINITIONS",
    }
