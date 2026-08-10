from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from test3.warehouse.storage import WarehousePaths
from .metrics import CRE_METRICS


def verification_reports(paths: WarehousePaths) -> list[dict]:
    root = paths.contained(Path("verification") / "cre")
    if not root.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(root.glob("dataset=*/version=*/verification.json"))]


def target_data_audit(paths: WarehousePaths) -> list[dict]:
    """Audit installed CRE evidence without counting proxies as institutional targets."""
    groups: dict[tuple, dict] = {}
    for report in verification_reports(paths):
        for row in report.get("observations", []):
            key = (row["property_type"], row["metric"], row["source_name"],
                   row.get("target_classification", "institutional_target"))
            item = groups.setdefault(key, {
                "property_type": key[0], "metric": key[1], "source": key[2],
                "classification": key[3], "markets": set(), "periods": set(),
                "observations": 0, "verified": 0, "model_eligible": 0,
                "earliest_period": None, "latest_period": None,
                "license_status": set(), "automation_status": "local_file_only",
            })
            item["observations"] += 1
            item["verified"] += int(row.get("verification_status") == "analyst_verified")
            item["model_eligible"] += int(bool(row.get("model_eligible")))
            item["markets"].add(row["geography_id"]); item["periods"].add(row["period"])
            item["license_status"].add("documented" if row.get("licensing_notes") else "missing")
            item["earliest_period"] = min(filter(None, (item["earliest_period"], row["period"])), default=row["period"])
            item["latest_period"] = max(filter(None, (item["latest_period"], row["period"])), default=row["period"])
    output = []
    for key in sorted(groups):
        item = groups[key]
        output.append({**item, "markets": len(item["markets"]), "periods": len(item["periods"]),
                       "license_status": "mixed" if len(item["license_status"]) > 1 else next(iter(item["license_status"]))})
    installed = {(item["property_type"], item["metric"]) for item in output}
    for metric, spec in sorted(CRE_METRICS.items()):
        for property_type in spec.property_types:
            if (property_type, metric) in installed:
                continue
            output.append({"property_type": property_type, "metric": metric, "source": None,
                           "classification": "institutional_target", "markets": 0, "periods": 0,
                           "observations": 0, "verified": 0, "model_eligible": 0,
                           "earliest_period": None, "latest_period": None,
                           "license_status": "not_applicable", "automation_status": "no_source_installed"})
    return sorted(output, key=lambda item: (item["property_type"], item["metric"], item["source"] or ""))


def target_readiness_funnel(paths: WarehousePaths, *, property_type: str | None = None,
                            metric: str | None = None) -> dict:
    stages = defaultdict(int)
    excluded = defaultdict(int)
    for report in verification_reports(paths):
        invalid = report.get("invalid_rows", [])
        if not property_type and not metric:
            stages["raw_candidates"] += len(invalid)
        for row in report.get("observations", []):
            if property_type and row["property_type"] != property_type:
                continue
            if metric and row["metric"] != metric:
                continue
            stages["raw_candidates"] += 1
            stages["structurally_valid"] += 1
            if row.get("licensing_notes"):
                stages["rights_documented"] += 1
            else:
                excluded["missing_rights"] += 1
                continue
            if row.get("verification_status") == "analyst_verified":
                stages["analyst_reviewed"] += 1
            else:
                excluded["not_analyst_reviewed"] += 1
                continue
            findings = set(row.get("verification_findings", []))
            if "source_conflict" not in findings:
                stages["conflict_resolved"] += 1
            else:
                excluded["source_conflict"] += 1
                continue
            if not findings.intersection({"methodology_change", "methodology_mismatch", "market_geography_mismatch"}):
                stages["methodology_compatible"] += 1
            else:
                excluded["methodology_or_geography"] += 1
                continue
            if row.get("model_eligible"):
                stages["model_eligible"] += 1
            else:
                excluded["other_quality_gate"] += 1
    order = ("raw_candidates", "structurally_valid", "rights_documented", "analyst_reviewed",
             "conflict_resolved", "methodology_compatible", "model_eligible")
    return {"property_type": property_type, "metric": metric,
            "stages": [{"stage": stage, "count": stages[stage]} for stage in order],
            "excluded": dict(sorted(excluded.items()))}


def coverage_matrix(paths: WarehousePaths, *, property_type: str, metric: str) -> dict:
    cells, markets, periods = {}, set(), set()
    for report in verification_reports(paths):
        for row in report.get("observations", []):
            if row["property_type"] != property_type or row["metric"] != metric:
                continue
            markets.add(row["geography_id"]); periods.add(row["period"])
            key = (row["geography_id"], row["period"])
            cell = cells.setdefault(key, {"observations": 0, "eligible": 0, "sources": set()})
            cell["observations"] += 1; cell["eligible"] += int(bool(row.get("model_eligible")))
            cell["sources"].add(row["source_name"])
    return {"property_type": property_type, "metric": metric, "markets": sorted(markets), "periods": sorted(periods),
            "cells": [{"market": key[0], "period": key[1], **value, "sources": sorted(value["sources"])}
                      for key, value in sorted(cells.items())]}
