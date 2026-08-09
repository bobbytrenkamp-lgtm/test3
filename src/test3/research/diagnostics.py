from __future__ import annotations

from math import sqrt

from .datasets import PanelDataset
from .linear import _inverse


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return None if denominator == 0 else numerator / denominator


def regression_diagnostics(panel: PanelDataset) -> dict:
    """Return governed feature correlations and correlation-matrix VIF diagnostics."""
    columns = (*panel.features, panel.target)
    values = {name: [row[name] for row in panel.rows] for name in columns}
    correlations = {
        left: {right: _correlation(values[left], values[right]) for right in columns}
        for left in columns
    }
    feature_matrix = [[correlations[left][right] for right in panel.features] for left in panel.features]
    vif = {}
    if len(panel.features) == 1:
        vif[panel.features[0]] = 1.0
    elif any(value is None for row in feature_matrix for value in row):
        vif = {name: None for name in panel.features}
    else:
        try:
            inverse = _inverse(feature_matrix, tolerance=1e-10)
            vif = {name: inverse[index][index] for index, name in enumerate(panel.features)}
        except ValueError:
            vif = {name: None for name in panel.features}
    return {
        "sample_size": len(panel.rows), "correlations": correlations, "vif": vif,
        "vif_warning": "VIF values above 5 merit review; unavailable values indicate zero variance or exact collinearity.",
        "missing_rule": "Complete cases only; no missing values were converted to zero.",
    }
