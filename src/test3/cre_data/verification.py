from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from statistics import median

from .metrics import get_cre_metric


SOURCE_RELIABILITY = {
    "federal_public": .98, "state_local_public": .92, "academic_open": .88,
    "brokerage_public_report": .78, "public_brokerage_report": .78, "analyst_owned": .72,
    "public_company_filing": .90, "user_owned": .72, "licensed_local": .75,
    "manual_research": .60, "unknown": .40,
}


def _period_index(label: str, frequency: str) -> int:
    if frequency == "annual":
        return int(label[:4])
    if frequency == "quarterly":
        return int(label[:4]) * 4 + int(label[-1]) - 1
    if frequency == "monthly":
        return int(label[:4]) * 12 + int(label[5:7]) - 1
    raise ValueError("gap checks support monthly, quarterly, and annual observations")


def _natural(row: dict) -> tuple:
    return (row["geography_type"], row["geography_id"], row["period"], row["frequency"], row["property_type"],
            row.get("property_subtype"), row["metric"])


def _series(row: dict, include_source: bool = False) -> tuple:
    key = (row["geography_type"], row["geography_id"], row["frequency"], row["property_type"],
           row.get("property_subtype"), row["metric"], row["methodology"])
    return key + ((row["source_name"], row["source_identifier"]) if include_source else ())


def _difference(left: Decimal, right: Decimal, measure_type: str) -> Decimal:
    if measure_type in {"rate", "signed_rate"}:
        return abs(left - right)
    scale = max(abs(left), abs(right), Decimal("0.000000001"))
    return abs(left - right) / scale


def verify_observations(rows: list[dict], *, evaluated_at: str | date | None = None,
                        analyst_review_confirmed: bool = False,
                        governed_market_ids: frozenset[str] | None = None) -> dict:
    evaluation_date = date.fromisoformat(str(evaluated_at)[:10]) if evaluated_at else date.today()
    findings, by_observation = [], defaultdict(list)
    exact, natural, revision, series, cadence, method_series = (defaultdict(list) for _ in range(6))
    for row in rows:
        exact[(_natural(row), row["source_name"], row["source_identifier"], row["vintage"], row["methodology"])].append(row)
        natural[_natural(row)].append(row)
        revision[(_natural(row), row["source_name"], row["source_identifier"], row["methodology"])].append(row)
        series[_series(row, include_source=True)].append(row)
        cadence[(row["geography_type"], row["geography_id"], row["property_type"], row.get("property_subtype"),
                 row["metric"], row["methodology"], row["source_name"], row["source_identifier"])].append(row)
        method_series[(row["geography_type"], row["geography_id"], row["property_type"], row.get("property_subtype"),
                       row["metric"], row["source_name"], row["source_identifier"])].append(row)
    def add(code, severity, message, affected):
        item = {"code": code, "severity": severity, "message": message,
                "observation_ids": sorted({row["observation_id"] for row in affected})}
        findings.append(item)
        for row in affected:
            by_observation[row["observation_id"]].append(code)
    for grouped in exact.values():
        if len(grouped) > 1:
            add("duplicate_observation", "error", "Duplicate natural observation within one source vintage.", grouped)
    for grouped in natural.values():
        methods = {row["methodology"] for row in grouped}
        if len(methods) > 1:
            add("methodology_mismatch", "warning", "Sources use materially different governed methodologies; do not combine automatically.", grouped)
        values = [Decimal(row["value"]) for row in grouped]
        spec = get_cre_metric(grouped[0]["metric"], grouped[0]["property_type"])
        distinct_sources = {(row["source_name"], row["source_identifier"]) for row in grouped}
        if len(distinct_sources) > 1 and max(_difference(left, right, spec.measure_type) for left in values for right in values) > Decimal("0.05"):
            add("source_conflict", "warning", "Independent sources disagree beyond the governed five-point/five-percent review tolerance.", grouped)
    for grouped in revision.values():
        vintages = {row["vintage"] for row in grouped}
        values = {row["value"] for row in grouped}
        if len(vintages) > 1 and len(values) > 1:
            add("revised_observation", "info", "A later source vintage reports a different value; both vintages are retained.", grouped)
    for grouped in cadence.values():
        if len({row["frequency"] for row in grouped}) > 1:
            add("frequency_mismatch", "warning", "One source series changes frequency; series must remain separate until explicitly transformed.", grouped)
    for grouped in method_series.values():
        if len({row["methodology"] for row in grouped}) > 1:
            add("methodology_change", "warning", "Source methodology changes within the longitudinal series; affected periods require explicit reconciliation.", grouped)
    if governed_market_ids is not None:
        for row in rows:
            if row["geography_type"] in {"market", "submarket"} and row["geography_id"] not in governed_market_ids:
                add("market_geography_mismatch", "error", "CRE market has no effective governed geographic definition.", (row,))
    for row in rows:
        if row.get("target_classification") != "institutional_target":
            add("proxy_not_institutional_target", "info", "Proxy/context evidence is retained but cannot become a CRE model target.", (row,))
    for grouped in series.values():
        ordered = sorted(grouped, key=lambda row: _period_index(row["period"], row["frequency"]))
        for left, right in zip(ordered, ordered[1:]):
            gap = _period_index(right["period"], right["frequency"]) - _period_index(left["period"], left["frequency"])
            if gap > 1:
                add("missing_periods", "warning", f"Series has {gap - 1} missing governed period(s).", (left, right))
            spec = get_cre_metric(right["metric"], right["property_type"])
            if spec.jump_review_threshold is not None:
                change = _difference(Decimal(left["value"]), Decimal(right["value"]), spec.measure_type)
                if change > Decimal(str(spec.jump_review_threshold)):
                    add("sudden_jump", "warning", f"Adjacent-period change {change} exceeds the metric review threshold.", (left, right))
    scored = []
    for row in rows:
        group = natural[_natural(row)]
        spec = get_cre_metric(row["metric"], row["property_type"])
        peers = [item for item in group if (item["source_name"], item["source_identifier"]) != (row["source_name"], row["source_identifier"])]
        if peers:
            agreement = max(0.0, 1.0 - float(median(_difference(Decimal(row["value"]), Decimal(item["value"]), spec.measure_type) for item in peers)) / .10)
        else:
            agreement = .50
        retrieval_age = max(0, (evaluation_date - datetime.fromisoformat(row["retrieved_at"]).date()).days)
        recency = 1.0 if retrieval_age <= 365 else .75 if retrieval_age <= 730 else .50 if retrieval_age <= 1825 else .25
        completeness = sum(row.get(field) not in (None, "", "unknown") for field in
                           ("release_date", "sample_count", "notes", "redistribution_permitted")) / 4
        effective_verified = row["verification_status"] == "analyst_verified" and analyst_review_confirmed
        if row["verification_status"] == "analyst_verified" and not analyst_review_confirmed:
            add("unconfirmed_verification", "warning", "File-declared verification was not accepted without an explicit operator review flag.", (row,))
        status = 1.0 if effective_verified else 0.0 if row["verification_status"] == "rejected" else .45
        if retrieval_age > 730:
            add("stale_retrieval", "warning", "Source snapshot was retrieved more than two years before verification.", (row,))
        anomaly = 0.0 if any(code in by_observation[row["observation_id"]] for code in ("duplicate_observation", "sudden_jump")) else 1.0
        components = {"source_reliability": SOURCE_RELIABILITY[row["source_class"]], "methodology_clarity": 1.0,
                      "independent_agreement": agreement, "recency": recency, "completeness": completeness,
                      "analyst_verification": status, "series_consistency": anomaly}
        confidence = sum(components[name] * weight for name, weight in
                         (("source_reliability", .25), ("methodology_clarity", .15), ("independent_agreement", .15),
                          ("recency", .10), ("completeness", .10), ("analyst_verification", .15), ("series_consistency", .10)))
        blocking_codes = {"duplicate_observation", "methodology_change", "market_geography_mismatch",
                          "proxy_not_institutional_target"}
        blocking = row["verification_status"] == "rejected" or bool(blocking_codes & set(by_observation[row["observation_id"]]))
        scored.append({**row, "confidence": round(confidence, 6), "confidence_components": components,
                       "verification_findings": sorted(by_observation[row["observation_id"]]),
                       "model_eligible": effective_verified and not blocking})
    return {"observations": scored, "findings": sorted(findings, key=lambda item: (item["code"], item["observation_ids"])),
            "summary": {"observations": len(rows), "model_eligible": sum(row["model_eligible"] for row in scored),
                        "verified": sum(row["verification_status"] == "analyst_verified" and analyst_review_confirmed for row in rows),
                        "unverified": sum(row["verification_status"] == "unverified" for row in rows),
                        "rejected": sum(row["verification_status"] == "rejected" for row in rows),
                        "findings": len(findings), "conflicts": sum(item["code"] == "source_conflict" for item in findings)}}


