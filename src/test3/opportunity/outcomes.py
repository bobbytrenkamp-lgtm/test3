"""Local, approval-gated realized acquisition outcome intake.

This module closes the research feedback loop without pretending that an
uploaded spreadsheet is verified evidence. Candidate bytes are inventoried,
review is exception-first, a human attestation is hash-bound to those exact
bytes, and approval creates a new immutable CSV plus evidence sidecar. Nothing
here trains or promotes a score.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re

from .scoring import REQUIRED_OUTCOME_FIELDS, score_dataset_readiness

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 100_000
REVIEW_SCHEMA = "test3-opportunity-outcome-review/1.0.0"
ATTESTATION_SCHEMA = "test3-opportunity-outcome-attestation/1.0.0"
APPROVED_SCHEMA = "test3-opportunity-outcome-approved/1.0.0"

CANDIDATE_FIELDS = (
    "observation_id", "property_id", "market_id", "period", "property_type",
    "forecast_origin", "feature_available_at", "outcome_realized_at",
    "outcome_released_at", "outcome", "outcome_value", "data_status",
    "source_hash", "feature_hash", "source_name", "source_record_id",
    "licensing_notes", "methodology",
)
APPROVED_FIELDS = CANDIDATE_FIELDS + ("analyst_verified", "rights_documented", "attestation_hash")
ACKNOWLEDGEMENTS = (
    "source_evidence_reviewed", "methodology_reviewed", "rights_confirmed",
    "outcomes_are_realized_not_forecast", "no_synthetic_or_interpolated_outcomes",
    "warning_findings_reviewed",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_candidates(path: str | Path) -> tuple[Path, list[dict]]:
    source = Path(path).resolve()
    if not source.is_file() or source.suffix.lower() != ".csv":
        raise ValueError("realized-outcome input must be an existing CSV")
    if source.stat().st_size > MAX_BYTES:
        raise ValueError(f"realized-outcome input exceeds {MAX_BYTES:,} bytes")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = tuple(reader.fieldnames or ())
        missing = sorted(set(CANDIDATE_FIELDS) - set(fields))
        if missing:
            raise ValueError(f"realized-outcome input is missing columns: {missing}")
        rows = []
        for row_number, row in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise ValueError(f"realized-outcome input exceeds {MAX_ROWS:,} rows")
            normalized = {field: str(row.get(field) or "").strip() for field in CANDIDATE_FIELDS}
            normalized["_row_number"] = row_number
            rows.append(normalized)
    if not rows:
        raise ValueError("realized-outcome input is empty")
    return source, rows


def _candidate_findings(rows: list[dict], *, as_of: date) -> list[dict]:
    findings = []
    observation_ids: dict[str, list[int]] = {}
    logical_ids: dict[tuple[str, str, str], list[int]] = {}
    for row in rows:
        number = row["_row_number"]
        missing = [field for field in CANDIDATE_FIELDS if not row[field]]
        if missing:
            findings.append({"severity": "blocking", "code": "missing_required_value",
                             "row": number, "details": missing})
            continue
        observation_ids.setdefault(row["observation_id"], []).append(number)
        logical_ids.setdefault((row["property_id"], row["forecast_origin"], row["outcome"]), []).append(number)
        try:
            origin = date.fromisoformat(row["forecast_origin"])
            feature = date.fromisoformat(row["feature_available_at"])
            realized = date.fromisoformat(row["outcome_realized_at"])
            released = date.fromisoformat(row["outcome_released_at"])
            value = float(row["outcome_value"])
        except ValueError:
            findings.append({"severity": "blocking", "code": "date_or_value_invalid", "row": number})
            continue
        if feature > origin:
            findings.append({"severity": "blocking", "code": "future_feature_leakage", "row": number})
        if realized <= origin or released < realized:
            findings.append({"severity": "blocking", "code": "outcome_timing_invalid", "row": number})
        if released > as_of:
            findings.append({"severity": "blocking", "code": "outcome_not_released_as_of_review", "row": number})
        if not -10 <= value <= 10:
            findings.append({"severity": "warning", "code": "extreme_outcome_value", "row": number,
                             "value": row["outcome_value"]})
        if row["data_status"] != "real":
            findings.append({"severity": "blocking", "code": "non_real_data", "row": number})
        if not re.fullmatch(r"[0-9a-fA-F]{64}", row["source_hash"]) or not re.fullmatch(r"[0-9a-fA-F]{64}", row["feature_hash"]):
            findings.append({"severity": "blocking", "code": "lineage_hash_invalid", "row": number})
        if not re.fullmatch(r"\d{4}-(?:Q[1-4]|\d{2})", row["period"]):
            findings.append({"severity": "blocking", "code": "period_invalid", "row": number})
    for code, groups in (("duplicate_observation_id", observation_ids),
                         ("duplicate_property_origin_outcome", logical_ids)):
        for identity, row_numbers in groups.items():
            if len(row_numbers) > 1:
                findings.append({"severity": "blocking", "code": code, "rows": row_numbers,
                                 "identity": identity})
    return findings


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def prepare_outcome_review(input_path: str | Path, output_path: str | Path,
                           *, as_of: date | None = None) -> dict:
    source, rows = _read_candidates(input_path)
    output = Path(output_path).resolve()
    if output.exists():
        raise FileExistsError("realized-outcome review packets are immutable")
    evaluation_date = as_of or date.today()
    findings = _candidate_findings(rows, as_of=evaluation_date)
    dataset_hash = _sha(source)
    payload = {
        "schema_version": REVIEW_SCHEMA,
        "authoritative": False,
        "status": "AWAITING_ANALYST_ATTESTATION",
        "input_file": source.name,
        "input_sha256": dataset_hash,
        "evaluated_as_of": evaluation_date.isoformat(),
        "summary": {
            "observations": len(rows),
            "properties": len({row["property_id"] for row in rows}),
            "markets": len({row["market_id"] for row in rows}),
            "periods": len({row["period"] for row in rows}),
            "outcomes": sorted({row["outcome"] for row in rows}),
            "sources": sorted({row["source_name"] for row in rows}),
            "blocking_findings": sum(item["severity"] == "blocking" for item in findings),
            "warnings": sum(item["severity"] == "warning" for item in findings),
        },
        "findings": findings,
        "deterministic_spot_check": [
            {key: row[key] for key in ("observation_id", "property_id", "market_id", "period", "outcome", "outcome_value", "source_record_id")}
            for row in sorted(rows, key=lambda item: hashlib.sha256((dataset_hash + item["observation_id"]).encode()).hexdigest())[:20]
        ],
        "attestation_template": {
            "schema_version": ATTESTATION_SCHEMA,
            "input_sha256": dataset_hash,
            "evaluated_as_of": evaluation_date.isoformat(),
            "analyst_identity": "", "signed_at": "", "rationale": "",
            "approved_outcomes": [],
            "acknowledgements": {name: False for name in ACKNOWLEDGEMENTS},
        },
    }
    _atomic_json(output, payload)
    return {"review_packet": str(output), "input_sha256": dataset_hash, **payload["summary"],
            "status": payload["status"]}


def _attestation(path: Path, expected_hash: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != ATTESTATION_SCHEMA:
        raise ValueError("unsupported realized-outcome attestation schema")
    if str(payload.get("input_sha256", "")).removeprefix("sha256:") != expected_hash:
        raise ValueError("attestation is bound to different candidate bytes")
    for field in ("analyst_identity", "signed_at", "rationale", "approved_outcomes", "evaluated_as_of"):
        if payload.get(field) in (None, "", []):
            raise ValueError(f"analyst attestation requires {field}")
    if len(str(payload["rationale"]).strip()) < 20:
        raise ValueError("analyst rationale must contain at least 20 characters")
    signed = datetime.fromisoformat(str(payload["signed_at"]).replace("Z", "+00:00"))
    if signed.tzinfo is None:
        raise ValueError("analyst signed_at must include a timezone")
    date.fromisoformat(str(payload["evaluated_as_of"]))
    missing = [name for name in ACKNOWLEDGEMENTS if (payload.get("acknowledgements") or {}).get(name) is not True]
    if missing:
        raise ValueError(f"analyst attestation acknowledgements are incomplete: {missing}")
    return payload


def approve_outcome_review(input_path: str | Path, attestation_path: str | Path,
                           output_path: str | Path, *, as_of: date | None = None) -> dict:
    source, rows = _read_candidates(input_path)
    attestation_file, output = Path(attestation_path).resolve(), Path(output_path).resolve()
    sidecar = output.with_suffix(output.suffix + ".attestation.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError("approved realized-outcome datasets are immutable")
    if not attestation_file.is_file():
        raise ValueError("completed analyst attestation does not exist")
    dataset_hash = _sha(source)
    attestation = _attestation(attestation_file, dataset_hash)
    review_as_of = date.fromisoformat(attestation["evaluated_as_of"])
    if as_of is not None and as_of != review_as_of:
        raise ValueError("approval as-of date differs from the attested review vintage")
    approved_outcomes = set(attestation["approved_outcomes"])
    selected = [row for row in rows if row["outcome"] in approved_outcomes]
    if not selected or approved_outcomes - {row["outcome"] for row in selected}:
        raise ValueError("attestation selects unknown or empty outcome scope")
    findings = _candidate_findings(selected, as_of=review_as_of)
    blockers = [item for item in findings if item["severity"] == "blocking"]
    if blockers:
        raise ValueError(f"selected outcome rows have blocking findings: {sorted({item['code'] for item in blockers})}")
    attestation_hash = hashlib.sha256(json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=APPROVED_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in selected:
            writer.writerow({**{field: row[field] for field in CANDIDATE_FIELDS},
                             "analyst_verified": "true", "rights_documented": "true",
                             "attestation_hash": attestation_hash})
    os.replace(temporary, output)
    output_hash = _sha(output)
    _atomic_json(sidecar, {
        "schema_version": APPROVED_SCHEMA, "input_sha256": dataset_hash,
        "output_sha256": output_hash, "attestation_sha256": attestation_hash,
        "attestation": attestation, "observations": len(selected),
    })
    return {"output": str(output), "output_sha256": output_hash, "attestation_sidecar": str(sidecar),
            "attestation_sha256": attestation_hash, "observations": len(selected),
            "outcomes": sorted(approved_outcomes)}


def approved_outcome_readiness(input_path: str | Path, *, as_of: date | None = None) -> dict:
    source = Path(input_path).resolve()
    sidecar = source.with_suffix(source.suffix + ".attestation.json")
    if not source.is_file() or not sidecar.is_file():
        raise ValueError("approved outcome CSV and its attestation sidecar are required")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    attestation = metadata.get("attestation")
    calculated_attestation_hash = (hashlib.sha256(json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                                   if isinstance(attestation, dict) else None)
    if (metadata.get("schema_version") != APPROVED_SCHEMA or metadata.get("output_sha256") != _sha(source)
            or metadata.get("attestation_sha256") != calculated_attestation_hash):
        raise ValueError("approved outcome dataset integrity check failed")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = []
        for row in csv.DictReader(stream):
            item = dict(row)
            item["analyst_verified"] = item.get("analyst_verified", "").lower() == "true"
            item["rights_documented"] = item.get("rights_documented", "").lower() == "true"
            if item.get("attestation_hash") != calculated_attestation_hash:
                raise ValueError("approved outcome row is detached from its attestation")
            rows.append(item)
    return score_dataset_readiness(rows, evaluation_date=as_of)
