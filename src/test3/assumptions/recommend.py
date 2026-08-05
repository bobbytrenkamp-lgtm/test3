from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from .benchmarks import describe
from .catalog import BY_NAME
from .confidence import score_confidence
from .features import freshness_score, select_fallback


def recommend(assumption_type: str, deal: dict, observations: list[dict], context: dict) -> dict:
    spec = BY_NAME.get(assumption_type)
    if not spec:
        raise ValueError("Unsupported assumption type")
    candidates = [row for row in observations if row.get("metric") == spec.metric]
    fallback, matched, geography, property_match = select_fallback(candidates, deal, context)
    if not matched:
        return {"assumptionType": assumption_type, "status": "unavailable", "low": None, "base": None, "high": None, "modelEstimate": None, "benchmarkEstimate": None, "confidence": "unavailable", "confidenceComponents": {}, "dataCompleteness": 0, "freshnessScore": 0, "geographicMatchScore": 0, "propertyMatchScore": 0, "outOfDomain": True, "fallbackLevel": "unavailable", "method": "unavailable", "supportingEvidence": [], "limitations": [f"No matching {spec.metric} observations are available."], "rationale": "A recommendation cannot be produced without observed evidence.", "sampleCount": 0, "candidateOnly": True}
    ordered = sorted(matched, key=lambda row: row["observation_date"])
    stats = describe([row["value"] for row in ordered])
    low, base, high = Decimal(stats["q1"]), Decimal(stats["median"]), Decimal(stats["q3"])
    latest = ordered[-1]["observation_date"]
    completeness = min(1.0, len({row["observation_date"] for row in ordered}) / spec.preferred_history)
    fresh = freshness_score(latest)
    out_of_domain = fallback in {"state_property_type", "national_property_type"}
    confidence = score_confidence(sample_count=len(ordered), completeness=completeness, freshness=fresh, geography=geography, property_match=property_match, source_quality=.75, model_validation=0, agreement=1, out_of_domain=out_of_domain)
    inputs = {"assumptionType": assumption_type, "metric": spec.metric, "dealPropertyType": deal.get("property_type"), "context": context, "fallbackLevel": fallback, "observationIds": [row["id"] for row in ordered], "statistics": stats}
    return {"assumptionType": assumption_type, "status": "candidate", "low": format(low, "f"), "base": format(base, "f"), "high": format(high, "f"), "modelEstimate": None, "benchmarkEstimate": stats["median"], "historicalMedian": stats["median"], "historicalIqr": {"low": stats["q1"], "high": stats["q3"]}, "mostRecentObserved": ordered[-1]["value"], "sampleCount": len(ordered), "dataWindow": {"start": ordered[0]["observation_date"], "end": latest}, "confidence": confidence["label"], "confidenceScore": confidence["score"], "confidenceComponents": confidence["components"], "dataCompleteness": completeness, "freshnessScore": fresh, "geographicMatchScore": geography, "propertyMatchScore": property_match, "outOfDomain": out_of_domain, "fallbackLevel": fallback, "method": "descriptive_iqr", "supportingEvidence": [row["id"] for row in ordered], "inputFeatures": inputs, "inputSha256": hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "limitations": (["A broader-geography fallback is disclosed and caps confidence."] if out_of_domain else []), "rationale": f"The candidate range uses {len(ordered)} observed {spec.metric} records at fallback level {fallback}; low/base/high are the first quartile, median, and third quartile.", "candidateOnly": True}