def available_as_of(rows: list[dict], forecast_origin: str | date) -> dict:
    """Exclude observations unavailable at a historical forecast origin."""
    origin = date.fromisoformat(str(forecast_origin)[:10])
    included, excluded, limitations = [], [], set()
    for row in rows:
        if row.get("release_date"):
            available = date.fromisoformat(row["release_date"])
            basis = "release_date"
        else:
            available = datetime.fromisoformat(row["retrieved_at"]).date()
            basis = "retrieved_at_conservative_fallback"
            limitations.add("Release date unavailable; retrieval date was used conservatively and does not recreate a true historical vintage.")
        if available <= origin:
            included.append(row)
        else:
            excluded.append({"observation_id": row["observation_id"], "available_date": available.isoformat(),
                             "forecast_origin": origin.isoformat(), "basis": basis, "code": "future_data_leakage"})
    return {"forecast_origin": origin.isoformat(), "included": included, "excluded": excluded,
            "limitations": sorted(limitations), "look_ahead": False}


def reconcile_observations(rows: list[dict], *, source_priority: tuple[str, ...]) -> list[dict]:
    """Select one explicit verified source per natural key; never average conflicting values."""
    if not source_priority or len(set(source_priority)) != len(source_priority):
        raise ValueError("source_priority must be a unique non-empty ordered list")
    priority = {source: index for index, source in enumerate(source_priority)}
    grouped = defaultdict(list)
    for row in rows:
        grouped[_natural(row)].append(row)
    output = []
    for key, candidates in sorted(grouped.items()):
        eligible = [row for row in candidates if row.get("model_eligible") and row["source_name"] in priority]
        if not eligible:
            continue
        chosen = min(eligible, key=lambda row: (priority[row["source_name"]], -row["confidence"],
                                                -datetime.fromisoformat(row["retrieved_at"]).timestamp(), row["observation_id"]))
        output.append({"natural_key": key, "selected_observation_id": chosen["observation_id"], "value": chosen["value"],
                       "source_name": chosen["source_name"], "selection_method": "explicit_source_priority_then_confidence",
                       "alternative_observation_ids": sorted(row["observation_id"] for row in candidates if row is not chosen),
                       "averaged": False})
    return output
