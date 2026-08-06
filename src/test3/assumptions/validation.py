from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt


def walk_forward_baselines(observations: list[dict], minimum_training_periods: int = 3) -> list[dict]:
    """Backtest persistence and historical-mean-change baselines without look-ahead."""
    grouped: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for row in observations:
        grouped[(row["metric"], row.get("property_type") or "all", row["geography_type"], row["geography_id"])].append((row["observation_date"], float(row["value"])))
    output = []
    for key, pairs in sorted(grouped.items()):
        pairs.sort(); actuals = [value for _, value in pairs]
        if len(actuals) <= minimum_training_periods:
            continue
        results = {"persistence": [], "mean_change": []}
        for index in range(minimum_training_periods, len(actuals)):
            training = actuals[:index]
            changes = [right - left for left, right in zip(training, training[1:])]
            predictions = {"persistence": training[-1], "mean_change": training[-1] + sum(changes) / len(changes)}
            for model, prediction in predictions.items():
                error = actuals[index] - prediction
                results[model].append((error, prediction, actuals[index]))
        for model, values in results.items():
            errors = [item[0] for item in values]
            direction_hits = [((prediction - actuals[index + minimum_training_periods - 1]) * (actual - actuals[index + minimum_training_periods - 1])) > 0 for index, (_, prediction, actual) in enumerate(values)]
            output.append({"metric": key[0], "propertyType": key[1], "geographyType": key[2], "geographyId": key[3], "baseline": model, "trainingMinimum": minimum_training_periods, "testCount": len(values), "testStartDate": pairs[minimum_training_periods][0], "testEndDate": pairs[-1][0], "mae": round(sum(abs(error) for error in errors) / len(errors), 10), "rmse": round(sqrt(sum(error * error for error in errors) / len(errors)), 10), "bias": round(sum(errors) / len(errors), 10), "directionalAccuracy": round(sum(direction_hits) / len(direction_hits), 6), "warning": "Walk-forward benchmark only; observed periods may be irregular and no production model is validated by this result."})
    return output


def market_regimes(observations: list[dict]) -> list[dict]:
    """Classify transparent rent/vacancy regimes and summarize observed transitions."""
    grouped: dict[tuple, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in observations:
        if row["metric"] in {"rent_growth_12m", "vacancy_rate"}:
            scope = (row.get("property_type") or "all", row["geography_type"], row["geography_id"])
            grouped[scope][row["observation_date"]][row["metric"]] = float(row["value"])
    output = []
    for scope, dated in sorted(grouped.items()):
        ordered = sorted(dated.items())
        regimes = []
        previous_vacancy = None
        for period, values in ordered:
            if "rent_growth_12m" not in values or "vacancy_rate" not in values:
                continue
            vacancy_change = None if previous_vacancy is None else values["vacancy_rate"] - previous_vacancy
            previous_vacancy = values["vacancy_rate"]
            if vacancy_change is None:
                regime = "initial"
            elif values["rent_growth_12m"] > 0 and vacancy_change <= 0:
                regime = "favorable"
            elif values["rent_growth_12m"] < 0 and vacancy_change > 0:
                regime = "adverse"
            else:
                regime = "mixed"
            regimes.append({"period": period, "regime": regime, "rentGrowth": values["rent_growth_12m"], "vacancyRate": values["vacancy_rate"], "vacancyChange": vacancy_change})
        if not regimes:
            continue
        transitions = Counter(f'{left["regime"]}->{right["regime"]}' for left, right in zip(regimes, regimes[1:]))
        output.append({"propertyType": scope[0], "geographyType": scope[1], "geographyId": scope[2], "periods": regimes, "regimeCounts": dict(sorted(Counter(item["regime"] for item in regimes).items())), "transitionCounts": dict(sorted(transitions.items())), "warning": "Transparent descriptive classification, not a hidden-state model or forecast."})
    return output
