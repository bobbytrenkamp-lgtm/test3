from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from .schema import parse_cre_file
from .verification import MODEL_BLOCKING_FINDING_CODES, verify_observations


MAA_REVIEW_PACKET_SCHEMA = "test3-maa-rent-growth-review/1.0.0"
MAA_ATTESTATION_SCHEMA = "test3-maa-rent-growth-attestation/1.0.0"
WARNING_DECISIONS = frozenset({
    "accept", "reject_observation", "exclude_market_period", "exclude_metric_period", "request_further_review",
})
MAA_ACKNOWLEDGEMENTS = (
    "source_evidence_reviewed",
    "methodology_reviewed",
    "warning_findings_reviewed",
    "usage_rights_considered",
    "maa_market_is_not_entire_metro",
    "separate_market_definitions_required",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_hash(payload: dict) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _warning_id(finding: dict) -> str:
    identity = {"code": finding["code"], "message": finding["message"],
                "observation_ids": sorted(finding["observation_ids"])}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _evidence_document(reference: str) -> str:
    return reference.split("#", 1)[0]


def _deterministic_sample(rows: list[dict], warned_ids: set[str], dataset_hash: str,
                          sample_size: int = 24) -> list[dict]:
    clean = [row for row in rows if row["observation_id"] not in warned_ids]
    periods = sorted({row["period"] for row in clean})
    if not periods:
        return []
    cut1, cut2 = max(1, len(periods) // 3), max(2, (2 * len(periods)) // 3)
    buckets = (set(periods[:cut1]), set(periods[cut1:cut2]), set(periods[cut2:]))
    output = []
    per_bucket = max(1, sample_size // 3)
    for bucket in buckets:
        candidates = [row for row in clean if row["period"] in bucket]
        candidates.sort(key=lambda row: hashlib.sha256(
            f"{dataset_hash}|{row['observation_id']}".encode()).hexdigest())
        chosen, seen_markets, seen_metrics = [], set(), set()
        for row in candidates:
            if len(chosen) >= per_bucket:
                break
            if row["geography_id"] not in seen_markets or row["metric"] not in seen_metrics:
                chosen.append(row); seen_markets.add(row["geography_id"]); seen_metrics.add(row["metric"])
        for row in candidates:
            if len(chosen) >= per_bucket:
                break
            if row not in chosen:
                chosen.append(row)
        output.extend(chosen)
    return [{key: row.get(key) for key in (
        "observation_id", "geography_id", "market", "period", "metric", "value", "unit",
        "methodology", "source_identifier", "release_date",
    )} for row in output[:sample_size]]


def prepare_maa_rent_growth_review(input_path: str | Path, output_path: str | Path, *,
                                   approved_metric: str = "rent_growth_yoy",
                                   approved_source: str = "MAA SEC supplemental") -> dict:
    source, output = Path(input_path), Path(output_path)
    if not source.is_file() or source.suffix.lower() != ".csv":
        raise ValueError("MAA review preparation requires an existing CSV")
    if output.exists():
        raise FileExistsError("MAA review packets are immutable")
    rows, errors, metadata = parse_cre_file(source.read_bytes(), suffix=".csv")
    if errors or not rows:
        raise ValueError("MAA review input must contain only structurally valid observations")
    if {row["source_class"] for row in rows} != {"public_company_filing"}:
        raise ValueError("MAA review input must contain only public-company filing observations")
    verification = verify_observations(rows, analyst_review_confirmed=False)
    by_id = {row["observation_id"]: row for row in rows}
    findings = verification["findings"]
    warning_findings = [item for item in findings if item["severity"] == "warning"]
    blocking = [item for item in findings if item["code"] in MODEL_BLOCKING_FINDING_CODES]
    warned_ids = {identifier for item in warning_findings for identifier in item["observation_ids"]}
    warnings = []
    for finding in warning_findings:
        affected = [by_id[item] for item in finding["observation_ids"] if item in by_id]
        affected.sort(key=lambda row: row["period"])
        previous, current = (affected[-2], affected[-1]) if len(affected) >= 2 else (None, affected[-1])
        change = (format(Decimal(current["value"]) - Decimal(previous["value"]), "f")
                  if previous is not None else None)
        warnings.append({
            "warning_id": _warning_id(finding), "warning_code": finding["code"], "message": finding["message"],
            "market": current["geography_id"], "quarter": current["period"], "metric": current["metric"],
            "value": current["value"], "previous_value": previous["value"] if previous else None,
            "change": change, "source_filing": _evidence_document(current["source_identifier"]),
            "evidence_reference": current["source_identifier"], "observation_id": current["observation_id"],
            "affected_observation_ids": finding["observation_ids"], "analyst_decision": None,
        })
    periods = sorted({row["period"] for row in rows})
    metrics = sorted({row["metric"] for row in rows})
    markets = sorted({row["geography_id"] for row in rows})
    finding_counts = {code: sum(item["code"] == code for item in findings) for code in sorted({item["code"] for item in findings})}
    payload = {
        "schema_version": MAA_REVIEW_PACKET_SCHEMA,
        "authoritative": False,
        "candidate_file": source.name,
        "candidate_dataset_sha256": metadata["sha256"],
        "dataset_summary": {
            "target_source": sorted({row["source_name"] for row in rows}),
            "methodologies": sorted({row["methodology"] for row in rows}),
            "candidate_observations": len(rows), "markets": len(markets), "quarters": len(periods),
            "metrics": metrics, "source_filings": len({_evidence_document(row["source_identifier"]) for row in rows}),
            "earliest_period": periods[0], "latest_period": periods[-1], "market_ids": markets,
        },
        "immediate_scope": {
            "property_type": "multifamily", "source": approved_source,
            "metric": approved_metric, "candidate_observations": sum(row["metric"] == approved_metric for row in rows),
            "suggested_period_from": periods[0], "suggested_period_to": periods[-1],
        },
        "verification_summary": {
            "checks_run": ["structure", "units", "duplicates", "methodology", "release_dates", "period_gaps",
                           "sudden_jumps", "operating_identity", "NOI_margin"],
            "blocking_findings": len(blocking), "warnings": len(warning_findings),
            "duplicates": finding_counts.get("duplicate_observation", 0),
            "methodology_conflicts": finding_counts.get("methodology_change", 0) + finding_counts.get("methodology_mismatch", 0),
            "unit_conflicts": finding_counts.get("operating_unit_mismatch", 0),
            "release_date_issues": finding_counts.get("future_data_leakage", 0),
            "missing_period_issues": finding_counts.get("missing_periods", 0),
            "sudden_jump_warnings": finding_counts.get("sudden_jump", 0),
            "finding_counts": finding_counts,
        },
        "warnings": warnings,
        "clean_spot_check_sample": _deterministic_sample(rows, warned_ids, metadata["sha256"]),
        "attestation_template": {
            "schema_version": MAA_ATTESTATION_SCHEMA,
            "analyst_identity": "", "analyst_signature": "", "signed_at": "", "rationale": "",
            "review_completion_statement": "", "candidate_dataset_sha256": metadata["sha256"],
            "approved_dataset_sha256": "", "approved_property_type": "", "approved_source": "",
            "approved_metrics": [], "approved_markets": [], "period_from": "", "period_to": "",
            "warning_decisions": [{"warning_id": item["warning_id"], "decision": "", "rationale": ""}
                                  for item in warnings],
            "acknowledgements": {name: False for name in MAA_ACKNOWLEDGEMENTS},
        },
    }
    payload["artifact_sha256"] = _artifact_hash(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return {"review_packet": str(output), "artifact_sha256": payload["artifact_sha256"],
            "candidate_observations": len(rows), "rent_growth_candidates": payload["immediate_scope"]["candidate_observations"],
            "warnings": len(warnings), "blockers": len(blocking), "status": "AWAITING_ANALYST_ATTESTATION"}


def _load_packet(path: Path, schema: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != schema or payload.get("artifact_sha256") != _artifact_hash(payload):
        raise ValueError("review artifact schema or integrity check failed")
    return payload


def approve_maa_rent_growth_review(input_path: str | Path, packet_path: str | Path,
                                   attestation_path: str | Path, output_path: str | Path) -> dict:
    source, packet_file, attestation_file, output = map(Path, (input_path, packet_path, attestation_path, output_path))
    sidecar = output.with_suffix(output.suffix + ".attestation.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError("approved MAA datasets are immutable")
    if not all(path.is_file() for path in (source, packet_file, attestation_file)):
        raise ValueError("candidate, review packet, and completed attestation must exist")
    packet = _load_packet(packet_file, MAA_REVIEW_PACKET_SCHEMA)
    attestation = json.loads(attestation_file.read_text(encoding="utf-8"))
    if attestation.get("schema_version") != MAA_ATTESTATION_SCHEMA:
        raise ValueError("unsupported MAA analyst attestation schema")
    for field in ("analyst_identity", "analyst_signature", "signed_at", "rationale", "review_completion_statement",
                  "candidate_dataset_sha256", "approved_dataset_sha256", "approved_property_type", "approved_source",
                  "approved_metrics", "approved_markets", "period_from", "period_to"):
        if attestation.get(field) in (None, "", []):
            raise ValueError(f"MAA analyst attestation requires {field}")
    signed_at = datetime.fromisoformat(str(attestation["signed_at"]).replace("Z", "+00:00"))
    if signed_at.tzinfo is None:
        raise ValueError("analyst signed_at must include a timezone")
    if len(str(attestation["rationale"]).strip()) < 20:
        raise ValueError("analyst rationale must contain at least 20 characters")
    candidate_hash = _sha256(source)
    if not (candidate_hash == packet["candidate_dataset_sha256"] == attestation["candidate_dataset_sha256"]
            == attestation["approved_dataset_sha256"]):
        raise ValueError("analyst attestation is not hash-bound to this exact candidate dataset")
    expected_source, expected_metric = packet["immediate_scope"]["source"], packet["immediate_scope"]["metric"]
    if attestation["approved_property_type"] != "multifamily" or attestation["approved_source"] != expected_source:
        raise ValueError("institutional review has an invalid property-type or source scope")
    if set(attestation["approved_metrics"]) != {expected_metric}:
        raise ValueError(f"this review packet approves only {expected_metric}")
    acknowledgements = attestation.get("acknowledgements") or {}
    missing = [name for name in MAA_ACKNOWLEDGEMENTS if acknowledgements.get(name) is not True]
    if missing:
        raise ValueError(f"MAA attestation acknowledgements are incomplete: {missing}")
    expected_warnings = {item["warning_id"]: item for item in packet["warnings"]}
    decisions = attestation.get("warning_decisions") or []
    if len(decisions) != len(expected_warnings) or {item.get("warning_id") for item in decisions} != set(expected_warnings):
        raise ValueError("every packet warning requires exactly one analyst decision")
    for item in decisions:
        if item.get("decision") not in WARNING_DECISIONS or len(str(item.get("rationale") or "").strip()) < 10:
            raise ValueError("warning decisions require an allowed decision and rationale")
    rows, errors, _ = parse_cre_file(source.read_bytes(), suffix=".csv")
    if errors:
        raise ValueError("candidate dataset is structurally invalid")
    markets = set(attestation["approved_markets"])
    period_from, period_to = str(attestation["period_from"]), str(attestation["period_to"])
    selected = [row for row in rows if row["property_type"] == "multifamily" and row["metric"] == expected_metric
                and row["geography_id"] in markets and period_from <= row["period"] <= period_to]
    if not selected or markets - {row["geography_id"] for row in selected}:
        raise ValueError("attestation selects no observations or unknown markets")
    excluded_ids = set()
    for decision in decisions:
        warning = expected_warnings[decision["warning_id"]]
        action = decision["decision"]
        if action == "accept":
            continue
        affected = [row for row in rows if row["observation_id"] in warning["affected_observation_ids"]]
        if action in {"reject_observation", "request_further_review"}:
            excluded_ids.update(row["observation_id"] for row in affected)
        elif action == "exclude_market_period":
            excluded_ids.update(row["observation_id"] for row in rows
                                if row["geography_id"] == warning["market"] and row["period"] == warning["quarter"])
        elif action == "exclude_metric_period":
            excluded_ids.update(row["observation_id"] for row in rows
                                if row["metric"] == warning["metric"] and row["period"] == warning["quarter"])
    selected = [row for row in selected if row["observation_id"] not in excluded_ids]
    checked = verify_observations([{**row, "verification_status": "analyst_verified"} for row in selected],
                                  analyst_review_confirmed=True)
    blockers = sorted({item["code"] for item in checked["findings"] if item["code"] in MODEL_BLOCKING_FINDING_CODES})
    if blockers:
        raise ValueError(f"approved scope fails central verification: {blockers}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open(encoding="utf-8-sig", newline="") as handle:
        fieldnames = list(csv.DictReader(handle).fieldnames or ())
    temporary = output.with_suffix(output.suffix + ".tmp")
    attestation_hash = hashlib.sha256(json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in selected:
            writer.writerow({**row, "verification_status": "analyst_verified",
                             "notes": " | ".join(filter(None, (row.get("notes"), f"Attestation=sha256:{attestation_hash}")))})
    os.replace(temporary, output)
    sidecar_payload = {
        "schema_version": "test3-maa-approved-rent-growth/1.0.0", "candidate_dataset_sha256": candidate_hash,
        "review_packet_sha256": packet["artifact_sha256"], "attestation_sha256": attestation_hash,
        "approved_output_sha256": _sha256(output), "attestation": attestation,
        "approved_observations": len(selected), "approved_markets": len({row["geography_id"] for row in selected}),
        "approved_periods": len({row["period"] for row in selected}), "excluded_observation_ids": sorted(excluded_ids),
    }
    sidecar_payload["artifact_sha256"] = _artifact_hash(sidecar_payload)
    sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "APPROVED_IMMUTABLE_DATASET_CREATED", "output": str(output),
            "output_sha256": sidecar_payload["approved_output_sha256"], "attestation_sidecar": str(sidecar),
            "approved_observations": len(selected), "approved_markets": sidecar_payload["approved_markets"],
            "approved_periods": sidecar_payload["approved_periods"]}
