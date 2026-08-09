from __future__ import annotations

from dataclasses import dataclass
from math import erfc, sqrt
from typing import Iterable

from .datasets import PanelDataset


def _transpose(matrix):
    return [list(column) for column in zip(*matrix, strict=True)]


def _matmul(left, right):
    return [[sum(a * b for a, b in zip(row, column, strict=True)) for column in zip(*right, strict=True)] for row in left]


def _inverse(matrix, tolerance=1e-12):
    size = len(matrix)
    work = [list(row) + [1.0 if i == j else 0.0 for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) <= tolerance:
            raise ValueError("design matrix is rank deficient; remove collinear predictors or fixed effects")
        work[column], work[pivot] = work[pivot], work[column]
        scale = work[column][column]
        work[column] = [value / scale for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [value - factor * pivot_value for value, pivot_value in zip(work[row], work[column], strict=True)]
    return [row[size:] for row in work]


def _quadratic_sandwich(inverse, meat):
    return _matmul(_matmul(inverse, meat), inverse)


def _metrics(actual, predicted):
    errors = [a - p for a, p in zip(actual, predicted, strict=True)]
    return {
        "mae": sum(abs(item) for item in errors) / len(errors),
        "rmse": sqrt(sum(item * item for item in errors) / len(errors)),
        "bias": sum(errors) / len(errors),
        "residual_mean": sum(errors) / len(errors),
        "residual_std": sqrt(sum((item - sum(errors) / len(errors)) ** 2 for item in errors) / max(1, len(errors) - 1)),
    }


@dataclass(frozen=True)
class LinearModel:
    target: str
    feature_names: tuple[str, ...]
    design_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    standard_errors: tuple[float, ...]
    p_values: tuple[float, ...]
    covariance_type: str
    entity_levels: tuple[str, ...]
    time_levels: tuple[str, ...]
    entity_column: str
    time_column: str
    diagnostics: dict

    def predict(self, rows: Iterable[dict]) -> list[float]:
        output = []
        for row in rows:
            design = [1.0, *(float(row[name]) for name in self.feature_names)]
            design.extend(1.0 if row[self.entity_column] == value else 0.0 for value in self.entity_levels)
            design.extend(1.0 if row[self.time_column] == value else 0.0 for value in self.time_levels)
            output.append(sum(value * coefficient for value, coefficient in zip(design, self.coefficients, strict=True)))
        return output

    def as_dict(self) -> dict:
        return {
            "target": self.target, "features": list(self.feature_names), "covariance_type": self.covariance_type,
            "coefficients": dict(zip(self.design_names, self.coefficients, strict=True)),
            "standard_errors": dict(zip(self.design_names, self.standard_errors, strict=True)),
            "p_values": dict(zip(self.design_names, self.p_values, strict=True)), "diagnostics": self.diagnostics,
            "inference_note": "P-values use an asymptotic normal approximation; association and prediction do not establish causation.",
        }


def fit_ols(panel: PanelDataset, *, entity_fixed_effects: bool = False, time_fixed_effects: bool = False,
            covariance: str = "hc1") -> LinearModel:
    if covariance not in {"classical", "hc1", "cluster_entity"}:
        raise ValueError("covariance must be classical, hc1, or cluster_entity")
    rows = panel.rows
    entity_levels = tuple(sorted({row[panel.entity_column] for row in rows})[1:]) if entity_fixed_effects else ()
    time_levels = tuple(sorted({row[panel.time_column] for row in rows})[1:]) if time_fixed_effects else ()
    names = ("intercept", *panel.features, *(f"entity[{value}]" for value in entity_levels), *(f"time[{value}]" for value in time_levels))
    x, y = [], []
    for row in rows:
        x.append([1.0, *(row[name] for name in panel.features),
                  *(1.0 if row[panel.entity_column] == level else 0.0 for level in entity_levels),
                  *(1.0 if row[panel.time_column] == level else 0.0 for level in time_levels)])
        y.append(row[panel.target])
    n, k = len(x), len(names)
    if n <= k:
        raise ValueError(f"insufficient observations for regression: n={n}, parameters={k}")
    xt = _transpose(x); xtx_inverse = _inverse(_matmul(xt, x))
    beta = [row[0] for row in _matmul(_matmul(xtx_inverse, xt), [[value] for value in y])]
    predicted = [sum(a * b for a, b in zip(row, beta, strict=True)) for row in x]
    errors = [actual - estimate for actual, estimate in zip(y, predicted, strict=True)]
    if covariance == "classical":
        scale = sum(value * value for value in errors) / (n - k)
        cov = [[value * scale for value in row] for row in xtx_inverse]
    elif covariance == "hc1":
        meat = [[0.0] * k for _ in range(k)]
        for row, error in zip(x, errors, strict=True):
            for i in range(k):
                for j in range(k):
                    meat[i][j] += error * error * row[i] * row[j]
        correction = n / (n - k)
        cov = [[value * correction for value in row] for row in _quadratic_sandwich(xtx_inverse, meat)]
    else:
        clusters = {}
        for row, design, error in zip(rows, x, errors, strict=True):
            score = clusters.setdefault(row[panel.entity_column], [0.0] * k)
            for index in range(k):
                score[index] += design[index] * error
        group_count = len(clusters)
        if group_count < 2:
            raise ValueError("clustered covariance requires at least two entities")
        meat = [[sum(score[i] * score[j] for score in clusters.values()) for j in range(k)] for i in range(k)]
        correction = group_count / (group_count - 1) * (n - 1) / (n - k)
        cov = [[value * correction for value in row] for row in _quadratic_sandwich(xtx_inverse, meat)]
    standard_errors = [sqrt(max(0.0, cov[index][index])) for index in range(k)]
    p_values = [erfc(abs(coefficient / error) / sqrt(2)) if error > 0 else 0.0 for coefficient, error in zip(beta, standard_errors, strict=True)]
    mean_y = sum(y) / n; sse = sum(value * value for value in errors); sst = sum((value - mean_y) ** 2 for value in y)
    diagnostics = _metrics(y, predicted)
    diagnostics.update({
        "sample_size": n, "parameter_count": k, "degrees_of_freedom": n - k,
        "r_squared": None if sst == 0 else 1 - sse / sst,
        "adjusted_r_squared": None if sst == 0 else 1 - (1 - (1 - sse / sst)) * (n - 1) / (n - k),
        "entities": len({row[panel.entity_column] for row in rows}), "periods": len({row[panel.time_column] for row in rows}),
        "excluded_missing": panel.excluded_missing, "entity_fixed_effects": entity_fixed_effects,
        "time_fixed_effects": time_fixed_effects,
    })
    return LinearModel(panel.target, panel.features, tuple(names), tuple(beta), tuple(standard_errors), tuple(p_values),
                       covariance, entity_levels, time_levels, panel.entity_column, panel.time_column, diagnostics)
