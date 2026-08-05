from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

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
