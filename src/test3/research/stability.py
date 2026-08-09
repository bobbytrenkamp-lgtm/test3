from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .datasets import PanelDataset, prepare_panel
from .linear import fit_ols
from .validation import prediction_metrics


DEFAULT_DIAGNOSTIC_WINDOWS = (("pre_2020", None, "2019-Q4"), ("2020_2022", "2020-Q1", "2022-Q4"),
                              ("post_2022", "2023-Q1", None))


def stability_diagnostics(panel: PanelDataset, *, entity_fixed_effects: bool,
                          covariance: str, predictions: list[dict] | None = None,
                          diagnostic_windows=DEFAULT_DIAGNOSTIC_WINDOWS) -> dict:
    periods = panel.periods
    if len(periods) < 6:
        return {"status": "insufficient_data", "severe_instability": True,
                "reason": "at least six periods are required for stability diagnostics"}
    starts = sorted({0, len(periods) // 4, len(periods) // 2})
    windows = []
    for start in starts:
        selected = [row for row in panel.rows if row[panel.time_column] >= periods[start]]
        try:
            subset = prepare_panel(selected, target=panel.target, features=panel.features,
                                   entity_column=panel.entity_column, time_column=panel.time_column,
                                   property_type_column=None)
            model = fit_ols(subset, entity_fixed_effects=entity_fixed_effects,
                            time_fixed_effects=False, covariance=covariance)
        except ValueError as exc:
            windows.append({"start": periods[start], "status": "failed", "reason": str(exc)})
            continue
        coefficients = {name: value for name, value in zip(model.design_names, model.coefficients, strict=True)
                        if name in panel.features}
        windows.append({"start": periods[start], "end": periods[-1], "status": "completed",
                        "sample_size": len(subset.rows), "coefficients": coefficients})
    sign_stability = {}
    for feature in panel.features:
        values = [item["coefficients"][feature] for item in windows if item.get("status") == "completed"]
        signs = {0 if value == 0 else 1 if value > 0 else -1 for value in values}
        sign_stability[feature] = {"windows": len(values), "sign_consistent": len(signs) <= 1,
                                   "minimum": min(values, default=None), "maximum": max(values, default=None)}
    prediction_rows = predictions or []
    by_market = defaultdict(list)
    for row in prediction_rows:
        by_market[row.get("entity")].append(row)
    market_performance = {market: prediction_metrics(rows) for market, rows in sorted(by_market.items()) if market}
    time_performance = {}
    for name, start, end in diagnostic_windows:
        rows = [row for row in prediction_rows if (start is None or row["period"] >= start) and
                (end is None or row["period"] <= end)]
        time_performance[name] = prediction_metrics(rows)
    unstable_features = sorted(name for name, result in sign_stability.items() if not result["sign_consistent"])
    feature_availability = {}
    for feature in panel.features:
        column = feature + "__available_at"
        feature_availability[feature] = mean(row.get(column) is not None for row in panel.rows)
    return {"status": "completed", "coefficient_windows": windows, "sign_stability": sign_stability,
            "unstable_features": unstable_features, "severe_instability": bool(unstable_features),
            "market_performance": market_performance, "time_performance": time_performance,
            "feature_availability_rate": feature_availability,
            "note": "Diagnostic windows describe stability; they are not permanent economic regimes."}
