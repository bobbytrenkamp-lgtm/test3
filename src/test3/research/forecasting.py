from __future__ import annotations

from math import floor


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("forecast range requires out-of-sample errors")
    position = (len(ordered) - 1) * probability
    lower, upper = floor(position), min(len(ordered) - 1, floor(position) + 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def create_forecast(*, model_result: dict, feature_row: dict, market: str, period: str,
                    property_type: str, target: str, data_as_of: str) -> dict:
    governance = model_result.get("governance", {})
    if governance.get("status") != "validated" or not governance.get("eligible_for_controlling_forecast"):
        raise ValueError("a formal forecast requires a validated real-data model")
    model = model_result["model"]
    contributions = []
    for name, coefficient in model["coefficients"].items():
        if name == "intercept":
            value, label = 1.0, "intercept"
        elif name.startswith("entity["):
            value, label = (1.0 if name == f"entity[{market}]" else 0.0), name
        elif name.startswith("time["):
            value, label = (1.0 if name == f"time[{period}]" else 0.0), name
        else:
            if feature_row.get(name) is None:
                raise ValueError(f"forecast feature is missing: {name}")
            value, label = float(feature_row[name]), name
        contributions.append({"feature": label, "coefficient": coefficient, "value": value,
                              "contribution": coefficient * value})
    estimate = sum(item["contribution"] for item in contributions)
    predictions = model_result.get("walk_forward", {}).get("predictions", [])
    errors = [float(row["actual"]) - float(row["prediction"]) for row in predictions]
    low_error, high_error = _quantile(errors, .25), _quantile(errors, .75)
    walk_metrics = model_result["walk_forward"]["metrics"]
    baseline_mae = min(value["mae"] for name, value in walk_metrics.items()
                       if name != "model" and value.get("mae") is not None)
    return {
        "schema_version": "test3-model-forecast/1.0.0", "target": target,
        "property_type": property_type, "market": market, "period": period,
        "model": {"model_id": model_result.get("model_id"), "version": model_result.get("model_version"),
                  "estimate": estimate},
        "range": {"low": estimate + low_error, "high": estimate + high_error,
                  "method": "empirical_walk_forward_residual_p25_p75"},
        "validation": {"walk_forward_mae": walk_metrics["model"]["mae"], "baseline_mae": baseline_mae,
                       "market_holdout_mae": model_result["market_holdout"]["metrics"]["mae"]},
        "drivers": sorted(contributions, key=lambda item: abs(item["contribution"]), reverse=True),
        "limitations": list(model_result.get("limitations", [])), "data_as_of": data_as_of,
        "candidate_only": True, "analyst_approval_required": True,
    }
