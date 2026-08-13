from __future__ import annotations

from dataclasses import dataclass

from .datasets import PanelDataset
from .specifications import ModelSpecification


MODEL_MODES = frozenset({"ad_hoc_research", "governed_candidate", "validated_production"})


@dataclass(frozen=True)
class ValidationPolicy:
    minimum_sample_size: int = 40
    minimum_markets: int = 3
    minimum_periods: int = 6
    require_baseline_improvement: bool = True
    require_market_holdout: bool = True
    require_python_reference: bool = True
    allow_r_unavailable: bool = True

    @classmethod
    def from_model_specification(cls, specification: ModelSpecification) -> "ValidationPolicy":
        """Build promotion gates from the authoritative governed model specification."""
        return cls(
            minimum_sample_size=specification.minimum_sample,
            minimum_markets=specification.minimum_markets,
            minimum_periods=specification.minimum_periods,
        )


def assess_model(panel: PanelDataset, walk_forward: dict, market_holdout: dict | None,
                 *, source_manifest_hashes: tuple[str, ...] = (), data_status: str = "research",
                 policy: ValidationPolicy = ValidationPolicy(), python_reference: dict | None = None,
                 r_reference: dict | None = None, stability: dict | None = None,
                 target_dataset_hashes: tuple[str, ...] = (), feature_table_hash: str | None = None,
                 model_mode: str = "ad_hoc_research",
                 model_specification: ModelSpecification | None = None) -> dict:
    if data_status not in {"research", "fictional_synthetic", "real"}:
        raise ValueError("unsupported model data status")
    if model_mode not in MODEL_MODES:
        raise ValueError("unsupported model mode")
    failures = []
    if model_specification is not None:
        governed_policy = ValidationPolicy.from_model_specification(model_specification)
        if policy.minimum_sample_size < governed_policy.minimum_sample_size or policy.minimum_markets < governed_policy.minimum_markets or policy.minimum_periods < governed_policy.minimum_periods:
            failures.append("validation policy is weaker than the governed model specification")
    if model_mode in {"governed_candidate", "validated_production"} and model_specification is None:
        failures.append("governed model mode requires a registered model specification")
    if model_mode == "validated_production" and data_status != "real":
        failures.append("production validation requires real data")
    if (model_mode == "validated_production" and model_specification is not None
            and model_specification.purpose != "forecast"):
        failures.append("inference-only specifications cannot become controlling forward forecasts")
    if len(panel.rows) < policy.minimum_sample_size:
        failures.append(f"sample size {len(panel.rows)} is below {policy.minimum_sample_size}")
    if len(panel.entities) < policy.minimum_markets:
        failures.append(f"market count {len(panel.entities)} is below {policy.minimum_markets}")
    if len(panel.periods) < policy.minimum_periods:
        failures.append(f"period count {len(panel.periods)} is below {policy.minimum_periods}")
    longitudinal_markets = sum(count >= policy.minimum_periods for count in panel.periods_by_entity.values())
    if longitudinal_markets < policy.minimum_markets:
        failures.append(f"markets meeting {policy.minimum_periods}-period depth {longitudinal_markets} "
                        f"is below {policy.minimum_markets}")
    if walk_forward.get("look_ahead") is not False:
        failures.append("walk-forward result does not affirm absence of look-ahead")
    if walk_forward.get("metrics", {}).get("model", {}).get("sample_size", 0) == 0:
        failures.append("walk-forward validation has no predictions")
    if policy.require_baseline_improvement and not walk_forward.get("model_beats_best_baseline"):
        failures.append("model did not beat the best governed baseline")
    if policy.require_market_holdout and (not market_holdout or market_holdout.get("metrics", {}).get("sample_size", 0) == 0):
        failures.append("market-holdout validation is missing")
    if data_status == "real" and not source_manifest_hashes:
        failures.append("real-data model has no source manifest hashes")
    if data_status == "real" and not target_dataset_hashes:
        failures.append("real-data model has no target dataset hashes")
    if data_status == "real" and not feature_table_hash:
        failures.append("real-data model has no immutable feature-table hash")
    if data_status == "real" and policy.require_python_reference and (not python_reference or python_reference.get("status") != "passed"):
        failures.append("independent Python reference validation did not pass")
    if r_reference and r_reference.get("status") == "not_available" and not policy.allow_r_unavailable:
        failures.append("R cross-check is required but unavailable")
    elif r_reference and r_reference.get("status") not in {"passed", "not_available"}:
        failures.append("R cross-check failed")
    if stability and stability.get("severe_instability"):
        failures.append("severe coefficient instability was detected")
    if failures:
        status = "rejected"
    elif model_mode == "validated_production" and data_status == "real":
        status = "validated"
    elif model_mode == "governed_candidate":
        status = "candidate"
    else:
        status = "research"
    return {
        "status": status, "eligible_for_controlling_forecast": status == "validated", "failures": failures,
        "policy": policy.__dict__, "data_status": data_status, "model_mode": model_mode,
        "model_specification": ({"name": model_specification.name, "version": model_specification.version}
                                if model_specification else None),
        "python_reference_status": (python_reference or {}).get("status", "not_run"),
        "r_cross_check_status": (r_reference or {}).get("status", "not_run"),
        "note": "Synthetic models can test machinery but can never become controlling forecasts.",
    }
