from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re


@dataclass(frozen=True)
class OpportunityScorePolicy:
    policy_id: str = "multifamily-acquisition-opportunity"
    version: str = "1.0.0"
    property_type: str = "multifamily"
    outcome: str = "realized_total_return"
    minimum_observations: int = 200
    minimum_markets: int = 10
    minimum_periods: int = 12
    minimum_periods_per_market: int = 8
    require_time_holdout: bool = True
    require_geography_holdout: bool = True
    require_baseline_improvement: bool = True
    require_independent_python_check: bool = True

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


DEFAULT_POLICY = OpportunityScorePolicy()
REQUIRED_OUTCOME_FIELDS = {
    "observation_id", "property_id", "market_id", "period", "property_type",
    "forecast_origin", "feature_available_at", "outcome_realized_at", "outcome_released_at",
    "outcome", "outcome_value", "data_status", "analyst_verified", "rights_documented",
    "source_hash", "feature_hash",
}


def _sha(value: object) -> bool:
    text = str(value or "").lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def score_dataset_readiness(rows: list[dict], policy: OpportunityScorePolicy = DEFAULT_POLICY,
                            evaluation_date: date | None = None) -> dict:
    if not isinstance(rows, list):
        raise ValueError("opportunity outcome rows must be a list")
    blockers, eligible, rejected = [], [], {}

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    as_of = evaluation_date or date.today()
    identity_counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        if isinstance(row, dict):
            identity = (str(row.get("property_id") or ""), str(row.get("forecast_origin") or ""),
                        str(row.get("outcome") or ""))
            identity_counts[identity] = identity_counts.get(identity, 0) + 1
    for row in rows:
        if not isinstance(row, dict) or not REQUIRED_OUTCOME_FIELDS <= set(row):
            reject("schema_invalid")
            continue
        if any(not str(row.get(field) or "").strip() for field in ("observation_id", "property_id", "market_id", "period")):
            reject("identity_invalid")
            continue
        if not re.fullmatch(r"\d{4}-(?:Q[1-4]|\d{2})", str(row["period"])):
            reject("period_invalid")
            continue
        identity = (str(row["property_id"]), str(row["forecast_origin"]), str(row["outcome"]))
        if identity_counts.get(identity, 0) > 1:
            reject("duplicate_property_origin_outcome")
            continue
        if row["data_status"] != "real":
            reject("non_real_data")
            continue
        if row["analyst_verified"] is not True or row["rights_documented"] is not True:
            reject("governance_incomplete")
            continue
        if str(row["property_type"]).lower() != policy.property_type:
            reject("property_type_mismatch")
            continue
        if str(row["outcome"]) != policy.outcome:
            reject("outcome_mismatch")
            continue
        if not _sha(row["source_hash"]) or not _sha(row["feature_hash"]):
            reject("lineage_hash_invalid")
            continue
        try:
            origin = date.fromisoformat(str(row["forecast_origin"]))
            feature_available = date.fromisoformat(str(row["feature_available_at"]))
            realized = date.fromisoformat(str(row["outcome_realized_at"]))
            released = date.fromisoformat(str(row["outcome_released_at"]))
            value = float(row["outcome_value"])
        except (TypeError, ValueError):
            reject("date_or_value_invalid")
            continue
        if feature_available > origin:
            reject("future_feature_leakage")
            continue
        if realized <= origin or released < realized:
            reject("outcome_not_forward")
            continue
        if released > as_of:
            reject("outcome_not_released_as_of_evaluation")
            continue
        if not (-10 <= value <= 10):
            reject("outcome_value_extreme_review")
            continue
        eligible.append(row)

    markets = sorted({str(row["market_id"]) for row in eligible})
    periods = sorted({str(row["period"]) for row in eligible})
    depth = {market: len({str(row["period"]) for row in eligible if str(row["market_id"]) == market})
             for market in markets}
    deep_markets = [market for market, count in depth.items() if count >= policy.minimum_periods_per_market]
    if len(eligible) < policy.minimum_observations:
        blockers.append(f"eligible_observations:{len(eligible)}<{policy.minimum_observations}")
    if len(markets) < policy.minimum_markets:
        blockers.append(f"markets:{len(markets)}<{policy.minimum_markets}")
    if len(periods) < policy.minimum_periods:
        blockers.append(f"periods:{len(periods)}<{policy.minimum_periods}")
    if len(deep_markets) < policy.minimum_markets:
        blockers.append(f"markets_meeting_longitudinal_depth:{len(deep_markets)}<{policy.minimum_markets}")
    return {
        "policy": {**asdict(policy), "content_hash": policy.content_hash},
        "evaluatedAsOf": as_of.isoformat(),
        "rawObservations": len(rows),
        "eligibleObservations": len(eligible),
        "markets": len(markets),
        "periods": len(periods),
        "marketsMeetingLongitudinalDepth": len(deep_markets),
        "periodDepthByMarket": depth,
        "rejected": rejected,
        "readyForCandidateBacktest": not blockers,
        "blockers": blockers,
        "status": "READY_FOR_CANDIDATE_BACKTEST" if not blockers else "INSUFFICIENT_REALIZED_OUTCOME_DATA",
    }


def promotion_decision(readiness: dict, validation: dict | None,
                       policy: OpportunityScorePolicy = DEFAULT_POLICY) -> dict:
    reasons = list(readiness.get("blockers") or [])
    validation = validation or {}
    if not readiness.get("readyForCandidateBacktest"):
        reasons.append("candidate_backtest_not_ready")
    if validation.get("dataStatus") != "real":
        reasons.append("validation_data_not_real")
    if int(validation.get("oosPredictions") or 0) <= 0:
        reasons.append("no_out_of_sample_predictions")
    if policy.require_time_holdout and validation.get("timeHoldoutStatus") != "passed":
        reasons.append("time_holdout_not_passed")
    if policy.require_geography_holdout and validation.get("geographyHoldoutStatus") != "passed":
        reasons.append("geography_holdout_not_passed")
    if policy.require_baseline_improvement and not float(validation.get("baselineImprovement") or 0) > 0:
        reasons.append("best_baseline_not_beaten")
    if validation.get("stabilityStatus") != "passed":
        reasons.append("stability_not_passed")
    if policy.require_independent_python_check and validation.get("pythonCrossCheckStatus") != "passed":
        reasons.append("independent_python_check_not_passed")
    if validation.get("rCrossCheckStatus") not in {"passed", "not_available_policy_permitted"}:
        reasons.append("r_cross_check_not_passed_or_permitted")
    source_hashes = validation.get("sourceHashes")
    if (not _sha(validation.get("modelResultHash")) or not isinstance(source_hashes, list)
            or not source_hashes or not all(_sha(value) for value in source_hashes)):
        reasons.append("validation_lineage_incomplete")
    reasons = sorted(set(reasons))
    return {
        "policyId": policy.policy_id,
        "policyVersion": policy.version,
        "policyHash": policy.content_hash,
        "status": "VALIDATED_PRODUCTION" if not reasons else "NO_VALIDATED_OPPORTUNITY_SCORE",
        "scoreProduced": not reasons,
        "eligibleForControllingUnderwriting": False,
        "analystApprovalRequired": True,
        "reasons": reasons,
    }


def current_score_status() -> dict:
    readiness = score_dataset_readiness([])
    return promotion_decision(readiness, None)
