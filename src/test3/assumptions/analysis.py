from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from math import sqrt

from .benchmarks import describe


def benchmark_matrix(observations: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in observations:
        groups[(row["metric"], row.get("property_type") or "all", row["geography_type"], row["geography_id"])].append(row)
    result = []
    for (metric, property_type, geography_type, geography_id), rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda item: item["observation_date"])
        stats = describe([item["value"] for item in ordered])
        first, last = Decimal(ordered[0]["value"]), Decimal(ordered[-1]["value"])
        periods = max(1, len({item["observation_date"] for item in ordered}) - 1)
        result.append({"metric": metric, "propertyType": property_type, "geographyType": geography_type, "geographyId": geography_id, "count": len(ordered), "startDate": ordered[0]["observation_date"], "endDate": ordered[-1]["observation_date"], "minimum": stats["minimum"], "q1": stats["q1"], "median": stats["median"], "q3": stats["q3"], "maximum": stats["maximum"], "meanChangePerObservedPeriod": format((last - first) / periods, "f"), "latest": ordered[-1]["value"]})
    return result


def correlation_matrix(observations: list[dict]) -> list[dict]:
    # Pairwise Pearson correlation on exact geography/property/date matches only.
    keyed: dict[tuple, dict[str, Decimal]] = defaultdict(dict)
    for row in observations:
        key = (row["observation_date"], row["geography_type"], row["geography_id"], row.get("property_type"))
        keyed[key][row["metric"]] = Decimal(row["value"])
    metrics = sorted({row["metric"] for row in observations})
    output = []
    for index, left in enumerate(metrics):
        for right in metrics[index + 1:]:
            pairs = [(float(values[left]), float(values[right])) for values in keyed.values() if left in values and right in values]
            if len(pairs) < 3:
                continue
            xs, ys = zip(*pairs)
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            numerator = sum((x - mx) * (y - my) for x, y in pairs)
            dx = sum((x - mx) ** 2 for x in xs) ** .5
            dy = sum((y - my) ** 2 for y in ys) ** .5
            correlation = numerator / (dx * dy) if dx and dy else 0.0
            output.append({"leftMetric": left, "rightMetric": right, "pairCount": len(pairs), "correlation": round(correlation, 6), "warning": "Descriptive association only; not causal."})
    return output


def _series(observations: list[dict]) -> dict[tuple, list[tuple[str, float]]]:
    grouped: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for row in observations:
        key = (row["metric"], row.get("property_type") or "all", row["geography_type"], row["geography_id"])
        grouped[key].append((row["observation_date"], float(row["value"])))
    return {key: sorted(values) for key, values in grouped.items()}


def time_series_diagnostics(observations: list[dict]) -> list[dict]:
    """Deterministic diagnostics; no forecasting claims and no third-party runtime."""
    output = []
    for (metric, property_type, geography_type, geography_id), values in sorted(_series(observations).items()):
        xs = [value for _, value in values]
        changes = [right - left for left, right in zip(xs, xs[1:])]
        mean_change = sum(changes) / len(changes) if changes else 0.0
        volatility = sqrt(sum((item - mean_change) ** 2 for item in changes) / max(1, len(changes) - 1)) if len(changes) > 1 else 0.0
        x_mean = (len(xs) - 1) / 2
        denominator = sum((index - x_mean) ** 2 for index in range(len(xs)))
        slope = sum((index - x_mean) * (value - sum(xs) / len(xs)) for index, value in enumerate(xs)) / denominator if denominator else 0.0
        peak, drawdown = xs[0], 0.0
        for value in xs:
            peak = max(peak, value)
            if peak:
                drawdown = min(drawdown, (value - peak) / abs(peak))
        latest_z = (xs[-1] - sum(xs) / len(xs)) / (sqrt(sum((value - sum(xs) / len(xs)) ** 2 for value in xs) / (len(xs) - 1)) or 1) if len(xs) > 1 else 0.0
        output.append({"metric": metric, "propertyType": property_type, "geographyType": geography_type, "geographyId": geography_id, "periodCount": len(xs), "startDate": values[0][0], "endDate": values[-1][0], "latest": round(xs[-1], 8), "linearTrendPerObservedPeriod": round(slope, 8), "meanChangePerObservedPeriod": round(mean_change, 8), "changeVolatility": round(volatility, 8), "maximumDrawdown": round(drawdown, 8), "latestZScore": round(latest_z, 6), "latestIsOutlier": abs(latest_z) >= 3, "warning": "Descriptive diagnostics only; observed periods may not be equally spaced."})
    return output


def stress_scenarios(observations: list[dict]) -> list[dict]:
    """Empirical downside/base/upside bands from observed changes."""
    output = []
    for key, values in sorted(_series(observations).items()):
        if len(values) < 3:
            continue
        changes = sorted(right - left for (_, left), (_, right) in zip(values, values[1:]))
        def percentile(fraction: float) -> float:
            position = fraction * (len(changes) - 1)
            lower = int(position)
            upper = min(lower + 1, len(changes) - 1)
            weight = position - lower
            return changes[lower] * (1 - weight) + changes[upper] * weight
        metric, property_type, geography_type, geography_id = key
        output.append({"metric": metric, "propertyType": property_type, "geographyType": geography_type, "geographyId": geography_id, "sampleCount": len(changes), "downsideP10Change": round(percentile(.1), 8), "baseP50Change": round(percentile(.5), 8), "upsideP90Change": round(percentile(.9), 8), "historicalWorstChange": round(changes[0], 8), "historicalBestChange": round(changes[-1], 8), "warning": "Historical empirical scenario, not a forecast or probability statement."})
    return output


def lead_lag_matrix(observations: list[dict], maximum_lag: int = 4) -> list[dict]:
    """Find strongest descriptive correlation at small observed-period lags."""
    keyed: dict[tuple, dict[str, float]] = defaultdict(dict)
    for row in observations:
        scope = (row.get("property_type") or "all", row["geography_type"], row["geography_id"])
        keyed[(scope, row["observation_date"])][row["metric"]] = float(row["value"])
    scopes = sorted({key[0] for key in keyed})
    output = []
    for scope in scopes:
        dated = [(date, values) for (item_scope, date), values in keyed.items() if item_scope == scope]
        dated.sort()
        metrics = sorted({metric for _, values in dated for metric in values})
        for index, leading in enumerate(metrics):
            for lagging in metrics[index + 1:]:
                candidates = []
                for lag in range(-maximum_lag, maximum_lag + 1):
                    pairs = []
                    for position, (_, values) in enumerate(dated):
                        other = position + lag
                        if leading in values and 0 <= other < len(dated) and lagging in dated[other][1]:
                            pairs.append((values[leading], dated[other][1][lagging]))
                    if len(pairs) < 4:
                        continue
                    xs, ys = zip(*pairs); mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
                    numerator = sum((x - mx) * (y - my) for x, y in pairs)
                    denominator = sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
                    candidates.append((abs(numerator / denominator) if denominator else 0, lag, numerator / denominator if denominator else 0, len(pairs)))
                if candidates:
                    _, lag, correlation, count = max(candidates)
                    output.append({"leadingMetric": leading, "laggingMetric": lagging, "strongestLagObservedPeriods": lag, "correlation": round(correlation, 6), "pairCount": count, "propertyType": scope[0], "geographyType": scope[1], "geographyId": scope[2], "warning": "Exploratory lead-lag association only; not causal and not a forecast."})
    return output
