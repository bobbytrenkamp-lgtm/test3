from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RecommendationPolicy:
    model_weight: Decimal = Decimal("0.50")
    historical_weight: Decimal = Decimal("0.35")
    recent_weight: Decimal = Decimal("0.15")
    minimum_downside_buffer: Decimal = Decimal("0")


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
    return forecast


def recommend_from_model(*, historical: dict, recent: Decimal, forecast: dict,
                         policy: RecommendationPolicy = RecommendationPolicy()) -> dict:
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
    baseline = Decimal(str(validation.get("baseline_mae") or "0"))
    improvement = max(Decimal("0"), baseline - error)
    model_validation = min(Decimal("1"), improvement / baseline) if baseline > 0 else Decimal("0")
    return {
        "downside": format(downside, "f"), "base": format(base, "f"), "upside": format(upside, "f"),
        "model_validation_score": float(model_validation), "policy": {key: str(value) for key, value in asdict(policy).items()},
        "rationale": "The base is a governed blend of the validated forecast, historical median and most recent observation; downside/upside also reflect empirical out-of-sample error and historical dispersion.",
    }
