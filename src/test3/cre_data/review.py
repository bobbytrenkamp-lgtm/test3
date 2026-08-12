from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from .schema import parse_cre_file


ATTESTATION_SCHEMA = "test3-cre-analyst-attestation/1.0.0"
REQUIRED_ACKNOWLEDGEMENTS = (
    "source_evidence_reviewed",
    "methodology_compatible",
    "market_definitions_reviewed",
    "rights_confirmed",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_attestation(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != ATTESTATION_SCHEMA:
        raise ValueError("unsupported CRE analyst-attestation schema")
    for field in ("analyst_identity", "signed_at", "rationale", "input_sha256",
                  "approved_markets", "approved_metrics", "period_from", "period_to"):
        if payload.get(field) in (None, "", []):
            raise ValueError(f"analyst attestation requires {field}")
    if len(str(payload["rationale"]).strip()) < 20:
        raise ValueError("analyst rationale must contain at least 20 characters")
    signed_at = datetime.fromisoformat(str(payload["signed_at"]).replace("Z", "+00:00"))
    if signed_at.tzinfo is None:
        raise ValueError("analyst signed_at must include a timezone")
    acknowledgements = payload.get("acknowledgements") or {}
    missing = [name for name in REQUIRED_ACKNOWLEDGEMENTS if acknowledgements.get(name) is not True]
    if missing:
        raise ValueError(f"analyst attestation acknowledgements are incomplete: {missing}")
    if len(payload["approved_markets"]) != len(set(payload["approved_markets"])):
        raise ValueError("approved_markets must be unique")
    if len(payload["approved_metrics"]) != len(set(payload["approved_metrics"])):
        raise ValueError("approved_metrics must be unique")
    return payload


def approve_cre_review(input_path: str | Path, attestation_path: str | Path,
                       output_path: str | Path) -> dict:
    """Create a new review-scoped CSV; never mutate or self-approve source evidence."""
    source, attestation_file, output = Path(input_path), Path(attestation_path), Path(output_path)
    sidecar = output.with_suffix(output.suffix + ".attestation.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError("approved CRE review outputs are immutable")
    if not source.is_file() or not attestation_file.is_file():
        raise ValueError("review input and attestation files must exist")
    if source.suffix.lower() != ".csv" or output.suffix.lower() != ".csv":
        raise ValueError("analyst review approval requires CSV input and output")
    attestation = _load_attestation(attestation_file)
    input_hash = _sha256(source)
    if attestation["input_sha256"].removeprefix("sha256:") != input_hash:
        raise ValueError("analyst attestation is bound to a different review file")
    parsed, errors, _ = parse_cre_file(source.read_bytes(), suffix=source.suffix)
    if errors:
        raise ValueError("review input contains structurally invalid observations")
    markets, metrics = set(attestation["approved_markets"]), set(attestation["approved_metrics"])
    period_from, period_to = str(attestation["period_from"]), str(attestation["period_to"])
    selected = [row for row in parsed if row["geography_id"] in markets and row["metric"] in metrics
                and period_from <= row["period"] <= period_to]
    if not selected:
        raise ValueError("analyst attestation selects no observations")
    observed_markets = {row["geography_id"] for row in selected}
    missing_markets = markets - observed_markets
    if missing_markets:
        raise ValueError(f"attestation selects unknown or empty markets: {sorted(missing_markets)}")
    missing_metrics = metrics - {row["metric"] for row in selected}
    if missing_metrics:
        raise ValueError(f"attestation selects unknown or empty metrics: {sorted(missing_metrics)}")
    if any(row["verification_status"] == "rejected" for row in selected):
        raise ValueError("rejected observations cannot be analyst-approved")
    attestation_hash = hashlib.sha256(json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open(encoding="utf-8-sig", newline="") as source_handle:
        fieldnames = list(csv.DictReader(source_handle).fieldnames or ())
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in selected:
            notes = " | ".join(filter(None, (row.get("notes"),
                f"Analyst={attestation['analyst_identity']}", f"Attestation=sha256:{attestation_hash}",
                f"Rationale={attestation['rationale']}")))
            writer.writerow({**row, "verification_status": "analyst_verified", "notes": notes})
    os.replace(temporary, output)
    output_hash = _sha256(output)
    sidecar_payload = json.dumps({
        "schema_version": "test3-cre-approved-review/1.0.0",
        "input_path": source.name,
        "input_sha256": input_hash,
        "output_path": output.name,
        "output_sha256": output_hash,
        "attestation_sha256": attestation_hash,
        "attestation": attestation,
        "observations": len(selected),
        "markets": len(observed_markets),
        "periods": len({row["period"] for row in selected}),
        "metrics": sorted({row["metric"] for row in selected}),
    }, indent=2, sort_keys=True) + "\n"
    temporary_sidecar = sidecar.with_suffix(sidecar.suffix + ".tmp")
    temporary_sidecar.write_text(sidecar_payload, encoding="utf-8")
    os.replace(temporary_sidecar, sidecar)
    return {"output": str(output), "output_sha256": output_hash,
            "attestation_sidecar": str(sidecar), "attestation_sha256": attestation_hash,
            "observations": len(selected), "markets": len(observed_markets),
            "periods": len({row["period"] for row in selected}),
            "metrics": sorted({row["metric"] for row in selected})}
