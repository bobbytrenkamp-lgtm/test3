from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from statistics import mean

from test3.cre_data.sources.sec_avb import COMPATIBILITY

from .datasets import PanelDataset, prepare_panel
from .linear import fit_ols
from .validation import prediction_metrics


SOURCE_COLUMN = "source_company"
GOVERNED_HORIZONS = (1, 2, 4)
HARMONIZATION_SCHEMA = "test3-cross-source-target-harmonization/1.0.0"


def _quarter_index(value: str) -> int:
    year, quarter = str(value).split("-Q")
    return int(year) * 4 + int(quarter) - 1


def exact_horizon_pairs(rows: list[dict], *, horizon: int, entity_column: str = "market_id",
                        time_column: str = "period", target_column: str = "target") -> list[dict]:
    """Pair forecast-origin rows with exact future targets; gaps are never row-shifted."""
    if horizon not in GOVERNED_HORIZONS:
        raise ValueError(f"horizon must be one of {GOVERNED_HORIZONS}")
    by_key = {(str(row[entity_column]), _quarter_index(str(row[time_column]))): row for row in rows}
    if len(by_key) != len(rows):
        raise ValueError("duplicate entity-period rows are prohibited")
    paired = []
    for row in rows:
        future = by_key.get((str(row[entity_column]), _quarter_index(str(row[time_column])) + horizon))
        if future is None: continue
        output = dict(row)
        output["forecast_origin_period"] = row[time_column]
        output["target_period"] = future[time_column]
        output["forecast_horizon_quarters"] = horizon
        output[target_column] = future[target_column]
        output["future_target_observation_id"] = future.get("target_observation_id")
        paired.append(output)
    return paired


def methodology_comparison() -> list[dict]:
    return [{"avb_metric": metric, **details} for metric, details in sorted(COMPATIBILITY.items())]


def directly_comparable_metrics() -> tuple[str, ...]:
    return tuple(row["avb_metric"] for row in methodology_comparison()
                 if row["classification"] == "directly_comparable")


def validate_target_harmonization(artifact: dict | None, *, sources: list[str]) -> dict:
    """Validate the human-approved semantic bridge; never infer comparability from labels."""
    reasons = []
    if not artifact:
        reasons.append("approved cross-source target harmonization artifact is required")
    else:
        if artifact.get("schema_version") != HARMONIZATION_SCHEMA:
            reasons.append("target harmonization schema is unsupported")
        if artifact.get("review_status") != "analyst_approved":
            reasons.append("target harmonization is not analyst approved")
        if not artifact.get("analyst_attestation_hash"):
            reasons.append("target harmonization lacks an analyst attestation hash")
        mappings = artifact.get("source_mappings") or {}
        missing = sorted(set(sources) - set(mappings))
        if missing:
            reasons.append(f"target harmonization lacks source mappings: {missing}")
        for source in sorted(set(sources) & set(mappings)):
            mapping = mappings[source]
            if not mapping.get("source_metric") or not mapping.get("methodology_version"):
                reasons.append(f"target harmonization for {source} lacks metric or methodology version")
            if mapping.get("compatibility") not in {"directly_comparable", "approved_with_controls"}:
                reasons.append(f"target harmonization for {source} is not approved as comparable")
        stated_hash = artifact.get("artifact_hash")
        body = {key: value for key, value in artifact.items() if key != "artifact_hash"}
        expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if stated_hash != expected:
            reasons.append("target harmonization artifact hash is invalid")
    return {"passed": not reasons, "reasons": reasons,
            "artifact_hash": artifact.get("artifact_hash") if artifact else None}


def _subset(panel: PanelDataset, rows: list[dict]) -> PanelDataset:
    return prepare_panel(rows, target=panel.target, features=panel.features,
                         entity_column=panel.entity_column, time_column=panel.time_column,
                         property_type_column=None)


def cross_source_generalization(panel: PanelDataset, source_by_entity: dict[str, str], *,
                                covariance: str = "hc1", target_harmonization: dict | None = None) -> dict:
    """Hard source-domain holdout; source labels never enter the predictor matrix."""
    sources = sorted(set(source_by_entity.values()))
    if len(sources) < 2:
        return {"status": "INSUFFICIENT_INDEPENDENT_SOURCES", "sources": sources, "experiments": []}
    missing = sorted(set(panel.entities) - set(source_by_entity))
    if missing:
        raise ValueError(f"source company missing for entities: {missing}")
    experiments = []
    for train_source in sources:
        for test_source in sources:
            if train_source == test_source: continue
            train_rows = [row for row in panel.rows if source_by_entity[row[panel.entity_column]] == train_source]
            test_rows = [row for row in panel.rows if source_by_entity[row[panel.entity_column]] == test_source]
            training = _subset(panel, train_rows)
            model = fit_ols(training, covariance=covariance)
            predictions = []
            prior_by_entity = {}
            for row, estimate in zip(test_rows, model.predict(test_rows), strict=True):
                entity = row[panel.entity_column]
                predictions.append({"entity": entity, "period": row[panel.time_column], "actual": row[panel.target],
                                    "prediction": estimate, "prior_actual": prior_by_entity.get(entity),
                                    "train_source": train_source, "test_source": test_source})
                prior_by_entity[entity] = row[panel.target]
            experiments.append({"train_source": train_source, "test_source": test_source,
                                "metrics": prediction_metrics(predictions), "predictions": predictions})
    harmonization = validate_target_harmonization(target_harmonization, sources=sources)
    result = {"status": "EVALUATED", "method": "train_one_source_test_another", "sources": sources,
              "experiments": experiments, "source_holdout_generalization": True}
    result["target_harmonization"] = harmonization
    result["artifact_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def company_bias(predictions: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in predictions:
        source = row.get("test_source") or row.get(SOURCE_COLUMN)
        if source: grouped[str(source)].append(float(row["actual"]) - float(row["prediction"]))
    return [{"source_company": source, "observations": len(errors), "mean_residual": mean(errors),
             "interpretation": "persistent residuals may represent portfolio/operator effects, not market fundamentals"}
            for source, errors in sorted(grouped.items())]


def cross_source_gate(result: dict, *, maximum_mae: float | None = None) -> dict:
    reasons = []
    if result.get("status") != "EVALUATED": reasons.append("two independently approved source domains are required")
    harmonization = result.get("target_harmonization") or {"passed": False,
        "reasons": ["approved cross-source target harmonization artifact is required"]}
    if not harmonization.get("passed"):
        reasons.extend(harmonization.get("reasons") or ["target harmonization failed"])
    for experiment in result.get("experiments", []):
        mae = experiment["metrics"].get("mae")
        if mae is None: reasons.append(f"{experiment['train_source']} to {experiment['test_source']} has no predictions")
        elif maximum_mae is not None and mae > maximum_mae:
            reasons.append(f"{experiment['train_source']} to {experiment['test_source']} MAE exceeds governed threshold")
    return {"passed": not reasons, "reasons": reasons,
            "promotion_note": ("cross-source validation passed" if not reasons else
                               "CURRENT ECONOMIC FEATURES DO NOT YET DEMONSTRATE CROSS-SOURCE GENERALIZATION")}
