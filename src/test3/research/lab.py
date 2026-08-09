from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb

from test3.cre_data.importer import cre_status
from test3.features.panel import FeaturePanel
from test3.research.target_panel import target_readiness
from test3.research.specifications import MODEL_SPECIFICATIONS
from test3.research.target_panel import target_readiness_for_specification
from test3.cre_data.sources import source_catalog
from test3.cre_data.geography import market_definitions
from test3.warehouse.duckdb_engine import WarehouseEngine, sql_literal
from test3.warehouse.manifests import active_manifests
from test3.warehouse.reporting import coverage_report
from test3.warehouse.storage import WarehousePaths


FEATURE_TABLES = ("county_year", "county_quarter", "cbsa_year", "cbsa_quarter")


def _target_coverage(paths: WarehousePaths) -> list[dict]:
    manifests = active_manifests(paths)
    files = [str(path) for item in manifests for path in item["resolved_files"]]
    if not files:
        return []
    source = "read_parquet([" + ",".join(sql_literal(path) for path in files) + "], union_by_name=true)"
    with duckdb.connect(":memory:") as connection:
        result = connection.execute(f"""SELECT property_type,metric,geography_type,period_type,
            count(*) observations,count(DISTINCT geography_id) markets,
            min(observation_date) earliest,max(observation_date) latest,
            count(*) FILTER (WHERE quality_level='high') high_quality
          FROM {source}
          WHERE source_id='user_import' AND property_type IS NOT NULL
          GROUP BY ALL ORDER BY property_type,metric,geography_type,period_type""")
        names = [item[0] for item in result.description]
        return [dict(zip(names, row, strict=True)) for row in result.fetchall()]


def _feature_tables(paths: WarehousePaths) -> list[dict]:
    output = []
    for table in FEATURE_TABLES:
        latest = FeaturePanel(paths, table).latest()
        if latest is None:
            output.append({"table": table, "status": "not_built", "rows": 0, "features": 0})
            continue
        output.append({
            "table": table, "status": "validated", "rows": latest.get("row_count", 0),
            "features": len(latest.get("features", [])), "created_at": latest.get("created_at"),
            "earliest": latest.get("earliest_period"), "latest": latest.get("latest_period"),
            "manifest_hash": latest.get("manifest_hash"),
        })
    return output


def _models(database, organization_id: str) -> list[dict]:
    with database.connect() as connection:
        rows = connection.execute("""SELECT id,model_name,model_version,target_assumption,
            property_types_json,geographic_coverage_json,sample_size,coefficients_json,
            standard_errors_json,model_metrics_json,residual_diagnostics_json,limitations_json,
            data_status,validation_state,artifact_content_hash,created_at
          FROM model_artifacts WHERE organization_id=? ORDER BY created_at DESC LIMIT 100""",
          (organization_id,)).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        for field in ("property_types_json", "geographic_coverage_json", "coefficients_json",
                      "standard_errors_json", "model_metrics_json", "residual_diagnostics_json",
                      "limitations_json"):
            item[field.removesuffix("_json")] = json.loads(item.pop(field))
        output.append(item)
    return output


def _target_workbench(paths: WarehousePaths) -> dict:
    root = paths.contained(Path("verification") / "cre")
    reports = []
    for path in sorted(root.glob("dataset=*/version=*/verification.json")) if root.exists() else ():
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    cells, methodologies, findings = {}, {}, []
    for report in reports:
        findings.extend({**item, "dataset_id": report["dataset_id"], "source_version": report["source_version"]}
                        for item in report.get("findings", []))
        for row in report.get("observations", []):
            key = (row["property_type"], row["metric"], row["geography_id"], row["period"])
            cells.setdefault(key, {"property_type": row["property_type"], "target": row["metric"],
                                   "market": row["geography_id"], "period": row["period"],
                                   "eligible": 0, "observations": 0})
            cells[key]["observations"] += 1
            cells[key]["eligible"] += int(bool(row.get("model_eligible")))
            series = (row["property_type"], row["metric"], row["geography_id"], row["source_name"])
            methodologies.setdefault(series, set()).add(row["methodology"])
    return {
        "coverage_matrix": sorted(cells.values(), key=lambda item: (item["property_type"], item["target"], item["market"], item["period"]))[:5000],
        "coverage_truncated": len(cells) > 5000,
        "conflicts": [item for item in findings if item["code"] == "source_conflict"][:500],
        "methodology_changes": [
            {"property_type": key[0], "target": key[1], "market": key[2], "source": key[3],
             "methodologies": sorted(values)} for key, values in methodologies.items() if len(values) > 1
        ][:500],
    }


def research_lab_report(data_dir: str | Path, database, organization_id: str) -> dict:
    """Return a bounded, read-only view of actual warehouse and model evidence."""
    paths = WarehousePaths.from_data_root(data_dir)
    paths.initialize()
    errors: list[dict] = []

    def checked(component: str, operation, fallback):
        try:
            return operation()
        except (OSError, ValueError, RuntimeError, duckdb.Error, json.JSONDecodeError) as exc:
            errors.append({"component": component, "error": str(exc)})
            return fallback

    summary = checked("warehouse", lambda: WarehouseEngine(paths).summary(),
                      {"files": 0, "rows": 0, "metrics": 0, "earliest": None, "latest": None})
    coverage = checked("coverage", lambda: coverage_report(paths), [])
    targets = checked("cre_targets", lambda: _target_coverage(paths), [])
    features = checked("feature_tables", lambda: _feature_tables(paths), [])
    imports = checked("cre_verification", lambda: cre_status(paths), [])
    readiness_by_target = checked("target_readiness", lambda: target_readiness(paths), [])
    specification_readiness = checked("model_specific_readiness", lambda: [
        target_readiness_for_specification(paths, MODEL_SPECIFICATIONS[name]) for name in sorted(MODEL_SPECIFICATIONS)], [])
    target_workbench = checked("target_workbench", lambda: _target_workbench(paths), {})
    sources = checked("cre_source_catalog", source_catalog, [])
    definitions = checked("market_definitions", lambda: market_definitions(paths), [])
    models = checked("models", lambda: _models(database, organization_id), [])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "degraded" if errors else "ready",
        "warehouse": summary,
        "coverage": coverage[:500],
        "coverage_truncated": len(coverage) > 500,
        "cre_targets": targets[:500],
        "cre_imports": imports[:100],
        "target_readiness": readiness_by_target[:500],
        "model_specific_readiness": specification_readiness,
        "target_workbench": target_workbench,
        "target_sources": sources,
        "market_definitions": definitions,
        "feature_tables": features,
        "models": models,
        "model_summary": {
            "total": len(models),
            "validated_real": sum(item["validation_state"] == "validated" and item["data_status"] == "real" for item in models),
            "rejected": sum(item["validation_state"] == "rejected" for item in models),
            "synthetic": sum(item["data_status"] == "fictional_synthetic" for item in models),
        },
        "readiness": {
            "has_public_predictors": bool(coverage),
            "has_verified_cre_targets": any(item.get("high_quality", 0) > 0 for item in targets),
            "has_validated_real_model": any(item["validation_state"] == "validated" and item["data_status"] == "real" for item in models),
            "note": "A model cannot be promoted without verified real CRE targets and out-of-sample baseline improvement.",
        },
        "errors": errors,
    }
