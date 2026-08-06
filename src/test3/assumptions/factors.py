from __future__ import annotations

from collections import defaultdict
from math import sqrt


def derived_change_factors(observations: list[dict], annual_lags: tuple[int, ...] = (4, 12)) -> list[dict]:
    """Create immutable-in-memory change factors without pretending to know source frequency."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in observations:
        grouped[(row["metric"], row.get("property_type") or "all", row["geography_type"], row["geography_id"])].append(row)
    output = []
    for key, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: item["observation_date"])
        values = [float(item["value"]) for item in rows]
        for index, row in enumerate(rows):
            if index:
                output.append(_factor(key, row["observation_date"], "period_change", values[index] - values[index - 1], index + 1))
                if values[index - 1]:
                    output.append(_factor(key, row["observation_date"], "period_percent_change", values[index] / values[index - 1] - 1, index + 1))
            for lag in annual_lags:
                if index >= lag and values[index - lag]:
                    output.append(_factor(key, row["observation_date"], f"change_{lag}_observed_periods", values[index] / values[index - lag] - 1, index + 1))
    return output


def _factor(key: tuple, period: str, factor: str, value: float, sample_count: int) -> dict:
    return {"sourceMetric": key[0], "propertyType": key[1], "geographyType": key[2], "geographyId": key[3], "period": period, "factor": factor, "value": round(value, 10), "sampleCountToDate": sample_count, "warning": "Observed-period transform; frequency must be verified from source metadata."}


def market_factor_scorecards(observations: list[dict]) -> list[dict]:
    """Rank like-for-like metric/property/geography-type series using unitless statistics."""
    grouped: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for row in observations:
        grouped[(row["metric"], row.get("property_type") or "all", row["geography_type"], row["geography_id"])].append((row["observation_date"], float(row["value"])))
    raw = []
    for key, pairs in sorted(grouped.items()):
        pairs.sort(); values = [value for _, value in pairs]
        if len(values) < 3:
            continue
        changes = [right - left for left, right in zip(values, values[1:])]
        mean = sum(changes) / len(changes)
        volatility = sqrt(sum((change - mean) ** 2 for change in changes) / max(1, len(changes) - 1))
        downside = sqrt(sum(min(0.0, change) ** 2 for change in changes) / len(changes))
        raw.append({"metric": key[0], "propertyType": key[1], "geographyType": key[2], "geographyId": key[3], "periodCount": len(values), "endDate": pairs[-1][0], "latest": values[-1], "momentum": values[-1] - values[0], "meanChange": mean, "volatility": volatility, "downsideDeviation": downside})
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for item in raw:
        buckets[(item["metric"], item["propertyType"], item["geographyType"])].append(item)
    output = []
    for items in buckets.values():
        for field in ("latest", "momentum", "meanChange", "volatility", "downsideDeviation"):
            ordered = sorted(items, key=lambda item: (item[field], item["geographyId"]))
            for rank, item in enumerate(ordered):
                item[field + "Percentile"] = round(rank / max(1, len(ordered) - 1), 6)
        for item in items:
            output.append({**item, "latest": round(item["latest"], 10), "momentum": round(item["momentum"], 10), "meanChange": round(item["meanChange"], 10), "volatility": round(item["volatility"], 10), "downsideDeviation": round(item["downsideDeviation"], 10), "peerCount": len(items), "warning": "Percentiles compare only identical metric, property type and geography level; higher is not always better."})
    return sorted(output, key=lambda item: (item["metric"], item["propertyType"], item["geographyType"], item["geographyId"]))
