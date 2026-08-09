from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RecommendationPolicy:
    policy_id: str
    version: str
    property_type: str
    assumption_type: str
    quality_tier: str
    model_weight: Decimal
    historical_weight: Decimal
    recent_weight: Decimal
    minimum_downside_buffer: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.model_weight + self.historical_weight + self.recent_weight != Decimal("1"):
            raise ValueError("recommendation policy weights must total one")


def _policy(policy_id: str, property_type: str, assumption_type: str, tier: str,
            model: str, historical: str, recent: str) -> RecommendationPolicy:
    return RecommendationPolicy(policy_id, "1.0.0", property_type, assumption_type, tier,
                                Decimal(model), Decimal(historical), Decimal(recent))


RECOMMENDATION_POLICIES = {
    ("multifamily", "market_rent_growth", "weak"): _policy(
        "mf-rent-growth", "multifamily", "market_rent_growth", "weak", ".25", ".50", ".25"),
    ("multifamily", "market_rent_growth", "moderate"): _policy(
        "mf-rent-growth", "multifamily", "market_rent_growth", "moderate", ".40", ".40", ".20"),
    ("multifamily", "market_rent_growth", "strong"): _policy(
        "mf-rent-growth", "multifamily", "market_rent_growth", "strong", ".50", ".35", ".15"),
    ("multifamily", "vacancy", "weak"): _policy(
        "mf-vacancy", "multifamily", "vacancy", "weak", ".20", ".55", ".25"),
    ("multifamily", "vacancy", "moderate"): _policy(
        "mf-vacancy", "multifamily", "vacancy", "moderate", ".35", ".45", ".20"),
    ("multifamily", "vacancy", "strong"): _policy(
        "mf-vacancy", "multifamily", "vacancy", "strong", ".45", ".40", ".15"),
}


def _model_quality(forecast: dict) -> tuple[str, Decimal, dict]:
    validation = forecast.get("validation", {})
    model_mae = Decimal(str(validation.get("walk_forward_mae") or "0"))
    baseline_mae = Decimal(str(validation.get("baseline_mae") or "0"))
    holdout_mae = Decimal(str(validation.get("market_holdout_mae") or "0"))
    improvement = max(Decimal("0"), baseline_mae - model_mae)
    improvement_ratio = improvement / baseline_mae if baseline_mae > 0 else Decimal("0")
    holdout_ratio = model_mae / holdout_mae if holdout_mae > 0 else Decimal("0")
    stability = forecast.get("model_quality", {}).get("stability", {})
    stable = not bool(stability.get("severe_instability"))
    python_ok = forecast.get("model_quality", {}).get("python_reference_status", "passed") == "passed"
    r_status = forecast.get("model_quality", {}).get("r_cross_check_status", "not_available")
    cross_checks_ok = python_ok and r_status in {"passed", "not_available"}
    score = (min(Decimal("1"), improvement_ratio * Decimal("2")) * Decimal(".55")
             + min(Decimal("1"), holdout_ratio) * Decimal(".25")
             + (Decimal(".10") if stable else Decimal("0"))
             + (Decimal(".10") if cross_checks_ok else Decimal("0")))
    tier = "strong" if score >= Decimal(".75") else "moderate" if score >= Decimal(".45") else "weak"
    return tier, min(Decimal("1"), score), {
        "walk_forward_improvement_ratio": str(improvement_ratio),
        "holdout_reliability_ratio": str(holdout_ratio),
        "stability_passed": stable, "cross_checks_passed": cross_checks_ok,
    }


def select_recommendation_policy(*, property_type: str, assumption_type: str,
                                 forecast: dict) -> tuple[RecommendationPolicy, Decimal, dict]:
    tier, score, evidence = _model_quality(forecast)
    selected = RECOMMENDATION_POLICIES.get((property_type, assumption_type, tier))
    if selected is None:
        # A conservative governed fallback keeps unsupported assumption/property pairs research-only.
        selected = _policy(f"{property_type}-{assumption_type}", property_type, assumption_type,
                           tier, ".20", ".55", ".25")
    return selected, score, evidence


def governed_model_forecast(model_artifact: dict | None, *, property_type: str, assumption_type: str) -> dict | None:
    if not model_artifact or model_artifact.get("data_status") != "real" or model_artifact.get("validation_state") != "validated":
        return None
    if assumption_type != model_artifact.get("target_assumption"):
        return None
    if property_type not in model_artifact.get("property_types", []):
        return None
    forecast = model_artifact.get("model_metrics", {}).get("forecast")
    if not isinstance(forecast, dict) or forecast.get("model", {}).get("estimate") is None:
        return None
    if forecast.get("candidate_only") is not True or forecast.get("analyst_approval_required") is not True:
        return None
    return {**forecast, "model_quality": {
        "stability": model_artifact.get("model_metrics", {}).get("stability", {}),
        "python_reference_status": model_artifact.get("model_metrics", {}).get("python_reference_status", "passed"),
        "r_cross_check_status": model_artifact.get("model_metrics", {}).get("r_cross_check_status", "not_available"),
    }}


def recommend_from_model(*, historical: dict, recent: Decimal, forecast: dict,
                         property_type: str = "multifamily", assumption_type: str = "market_rent_growth",
                         policy: RecommendationPolicy | None = None) -> dict:
    selected, quality_score, quality_evidence = select_recommendation_policy(
        property_type=property_type, assumption_type=assumption_type, forecast=forecast)
    policy = policy or selected
    estimate = Decimal(str(forecast["model"]["estimate"]))
    median = Decimal(str(historical["median"])); q1 = Decimal(str(historical["q1"])); q3 = Decimal(str(historical["q3"]))
    base = policy.model_weight * estimate + policy.historical_weight * median + policy.recent_weight * recent
    forecast_range = forecast.get("range", {})
    forecast_low = Decimal(str(forecast_range.get("low", estimate)))
    forecast_high = Decimal(str(forecast_range.get("high", estimate)))
    validation = forecast.get("validation", {})
    error = Decimal(str(validation.get("walk_forward_mae") or "0"))
    downside = min(q1, forecast_low, base - max(error, policy.minimum_downside_buffer))
    upside = max(q3, forecast_high, base + error)
    return {
        "downside": format(downside, "f"), "base": format(base, "f"), "upside": format(upside, "f"),
        "model_validation_score": float(quality_score),
        "recommendation_policy_id": policy.policy_id,
        "recommendation_policy_version": policy.version,
        "model_quality_tier": policy.quality_tier,
        "model_quality_evidence": quality_evidence,
        "policy": {key: str(value) for key, value in asdict(policy).items()},
        "rationale": f"Policy {policy.policy_id} v{policy.version} selected the {policy.quality_tier} model-quality weights and deterministically blended the validated forecast, historical median, and most recent observation.",
    }
