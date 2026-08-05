from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from .benchmarks import describe
from .confidence import score_confidence
from .features import freshness_score, select_fallback

FICTIONAL_WARNING = "FICTIONAL SYNTHETIC MODEL — NOT FOR REAL UNDERWRITING"


def recommend_market_rent_growth(deal: dict, observations: list[dict], context: dict, model_artifact: dict | None = None) -> dict:
    growth = [row for row in observations if row.get("metric") == "rent_growth_12m"]
    fallback, matched, geography, property_match = select_fallback(growth, deal, context)
    if not matched:
        return {"assumptionType":"market_rent_growth", "status":"unavailable", "low":None, "base":None, "high":None, "modelEstimate":None, "confidence":"unavailable", "confidenceComponents":{}, "fallbackLevel":"unavailable", "supportingEvidence":[], "limitations":["No matching market-rent-growth observations are available."], "rationale":"A recommendation cannot be produced without observed rent-growth evidence.", "candidateOnly":True}
    ordered = sorted(matched, key=lambda row: row["observation_date"])
    stats = describe([row["value"] for row in ordered])
    model_estimate, model_validation, limitations = None, 0.0, []
    if model_artifact:
        if model_artifact.get("data_status") == "fictional_synthetic":
            limitations.append(f"{FICTIONAL_WARNING}. Statistical estimate excluded.")
        elif model_artifact.get("validation_state") == "validated":
            prediction = model_artifact.get("model_metrics", {}).get("reference_prediction")
            if prediction is not None:
                model_estimate = str(prediction)
                model_validation = float(model_artifact.get("model_metrics", {}).get("validation_score", 0))
    median, q1, q3 = Decimal(stats["median"]), Decimal(stats["q1"]), Decimal(stats["q3"])
    base = (median + Decimal(model_estimate)) / 2 if model_estimate is not None else median
    low, high = min(q1, base), max(q3, base)
    latest = ordered[-1]["observation_date"]
    freshness = freshness_score(latest)
    completeness = min(1.0, len({row["observation_date"] for row in ordered}) / 12)
    agreement = 1.0 if model_estimate is None else max(0.0, 1.0 - float(abs(Decimal(model_estimate) - median)) / .05)
    out_of_domain = fallback in {"state_property_type", "national_property_type"}
    confidence = score_confidence(sample_count=len(ordered), completeness=completeness, freshness=freshness, geography=geography, property_match=property_match, source_quality=.75, model_validation=model_validation, agreement=agreement, out_of_domain=out_of_domain)
    inputs = {"dealPropertyType":deal.get("property_type"), "context":context, "fallbackLevel":fallback, "observationIds":[row["id"] for row in ordered], "historicalStatistics":stats, "modelArtifactId":model_artifact.get("id") if model_artifact else None}
    return {
        "assumptionType":"market_rent_growth", "status":"candidate", "low":format(low,"f"), "base":format(base,"f"), "high":format(high,"f"),
        "modelEstimate":model_estimate, "benchmarkEstimate":stats["median"], "historicalMedian":stats["median"], "historicalIqr":{"low":stats["q1"],"high":stats["q3"]},
        "mostRecentObservedGrowth":ordered[-1]["value"], "sampleCount":len(ordered), "dataWindow":{"start":ordered[0]["observation_date"],"end":latest},
        "confidence":confidence["label"], "confidenceScore":confidence["score"], "confidenceComponents":confidence["components"],
        "dataCompleteness":completeness, "freshnessScore":freshness, "geographicMatchScore":geography, "propertyMatchScore":property_match,
        "outOfDomain":out_of_domain, "fallbackLevel":fallback, "method":"descriptive_iqr" + ("_plus_validated_model" if model_estimate else ""),
        "supportingEvidence":[row["id"] for row in ordered], "inputFeatures":inputs, "inputSha256":hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "limitations":limitations + (["A broader-geography fallback is disclosed and caps confidence."] if out_of_domain else []),
        "rationale":f"The candidate range uses {len(ordered)} observed rent-growth records at fallback level {fallback}; the base is the historical median" + (" blended equally with the validated model estimate." if model_estimate else "."),
        "candidateOnly":True,
    }
