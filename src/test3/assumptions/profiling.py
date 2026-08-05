from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from .catalog import ASSUMPTION_CATALOG


def profile_observations(observations: list[dict]) -> dict:
    by_metric: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        by_metric[row["metric"]].append(row)
    metrics = []
    for metric, rows in sorted(by_metric.items()):
        dates = sorted({row["observation_date"] for row in rows})
        values = [Decimal(str(row["value"])) for row in rows]
        metrics.append({"metric": metric, "observationCount": len(rows), "periodCount": len(dates), "startDate": dates[0], "endDate": dates[-1], "geographyCount": len({(row["geography_type"], row["geography_id"]) for row in rows}), "propertyTypes": sorted({row["property_type"] for row in rows if row.get("property_type")}), "sourceCount": len({row["source_label"] for row in rows}), "minimum": format(min(values), "f"), "maximum": format(max(values), "f"), "stale": (date.today() - date.fromisoformat(dates[-1])).days > 730})
    available = {item["metric"] for item in metrics}
    coverage = [{"assumptionType": spec.name, "metric": spec.metric, "available": spec.metric in available, "observationCount": len(by_metric.get(spec.metric, []))} for spec in ASSUMPTION_CATALOG]
    return {"observationCount": len(observations), "metricCount": len(metrics), "geographyCount": len({(row["geography_type"], row["geography_id"]) for row in observations}), "propertyTypeCount": len({row["property_type"] for row in observations if row.get("property_type")}), "sourceCounts": dict(sorted(Counter(row["source_label"] for row in observations).items())), "metrics": metrics, "assumptionCoverage": coverage, "coverageRatio": sum(item["available"] for item in coverage) / len(coverage), "generatedLocally": True}
