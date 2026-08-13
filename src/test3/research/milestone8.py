from __future__ import annotations

from collections import defaultdict

from test3.cre_data.geography import market_definitions
from test3.cre_data.sources.sec_avb import methodology_comparison_artifact
from test3.cre_data.versions import verification_reports
from test3.warehouse.storage import WarehousePaths

from .milestone7 import milestone7_status


def _company(row: dict) -> str | None:
    name = str(row.get("source_name") or "").casefold()
    identifier = str(row.get("source_identifier") or "").casefold()
    if "mid-america" in name or "maa" in identifier: return "MAA"
    if "avalonbay" in name or "avb" in identifier: return "AVB"
    return None


def institutional_source_coverage(paths: WarehousePaths) -> list[dict]:
    grouped = defaultdict(list)
    for report in verification_reports(paths):
        for row in report.get("observations", []):
            company = _company(row)
            if company: grouped[company].append(row)
    definitions = market_definitions(paths); output = []
    for company in ("MAA", "AVB"):
        rows = grouped[company]; approved = [row for row in rows if row.get("verification_status") == "analyst_verified"]
        markets = {row.get("geography_id") for row in rows}; approved_markets = {row.get("geography_id") for row in approved}
        approved_defs = {item["market_id"] for item in definitions if item.get("review_status") == "analyst_approved"}
        output.append({"source_company": company, "candidate_observations": len(rows),
                       "approved_observations": len(approved), "markets": len(markets),
                       "approved_markets": len(approved_markets),
                       "governed_market_definitions": len(markets & approved_defs),
                       "periods": len({row.get("period") for row in rows}),
                       "earliest": min((row.get("period") for row in rows), default=None),
                       "latest": max((row.get("period") for row in rows), default=None),
                       "metrics": sorted({row.get("metric") for row in rows})})
    return output


def milestone8_status(paths: WarehousePaths, *, include_milestone7_detail: bool = False) -> dict:
    m7 = milestone7_status(paths); sources = institutional_source_coverage(paths)
    by_source = {row["source_company"]: row for row in sources}; blockers = []
    for company in ("MAA", "AVB"):
        if not by_source[company]["approved_observations"]: blockers.append(f"AWAITING_{company}_ANALYST_ATTESTATION")
        if not by_source[company]["governed_market_definitions"]: blockers.append(f"AWAITING_{company}_MARKET_DEFINITION_APPROVAL")
    m7_summary = {"overall_status": m7["overall_status"], "attestation": m7["attestation"],
                  "validated_forecast_available": m7["validated_forecast_available"],
                  "models_evaluated": sum(item["status"] != "NOT_EVALUATED_PREREQUISITE_GATE" for item in m7["models"]),
                  "promotion_decisions": {item["model_specification"]: item["promotion_status"] for item in m7["models"]}}
    return {"milestone": 8, "sources": sources, "methodology_comparison": methodology_comparison_artifact(),
            "milestone7": m7 if include_milestone7_detail else m7_summary, "blockers": blockers,
            "experiments": {name: "NOT_EVALUATED_PREREQUISITE_GATE" for name in
                            ("maa_only", "avb_only", "pooled", "maa_to_avb", "avb_to_maa",
                             "source_holdout", "horizon_1q", "horizon_2q", "horizon_4q")},
            "promotion_status": "NO_MODEL_QUALIFIED_FOR_VALIDATED_PRODUCTION",
            "assumption_evidence_package": None, "test2_parser_validation": "NOT_RUN_NO_VALIDATED_MODEL",
            "overall_status": blockers[0] if blockers else "READY_FOR_CROSS_SOURCE_EVALUATION"}
