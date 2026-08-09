from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from test3.warehouse.storage import WarehousePaths


EVIDENCE_FIELDS = ("document_sha256", "page", "table", "row", "column", "original_label", "original_value")


def save_document_candidates(paths: WarehousePaths, *, document_sha256: str, candidates: list[dict]) -> Path:
    if not document_sha256 or len(document_sha256.removeprefix("sha256:")) != 64:
        raise ValueError("document SHA-256 is required")
    checked = []
    for candidate in candidates:
        evidence = candidate.get("evidence") or {}
        missing = [field for field in EVIDENCE_FIELDS if evidence.get(field) in (None, "")]
        if missing or evidence.get("document_sha256", "").removeprefix("sha256:") != document_sha256.removeprefix("sha256:"):
            raise ValueError(f"candidate evidence is incomplete or detached: {missing}")
        if candidate.get("status", "candidate") != "candidate":
            raise ValueError("new document observations must remain candidate-only")
        checked.append({**candidate, "status": "candidate", "analyst_approved": False})
    payload = {"schema_version": "test3-cre-document-candidates/1.0.0",
               "created_at": datetime.now(timezone.utc).isoformat(), "document_sha256": document_sha256,
               "candidates": checked}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    directory = paths.contained(Path("raw") / "cre_document_candidates" / document_sha256.removeprefix("sha256:"))
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{digest}.json"
    if not destination.exists():
        destination.write_text(json.dumps({**payload, "candidate_package_sha256": digest}, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    return destination


def approve_document_candidates(path: str | Path, *, approved_indexes: tuple[int, ...], analyst_rationale: str) -> list[dict]:
    if not analyst_rationale.strip():
        raise ValueError("analyst rationale is required")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    package_hash = payload.pop("candidate_package_sha256", None)
    actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if package_hash != actual:
        raise ValueError("candidate package integrity failure")
    candidates = payload.get("candidates", [])
    if any(index < 0 or index >= len(candidates) for index in approved_indexes):
        raise ValueError("approved candidate index is out of range")
    approved = []
    for index in approved_indexes:
        item = candidates[index]
        normalized = dict(item.get("observation") or {})
        normalized["verification_status"] = "analyst_verified"
        evidence = item["evidence"]
        original_identifier = normalized.get("source_identifier")
        normalized["source_identifier"] = (
            f"document:sha256:{payload['document_sha256'].removeprefix('sha256:')}#page={evidence['page']};table={evidence['table']};"
            f"row={evidence['row']};column={evidence['column']}")
        normalized["notes"] = " | ".join(filter(None, [normalized.get("notes"), f"Analyst rationale: {analyst_rationale}",
                                                        f"Original source identifier: {original_identifier}" if original_identifier else None,
                                                        f"Original: {evidence['original_label']}={evidence['original_value']}"]))
        approved.append(normalized)
    return approved
