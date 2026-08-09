from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
import math

from .datasets import PanelDataset
from .linear import LinearModel


@dataclass(frozen=True)
class CrossCheckTolerances:
    coefficient_absolute: float = 1e-7
    standard_error_absolute: float = 1e-6
    r_squared_absolute: float = 1e-9


def _design(panel: PanelDataset, entity_fixed_effects: bool, time_fixed_effects: bool):
    entity_levels = tuple(sorted(panel.entities)[1:]) if entity_fixed_effects else ()
    time_levels = tuple(sorted(panel.periods)[1:]) if time_fixed_effects else ()
    names = ("intercept", *panel.features, *(f"entity[{value}]" for value in entity_levels),
             *(f"time[{value}]" for value in time_levels))
    matrix, target, groups = [], [], []
    for row in panel.rows:
        matrix.append([1.0, *(row[name] for name in panel.features),
                       *(1.0 if row[panel.entity_column] == level else 0.0 for level in entity_levels),
                       *(1.0 if row[panel.time_column] == level else 0.0 for level in time_levels)])
        target.append(row[panel.target]); groups.append(row[panel.entity_column])
    return names, matrix, target, groups


def cross_check_statsmodels(panel: PanelDataset, native: LinearModel, *, entity_fixed_effects: bool = False,
                            time_fixed_effects: bool = False,
                            tolerances: CrossCheckTolerances = CrossCheckTolerances()) -> dict:
    """Independently verify native regression when optional statsmodels is installed."""
    if importlib.util.find_spec("statsmodels") is None or importlib.util.find_spec("numpy") is None:
        return {"status": "not_available", "reason": "Optional local statsmodels/numpy runtime is not installed.",
                "tolerances": asdict(tolerances)}
    import numpy as np  # type: ignore[import-not-found]
    import statsmodels.api as sm  # type: ignore[import-not-found]

    names, matrix, target, groups = _design(panel, entity_fixed_effects, time_fixed_effects)
    result = sm.OLS(np.asarray(target, dtype=float), np.asarray(matrix, dtype=float)).fit()
    if native.covariance_type == "hc1":
        result = result.get_robustcov_results(cov_type="HC1")
    elif native.covariance_type == "cluster_entity":
        result = result.get_robustcov_results(cov_type="cluster", groups=np.asarray(groups), use_correction=True)
    coefficients = dict(zip(names, (float(value) for value in result.params), strict=True))
    standard_errors = dict(zip(names, (float(value) for value in result.bse), strict=True))
    coefficient_difference = max(abs(coefficients[name] - native.coefficients[index]) for index, name in enumerate(names))
    se_difference = max(abs(standard_errors[name] - native.standard_errors[index]) for index, name in enumerate(names))
    r_squared_difference = abs(float(result.rsquared) - float(native.diagnostics["r_squared"]))
    passed = (coefficient_difference <= tolerances.coefficient_absolute and
              se_difference <= tolerances.standard_error_absolute and
              r_squared_difference <= tolerances.r_squared_absolute)
    values = (coefficient_difference, se_difference, r_squared_difference)
    if not all(math.isfinite(value) for value in values):
        passed = False
    return {
        "status": "passed" if passed else "failed", "coefficients": coefficients,
        "standard_errors": standard_errors, "r_squared": float(result.rsquared),
        "adjusted_r_squared": float(result.rsquared_adj), "sample_size": int(result.nobs),
        "coefficient_max_difference": coefficient_difference, "se_max_difference": se_difference,
        "r_squared_difference": r_squared_difference, "tolerances": asdict(tolerances),
    }
