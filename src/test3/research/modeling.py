from __future__ import annotations

from .datasets import PanelDataset
from .diagnostics import regression_diagnostics
from .governance import ValidationPolicy, assess_model
from .linear import fit_ols
from .validation import market_holdout_validate, walk_forward_validate


def train_panel_candidate(panel: PanelDataset, *, entity_fixed_effects: bool = True,
                          time_fixed_effects: bool = True, covariance: str = "cluster_entity",
                          minimum_training_periods: int = 4, data_status: str = "research",
                          source_manifest_hashes: tuple[str, ...] = (),
                          policy: ValidationPolicy = ValidationPolicy()) -> dict:
    model = fit_ols(panel, entity_fixed_effects=entity_fixed_effects,
                    time_fixed_effects=time_fixed_effects, covariance=covariance)
    diagnostics = regression_diagnostics(panel)
    # Time effects are not enabled in forward validation because the future time level is unknowable.
    walk = walk_forward_validate(panel, minimum_training_periods=minimum_training_periods,
                                 entity_fixed_effects=entity_fixed_effects, time_fixed_effects=False,
                                 covariance=covariance)
    holdout = market_holdout_validate(panel)
    governance = assess_model(panel, walk, holdout, source_manifest_hashes=source_manifest_hashes,
                              data_status=data_status, policy=policy)
    return {
        "model": model.as_dict(), "diagnostics": diagnostics, "walk_forward": walk,
        "market_holdout": holdout, "governance": governance, "training_data_hash": panel.dataset_hash,
        "source_manifest_hashes": list(source_manifest_hashes),
        "limitations": [
            "Associations and forecasts do not establish causation.",
            "Structural breaks, source revisions, measurement error, and omitted variables may impair performance.",
            "Fixed effects absorb stable group/time differences but do not eliminate time-varying confounding.",
        ],
    }
