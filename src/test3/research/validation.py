from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import mean, median

from .datasets import PanelDataset, availability_date, period_bounds, prepare_panel
from .linear import fit_ols


def prediction_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"sample_size": 0, "mae": None, "rmse": None, "bias": None, "directional_accuracy": None}
    errors = [row["actual"] - row["prediction"] for row in rows]
    directions = [row for row in rows if row.get("prior_actual") is not None]
    hits = [((row["prediction"] - row["prior_actual"]) * (row["actual"] - row["prior_actual"])) > 0 for row in directions]
    return {"sample_size": len(rows), "mae": mean(abs(item) for item in errors),
            "rmse": sqrt(mean(item * item for item in errors)), "bias": mean(errors),
            "directional_accuracy": mean(hits) if hits else None}


def walk_forward_validate(panel: PanelDataset, *, minimum_training_periods: int = 4,
                          entity_fixed_effects: bool = True, time_fixed_effects: bool = False,
                          covariance: str = "cluster_entity") -> dict:
    periods = panel.periods
    if len(periods) <= minimum_training_periods:
        raise ValueError("insufficient periods for walk-forward validation")
    predictions = {name: [] for name in ("model", "last_observation", "entity_mean", "historical_median",
                                         "recent_3_year_mean", "peer_market_median", "simple_autoregressive")}
    excluded_unreleased_targets = 0
    for test_period in periods[minimum_training_periods:]:
        forecast_origin = period_bounds(test_period)[0]
        historical_rows = [row for row in panel.rows if row[panel.time_column] < test_period]
        availability_column = panel.target + "__available_at"
        training_rows = [row for row in historical_rows if row.get(availability_column) is None or
                         availability_date(row[availability_column]) < forecast_origin]
        excluded_unreleased_targets += len(historical_rows) - len(training_rows)
        test_rows = [row for row in panel.rows if row[panel.time_column] == test_period]
        training = prepare_panel(training_rows, target=panel.target, features=panel.features,
                                 entity_column=panel.entity_column, time_column=panel.time_column,
                                 property_type_column=None)
        model = fit_ols(training, entity_fixed_effects=entity_fixed_effects,
                        time_fixed_effects=time_fixed_effects, covariance=covariance)
        entity_history = defaultdict(list)
        for row in training.rows:
            entity_history[row[panel.entity_column]].append(row[panel.target])
        all_training = [row[panel.target] for row in training.rows]
        latest_by_peer = {entity: values[-1] for entity, values in entity_history.items() if values}
        recent_window = 12 if "-Q" in test_period else 3
        ar_pairs = [(values[index - 1], values[index]) for values in entity_history.values() for index in range(1, len(values))]
        if len(ar_pairs) >= 3:
            x_mean = mean(left for left, _ in ar_pairs); y_mean = mean(right for _, right in ar_pairs)
            denominator = sum((left - x_mean) ** 2 for left, _ in ar_pairs)
            ar_beta = sum((left - x_mean) * (right - y_mean) for left, right in ar_pairs) / denominator if denominator else 0.0
            ar_intercept = y_mean - ar_beta * x_mean
        else:
            ar_beta, ar_intercept = 1.0, 0.0
        model_values = model.predict(test_rows)
        for row, model_value in zip(test_rows, model_values, strict=True):
            history = entity_history.get(row[panel.entity_column])
            if not history:
                continue
            common = {"actual": row[panel.target], "entity": row[panel.entity_column], "period": test_period,
                      "prior_actual": history[-1]}
            peer_values = [value for entity, value in latest_by_peer.items() if entity != row[panel.entity_column]]
            for name, value in (("model", model_value), ("last_observation", history[-1]),
                                ("entity_mean", mean(history)), ("historical_median", median(all_training)),
                                ("recent_3_year_mean", mean(history[-recent_window:])),
                                ("peer_market_median", median(peer_values) if peer_values else median(all_training)),
                                ("simple_autoregressive", ar_intercept + ar_beta * history[-1])):
                predictions[name].append({**common, "prediction": value})
    metrics = {name: prediction_metrics(rows) for name, rows in predictions.items()}
    baseline_mae = min(value["mae"] for name, value in metrics.items() if name != "model" and value["mae"] is not None)
    model_mae = metrics["model"]["mae"]
    return {"method": "expanding_window", "minimum_training_periods": minimum_training_periods,
            "test_start": periods[minimum_training_periods], "test_end": periods[-1], "metrics": metrics,
            "model_beats_best_baseline": model_mae is not None and model_mae < baseline_mae,
            "mae_improvement": None if model_mae is None else baseline_mae - model_mae,
            "predictions": predictions["model"], "look_ahead": False,
            "excluded_unreleased_targets": excluded_unreleased_targets,
            "target_availability_enforced": True,
            "warning": "Predictive validation only; it does not establish causality or guarantee future performance."}


def market_holdout_validate(panel: PanelDataset, *, covariance: str = "hc1") -> dict:
    if len(panel.entities) < 3:
        raise ValueError("market holdout validation requires at least three entities")
    predictions = []
    for entity in panel.entities:
        training_rows = [row for row in panel.rows if row[panel.entity_column] != entity]
        held_out = [row for row in panel.rows if row[panel.entity_column] == entity]
        training = prepare_panel(training_rows, target=panel.target, features=panel.features,
                                 entity_column=panel.entity_column, time_column=panel.time_column,
                                 property_type_column=None)
        model = fit_ols(training, covariance=covariance)
        estimates = model.predict(held_out)
        prior = None
        for row, estimate in zip(held_out, estimates, strict=True):
            predictions.append({"entity": entity, "period": row[panel.time_column], "actual": row[panel.target],
                                "prediction": estimate, "prior_actual": prior})
            prior = row[panel.target]
    return {"method": "leave_one_market_out", "metrics": prediction_metrics(predictions), "markets": list(panel.entities),
            "predictions": predictions, "entity_fixed_effects": False, "time_fixed_effects": False,
            "warning": "Geographic generalization test; coefficients remain associational."}
