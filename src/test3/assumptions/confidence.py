from __future__ import annotations


def score_confidence(*, sample_count: int, completeness: float, freshness: float, geography: float, property_match: float, source_quality: float, model_validation: float, agreement: float, out_of_domain: bool) -> dict:
    sample = min(1.0, sample_count / 24) if sample_count > 0 else 0.0
    components = {
        "sampleSize": round(sample, 4), "dataCompleteness": round(completeness, 4), "freshness": round(freshness, 4),
        "geographicMatch": round(geography, 4), "propertyTypeMatch": round(property_match, 4),
        "sourceQuality": round(source_quality, 4), "modelValidation": round(model_validation, 4), "modelBenchmarkAgreement": round(agreement, 4),
    }
    weights = {"sampleSize": .15, "dataCompleteness": .15, "freshness": .15, "geographicMatch": .15, "propertyTypeMatch": .15, "sourceQuality": .10, "modelValidation": .10, "modelBenchmarkAgreement": .05}
    total = sum(components[key] * weight for key, weight in weights.items())
    if out_of_domain:
        total = min(total, .49)
    label = "high" if total >= .8 and sample >= .75 and model_validation >= .7 else "moderate" if total >= .55 else "low" if sample_count else "unavailable"
    return {"label": label, "score": round(total, 4), "components": components}
