from __future__ import annotations

import hashlib
import json

from .datasets import PanelDataset
from .diagnostics import regression_diagnostics
from .governance import ValidationPolicy, assess_model
from .linear import fit_ols
from .reference import cross_check_statsmodels
from .r_crosscheck import cross_check_r
from .specifications import ModelSpecification
from .stability import stability_diagnostics
from .validation import market_holdout_validate, walk_forward_validate


def train_panel_candidate(panel: PanelDataset, *, entity_fixed_effects: bool = True,
                          time_fixed_effects: bool = True, covariance: str = "cluster_entity",
                          minimum_training_periods: int = 4, data_status: str = "research",
                          source_manifest_hashes: tuple[str, ...] = (),
                          target_dataset_hashes: tuple[str, ...] = (), feature_table_hash: str | None = None,
                          feature_registry_version: str | None = None,
                          model_specification: ModelSpecification | None = None,
                          model_mode: str = "ad_hoc_research",
                          code_commit: str | None = None,
                          policy: ValidationPolicy | None = None) -> dict:
    if model_specification is not None:
        if panel.target != model_specification.target:
            raise ValueError("panel target does not match the governed model specification")
        if tuple(panel.features) != tuple(model_specification.features):
            raise ValueError("panel features do not match the governed model specification")
        entity_fixed_effects = model_specification.entity_fixed_effects
        time_fixed_effects = model_specification.time_fixed_effects
        covariance = model_specification.covariance
        governed_policy = ValidationPolicy.from_model_specification(model_specification)
        if policy is not None and (
            policy.minimum_sample_size < governed_policy.minimum_sample_size
            or policy.minimum_markets < governed_policy.minimum_markets
            or policy.minimum_periods < governed_policy.minimum_periods
        ):
            raise ValueError("custom validation policy cannot weaken the governed model specification")
        policy = policy or governed_policy
    else:
        policy = policy or ValidationPolicy()
    model = fit_ols(panel, entity_fixed_effects=entity_fixed_effects,
                    time_fixed_effects=time_fixed_effects, covariance=covariance)
    python_reference = cross_check_statsmodels(panel, model, entity_fixed_effects=entity_fixed_effects,
                                               time_fixed_effects=time_fixed_effects)
    r_reference = cross_check_r(panel, model, entity_fixed_effects=entity_fixed_effects,
                                time_fixed_effects=time_fixed_effects, covariance=covariance)
    diagnostics = regression_diagnostics(panel)
    # Time effects are not enabled in forward validation because the future time level is unknowable.
    walk = walk_forward_validate(panel, minimum_training_periods=minimum_training_periods,
                                 entity_fixed_effects=entity_fixed_effects, time_fixed_effects=False,
                                 covariance=covariance)
    holdout = market_holdout_validate(panel)
    stability = stability_diagnostics(panel, entity_fixed_effects=entity_fixed_effects, covariance=covariance,
                                      predictions=walk["predictions"])
    governance = assess_model(panel, walk, holdout, source_manifest_hashes=source_manifest_hashes,
                              data_status=data_status, policy=policy, python_reference=python_reference,
                              r_reference=r_reference, stability=stability,
                              target_dataset_hashes=target_dataset_hashes, feature_table_hash=feature_table_hash,
                              model_mode=model_mode, model_specification=model_specification)
    result = {
        "model": model.as_dict(), "diagnostics": diagnostics, "walk_forward": walk,
        "market_holdout": holdout, "stability": stability, "python_reference": python_reference,
        "r_reference": r_reference, "governance": governance, "training_data_hash": panel.dataset_hash,
        "source_manifest_hashes": list(source_manifest_hashes),
        "target_dataset_hashes": list(target_dataset_hashes), "feature_table_hash": feature_table_hash,
        "feature_registry_version": feature_registry_version,
        "model_specification": (model_specification.__dict__ if model_specification else None),
        "code_commit": code_commit,
        "limitations": [
            "Associations and forecasts do not establish causation.",
            "Structural breaks, source revisions, measurement error, and omitted variables may impair performance.",
            "Fixed effects absorb stable group/time differences but do not eliminate time-varying confounding.",
        ],
    }
    body = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    result["model_result_hash"] = hashlib.sha256(body.encode()).hexdigest()
    return result
