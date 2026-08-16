"""Canonical, lossless persistence contract for Opportunity Finder evidence."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Mapping

from .screening import DIMENSIONS, OpportunityScreeningInput


CANDIDATE_EVIDENCE_SCHEMA_VERSION = "test3-opportunity-candidate-evidence/1.0.0"
PROPERTY_TYPES = frozenset({"multifamily", "industrial", "office", "retail", "student_housing",
                            "self_storage", "hotel", "data_center", "other"})
CANDIDATE_STATUSES = frozenset({"candidate", "promoted_to_diligence", "archived"})
ORIGIN_TYPES = frozenset({"manual", "authorized_csv", "existing_deal", "test1_handoff"})

DECIMAL_FIELDS = frozenset({"subject_rent", "market_rent", "acquisition_basis", "comparable_sale_basis",
                            "current_noi", "stabilized_noi", "subject_cap_rate", "market_cap_rate",
                            "subject_vacancy", "market_vacancy"})
INTEGER_FIELDS = frozenset({"rent_comp_count", "sale_comp_count"})
BOOLEAN_FIELDS = frozenset({"location_evidence_complete", "renovation_budget_verified"})
DATE_FIELDS = frozenset({"insurance_evidence_date"})
STRING_FIELDS = frozenset({"rent_unit", "basis_unit"})
VERSION_FIELDS = DECIMAL_FIELDS | INTEGER_FIELDS | BOOLEAN_FIELDS | DATE_FIELDS | STRING_FIELDS | {
    "analysis_as_of", "evidence_hashes", "evidence_dates"
}
FORBIDDEN_RESULT_FIELDS = frozenset({"screening_tier", "screeningTier", "reasons", "warnings",
                                     "derived_metrics", "derivedMetrics", "result", "result_hash"})


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def normalized_address_hash(address: object) -> str | None:
    text = re.sub(r"[.,]", "", str(address or "").strip().casefold())
    suffixes = {"street": "st", "road": "rd", "avenue": "ave", "boulevard": "blvd", "drive": "dr",
                "lane": "ln", "court": "ct", "highway": "hwy", "parkway": "pkwy"}
    normalized = " ".join(suffixes.get(token, token) for token in text.split())
    return hashlib.sha256(normalized.encode()).hexdigest() if normalized else None


def _decimal_text(value: object, field: str) -> str:
    if isinstance(value, (float, bool)):
        raise ValueError(f"{field} must be supplied as a decimal string or integer, never a JSON float")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative decimal")
    if field in {"subject_cap_rate", "market_cap_rate", "subject_vacancy", "market_vacancy"} and parsed > 1:
        raise ValueError(f"{field} must be a decimal fraction no greater than 1")
    return format(parsed, "f")


def _date_text(value: object, field: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def normalize_evidence_payload(candidate_id: str, property_type: str, payload: Mapping[str, object]) -> dict:
    """Reject derived/client-controlled results and return a stable lossless snapshot."""
    if not isinstance(payload, Mapping):
        raise ValueError("Candidate evidence must be a JSON object")
    forbidden = set(payload).intersection(FORBIDDEN_RESULT_FIELDS)
    if forbidden:
        raise ValueError("Screening results are server-derived and cannot be supplied by clients")
    unknown = set(payload) - VERSION_FIELDS
    if unknown:
        raise ValueError("Unsupported candidate evidence fields: " + ", ".join(sorted(unknown)))
    if "analysis_as_of" not in payload:
        raise ValueError("analysis_as_of is required")
    analysis_as_of = date.fromisoformat(_date_text(payload["analysis_as_of"], "analysis_as_of"))
    if analysis_as_of > datetime.now(timezone.utc).date():
        raise ValueError("analysis_as_of cannot be after the current UTC date")
    normalized: dict[str, object] = {"analysis_as_of": analysis_as_of.isoformat()}
    for field in sorted(DECIMAL_FIELDS):
        if field in payload and payload[field] is not None:
            normalized[field] = _decimal_text(payload[field], field)
    for field in sorted(INTEGER_FIELDS):
        if field in payload and payload[field] is not None:
            value = payload[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
            normalized[field] = value
    for field in sorted(BOOLEAN_FIELDS):
        if field in payload and payload[field] is not None:
            if not isinstance(payload[field], bool):
                raise ValueError(f"{field} must be a boolean")
            normalized[field] = payload[field]
    for field in sorted(STRING_FIELDS):
        if field in payload and payload[field] is not None:
            value = str(payload[field]).strip()
            if not value or len(value) > 100:
                raise ValueError(f"{field} must be a non-empty string of at most 100 characters")
            normalized[field] = value
    for field in sorted(DATE_FIELDS):
        if field in payload and payload[field] is not None:
            parsed = date.fromisoformat(_date_text(payload[field], field))
            if parsed > analysis_as_of:
                raise ValueError(f"{field} cannot be after analysis_as_of")
            normalized[field] = parsed.isoformat()
    for field in ("evidence_hashes", "evidence_dates"):
        raw = payload.get(field, {})
        if not isinstance(raw, Mapping) or set(raw) - set(DIMENSIONS):
            raise ValueError(f"{field} must contain only governed evidence dimensions")
        if field == "evidence_hashes":
            converted = {}
            for dimension, hashes in raw.items():
                if not isinstance(hashes, list) or len(hashes) > 100:
                    raise ValueError("Evidence hashes must be bounded arrays")
                values = sorted({str(item).lower() for item in hashes})
                if any(len(item) != 64 or any(c not in "0123456789abcdef" for c in item) for item in values):
                    raise ValueError(f"{dimension} evidence contains an invalid SHA-256")
                converted[str(dimension)] = values
        else:
            converted = {}
            for dimension, value in raw.items():
                parsed = date.fromisoformat(_date_text(value, f"evidence_dates.{dimension}"))
                if parsed > analysis_as_of:
                    raise ValueError(f"evidence_dates.{dimension} cannot be after analysis_as_of")
                converted[str(dimension)] = parsed.isoformat()
        normalized[field] = converted
    return {"schemaVersion": CANDIDATE_EVIDENCE_SCHEMA_VERSION, "candidateId": candidate_id,
            "propertyType": property_type, "inputs": normalized}


def screening_input_from_snapshot(snapshot: Mapping[str, object]) -> OpportunityScreeningInput:
    inputs = dict(snapshot.get("inputs") or {})
    kwargs: dict[str, object] = {
        "candidate_id": str(snapshot["candidateId"]),
        "property_type": str(snapshot["propertyType"]),
        "analysis_as_of": date.fromisoformat(str(inputs.pop("analysis_as_of"))),
    }
    for field in DECIMAL_FIELDS:
        if field in inputs:
            kwargs[field] = Decimal(str(inputs[field]))
    for field in INTEGER_FIELDS | BOOLEAN_FIELDS | STRING_FIELDS:
        if field in inputs:
            kwargs[field] = inputs[field]
    for field in DATE_FIELDS:
        if field in inputs:
            kwargs[field] = date.fromisoformat(str(inputs[field]))
    kwargs["evidence_hashes"] = dict(inputs.get("evidence_hashes") or {})
    kwargs["evidence_dates"] = {key: date.fromisoformat(str(value))
                                for key, value in dict(inputs.get("evidence_dates") or {}).items()}
    return OpportunityScreeningInput(**kwargs)
