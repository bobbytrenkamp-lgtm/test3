from __future__ import annotations

from collections import defaultdict
from test3.warehouse.storage import WarehousePaths
from .metrics import CRE_METRICS
from .versions import verification_reports


def _period_index(period: str, frequency: str) -> int:
    if frequency == "annual":
        return int(period[:4])
    if frequency == "quarterly":
        return int(period[:4]) * 4 + int(period[-1]) - 1
    if frequency == "monthly":
        return int(period[:4]) * 12 + int(period[5:7]) - 1
    raise ValueError(f"unsupported CRE series frequency: {frequency}")


def series_quality_scorecard(paths: WarehousePaths, *, property_type: str | None = None,
                             metric: str | None = None) -> list[dict]:
    """Expose auditable quality components for each active source-market series."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for report in verification_reports(paths):
        for row in report.get("observations", []):
            if property_type and row.get("property_type") != property_type:
                continue
            if metric and row.get("metric") != metric:
                continue
            key = (row["source_name"], row["property_type"], row["metric"],
                   row["geography_type"], row["geography_id"])
            groups[key].append(row)
    output = []
    for key, rows in sorted(groups.items()):
        frequencies = {row["frequency"] for row in rows}
        periods = {row["period"] for row in rows}
        duplicate_periods = len(rows) - len(periods)
        expected_periods = None
        missing_periods = None
        coverage_ratio = None
        if len(frequencies) == 1 and periods:
            frequency = next(iter(frequencies))
            indexes = [_period_index(period, frequency) for period in periods]
            expected_periods = max(indexes) - min(indexes) + 1
            missing_periods = expected_periods - len(periods)
            coverage_ratio = round(len(periods) / expected_periods, 6)
        methodologies = {row["methodology"] for row in rows}
        findings = defaultdict(int)
        for row in rows:
            for finding in row.get("verification_findings", []):
                findings[finding] += 1
        output.append({
            "source": key[0], "property_type": key[1], "metric": key[2],
            "geography_type": key[3], "market": key[4], "observations": len(rows),
            "earliest_period": min(periods, default=None), "latest_period": max(periods, default=None),
            "frequency": next(iter(frequencies)) if len(frequencies) == 1 else "mixed",
            "expected_periods": expected_periods, "missing_periods": missing_periods,
            "coverage_ratio": coverage_ratio, "duplicate_periods": duplicate_periods,
            "methodology_versions": len(methodologies),
            "methodology_consistent": len(methodologies) == 1,
            "unit_consistent": len({row["unit"] for row in rows}) == 1,
            "release_date_coverage": round(sum(bool(row.get("release_date")) for row in rows) / len(rows), 6),
            "verification_rate": round(sum(row.get("verification_status") == "analyst_verified" for row in rows) / len(rows), 6),
            "model_eligible_rate": round(sum(bool(row.get("model_eligible")) for row in rows) / len(rows), 6),
            "findings": dict(sorted(findings.items())),
        })
    return output


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
