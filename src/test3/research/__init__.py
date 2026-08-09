"""Transparent, local CRE research methods."""
from .datasets import PanelDataset, prepare_panel
from .diagnostics import regression_diagnostics
from .lags import create_lagged_records, evaluate_candidate_lags
from .linear import LinearModel, fit_ols
from .governance import ValidationPolicy, assess_model
from .modeling import train_panel_candidate
from .validation import market_holdout_validate, prediction_metrics, walk_forward_validate
from .target_panel import ReadinessPolicy, build_target_panel, target_readiness

__all__ = [
    "LinearModel", "PanelDataset", "ValidationPolicy", "assess_model", "create_lagged_records",
    "evaluate_candidate_lags", "fit_ols",
    "market_holdout_validate", "prediction_metrics", "prepare_panel", "regression_diagnostics",
    "train_panel_candidate", "walk_forward_validate", "ReadinessPolicy", "build_target_panel", "target_readiness",
]
