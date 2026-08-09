from __future__ import annotations

from collections import defaultdict

from .datasets import prepare_panel
from .diagnostics import regression_diagnostics
from .validation import walk_forward_validate


def _shift(period: str, lag: int) -> str:
    if lag < 0:
        raise ValueError("lags must be non-negative")
    if len(period) == 4 and period.isdigit():
        return str(int(period) - lag)
    if len(period) == 7 and period[4:6] == "-Q" and period[6] in "1234":
        index = int(period[:4]) * 4 + int(period[6]) - 1 - lag
        return f"{index // 4:04d}-Q{index % 4 + 1}"
    raise ValueError("lag research supports governed annual or quarterly period labels")


def create_lagged_records(records, *, feature: str, lags: tuple[int, ...], entity_column: str = "market_id",
                          time_column: str = "period") -> tuple[list[dict], tuple[str, ...]]:
    if not lags or len(set(lags)) != len(lags) or any(lag < 0 for lag in lags):
        raise ValueError("lags must be a unique non-empty set of non-negative periods")
    lookup = defaultdict(dict)
    source_rows = [dict(row) for row in records]
    for row in source_rows:
        key = (str(row.get(entity_column) or ""), str(row.get(time_column) or ""))
        if key[1] in lookup[key[0]]:
            raise ValueError("duplicate entity-period in lag source")
        lookup[key[0]][key[1]] = row
    names = tuple(f"{feature}_lag_{lag}" for lag in lags)
    output = []
    for row in source_rows:
        entity, period = str(row[entity_column]), str(row[time_column])
        enriched = dict(row)
        for lag, name in zip(lags, names, strict=True):
            source = lookup[entity].get(_shift(period, lag))
            enriched[name] = None if source is None else source.get(feature)
            if source is not None and source.get(feature + "__available_at") is not None:
                enriched[name + "__available_at"] = source[feature + "__available_at"]
        output.append(enriched)
    return output, names


def evaluate_candidate_lags(records, *, target: str, feature: str, lags: tuple[int, ...],
                            minimum_training_periods: int = 4, entity_column: str = "market_id",
                            time_column: str = "period", required_property_type: str | None = None) -> list[dict]:
    lagged, names = create_lagged_records(records, feature=feature, lags=lags,
                                          entity_column=entity_column, time_column=time_column)
    output = []
    for lag, name in zip(lags, names, strict=True):
        panel = prepare_panel(lagged, target=target, features=(name,), entity_column=entity_column,
                              time_column=time_column, required_property_type=required_property_type)
        validation = walk_forward_validate(panel, minimum_training_periods=minimum_training_periods,
                                           entity_fixed_effects=True, covariance="cluster_entity")
        diagnostic = regression_diagnostics(panel)
        output.append({"feature": feature, "lag": lag, "lagged_feature": name,
                       "correlation": diagnostic["correlations"][name][target],
                       "sample_size": len(panel.rows), "walk_forward": validation["metrics"]["model"],
                       "best_baseline_mae": min(value["mae"] for key, value in validation["metrics"].items()
                                                if key != "model" and value["mae"] is not None),
                       "model_beats_best_baseline": validation["model_beats_best_baseline"]})
    return sorted(output, key=lambda item: (item["walk_forward"]["mae"] is None,
                                            item["walk_forward"]["mae"] or float("inf"), item["lag"]))
