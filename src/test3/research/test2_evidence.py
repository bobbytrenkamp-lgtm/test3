from __future__ import annotations

import hashlib
import json


REQUIRED_VALIDATION = ("walk_forward_mae", "best_baseline_mae", "market_holdout_mae")


def build_test2_assumption_evidence(forecast: dict, *, analyst_decision: dict | None = None) -> dict:
    """Create advisory evidence only for a governed production forecast."""
    if forecast.get("status") != "validated_production":
        raise ValueError("Test2 evidence requires a validated_production forecast")
    if not forecast.get("model_id") or not forecast.get("model_version"):
        raise ValueError("model identity and version are required")
    validation = forecast.get("validation") or {}
    missing = [field for field in REQUIRED_VALIDATION if validation.get(field) is None]
    if missing:
        raise ValueError(f"forecast validation is incomplete: {missing}")
    hashes = forecast.get("lineage_hashes") or {}
    required_hashes = ("target_dataset_hash", "feature_panel_hash", "market_definition_hash", "model_result_hash")
    if any(not hashes.get(field) for field in required_hashes):
        raise ValueError("complete immutable forecast lineage is required")
    if analyst_decision is not None and analyst_decision.get("decision") not in {"approve", "modify", "reject"}:
        raise ValueError("analyst decision must be approve, modify, or reject")
    body = {
        "schema_version": "test3-test2-assumption-evidence/1.0.0",
        "advisory_only": True,
        "test2_assumption_overwritten": False,
        "market": forecast["market"], "property_type": forecast["property_type"],
        "assumption_type": forecast["target"], "forecast_period": forecast["forecast_period"],
        "forecast_value": forecast["estimate"], "forecast_range": forecast.get("forecast_range"),
        "forecast_range_method": forecast.get("forecast_range_method"),
        "model_id": forecast["model_id"], "model_version": forecast["model_version"],
        "data_as_of": forecast.get("data_as_of"), "validation": validation,
        "lineage_hashes": hashes, "limitations": list(forecast.get("limitations") or []),
        "analyst_decision": analyst_decision,
        "application_status": "analyst_review_required" if analyst_decision is None else "analyst_decision_recorded",
    }
    body["evidence_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body
