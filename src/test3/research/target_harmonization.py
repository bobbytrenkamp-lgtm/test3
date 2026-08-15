from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from test3.cre_data.sources.sec_avb import methodology_comparison_artifact
from test3.warehouse.storage import WarehousePaths


PACKET_SCHEMA = "test3-cross-source-target-harmonization-review/1.0.0"
ATTESTATION_SCHEMA = "test3-cross-source-target-harmonization-attestation/1.0.0"
APPROVED_SCHEMA = "test3-cross-source-target-harmonization/1.0.0"
HARMONIZATION_ID = "maa-avb-multifamily-pricing-growth"
ACKNOWLEDGEMENTS = (
    "source_methodologies_reviewed",
    "metrics_are_not_identical",
    "issuer_portfolios_are_not_metro_markets",
    "source_effect_or_separate_models_required",
    "no_automatic_source_averaging",
    "cross_source_results_are_predictive_not_causal",
)


def _hash(payload: dict, hash_field: str = "artifact_hash") -> str:
    body = {key: value for key, value in payload.items() if key != hash_field}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _candidate_mappings() -> dict:
    return {
        "MAA": {
            "source_metric": "rent_growth_yoy",
            "methodology_version": "same_store_yoy",
            "semantic_definition": "MAA-reported same-store effective-rent year-over-year growth",
            "compatibility": "review_required",
        },
        "AVB": {
            "source_metric": "average_monthly_revenue_growth_yoy",
            "methodology_version": "same_store_revenue_per_occupied_home_yoy",
            "semantic_definition": "AVB-reported same-store residential revenue per occupied home year-over-year growth",
            "compatibility": "review_required",
        },
    }


def prepare_target_harmonization_review(output_path: str | Path) -> dict:
    """Create a blank, hash-bound human review packet; this never grants approval."""
    output = Path(output_path)
    if output.exists():
        raise FileExistsError("target harmonization review packets are immutable")
    comparison = methodology_comparison_artifact()
    payload = {
        "schema_version": PACKET_SCHEMA,
        "harmonization_id": HARMONIZATION_ID,
        "review_status": "candidate_review_required",
        "canonical_research_target": "issuer_same_store_residential_pricing_growth_yoy",
        "controlling_market_rent_target": False,
        "source_mappings": _candidate_mappings(),
        "methodology_comparison_hash": comparison["artifact_hash"],
        "required_controls": {
            "source_effect_or_separate_models": True,
            "separate_source_performance": True,
            "no_automatic_averaging": True,
            "portfolio_market_geography_retained": True,
        },
        "limitations": [
            "MAA effective-rent growth and AVB revenue-per-occupied-home growth are not identical measures.",
            "Both sources describe issuer same-store portfolios, not entire institutional metro markets.",
            "Approval permits controlled external-validity research; it does not prove interchangeability or causality.",
        ],
        "attestation_template": {
            "schema_version": ATTESTATION_SCHEMA,
            "review_packet_hash": "",
            "analyst_identity": "",
            "analyst_signature": "",
            "signed_at": "",
            "rationale": "",
            "decision": "",
            "source_mapping_decisions": {
                source: {"decision": "", "rationale": ""} for source in _candidate_mappings()
            },
            "acknowledgements": {name: False for name in ACKNOWLEDGEMENTS},
        },
    }
    # The blank convenience template is excluded to avoid recursive self-binding.
    review_body = {key: value for key, value in payload.items() if key not in {"artifact_hash", "attestation_template"}}
    payload["artifact_hash"] = hashlib.sha256(
        json.dumps(review_body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    payload["attestation_template"]["review_packet_hash"] = payload["artifact_hash"]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return {"status": "AWAITING_TARGET_HARMONIZATION_ATTESTATION", "review_packet": str(output),
            "artifact_hash": payload["artifact_hash"], "sources": sorted(payload["source_mappings"])}


def _packet_hash(payload: dict) -> str:
    body = {key: value for key, value in payload.items() if key not in {"artifact_hash", "attestation_template"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def approve_target_harmonization(paths: WarehousePaths, packet_path: str | Path,
                                 attestation_path: str | Path) -> dict:
    """Persist a human-approved semantic bridge without claiming metric identity."""
    packet_file, attestation_file = Path(packet_path), Path(attestation_path)
    if not packet_file.is_file() or not attestation_file.is_file():
        raise ValueError("review packet and completed attestation must exist")
    packet = json.loads(packet_file.read_text(encoding="utf-8"))
    if packet.get("schema_version") != PACKET_SCHEMA or packet.get("artifact_hash") != _packet_hash(packet):
        raise ValueError("target harmonization review packet integrity failure")
    attestation = json.loads(attestation_file.read_text(encoding="utf-8"))
    if attestation.get("schema_version") != ATTESTATION_SCHEMA:
        raise ValueError("unsupported target harmonization attestation schema")
    for field in ("review_packet_hash", "analyst_identity", "analyst_signature", "signed_at", "rationale", "decision"):
        if not str(attestation.get(field) or "").strip():
            raise ValueError(f"target harmonization attestation requires {field}")
    if attestation["review_packet_hash"] != packet["artifact_hash"]:
        raise ValueError("target harmonization attestation is not hash-bound to this review packet")
    signed_at = datetime.fromisoformat(str(attestation["signed_at"]).replace("Z", "+00:00"))
    if signed_at.tzinfo is None:
        raise ValueError("target harmonization signed_at must include a timezone")
    if len(str(attestation["rationale"]).strip()) < 30:
        raise ValueError("target harmonization rationale must contain at least 30 characters")
    if attestation["decision"] != "approve_with_controls":
        raise ValueError("target harmonization requires explicit approve_with_controls")
    missing_ack = [name for name in ACKNOWLEDGEMENTS
                   if (attestation.get("acknowledgements") or {}).get(name) is not True]
    if missing_ack:
        raise ValueError(f"target harmonization acknowledgements are incomplete: {missing_ack}")
    decisions = attestation.get("source_mapping_decisions") or {}
    if set(decisions) != set(packet["source_mappings"]):
        raise ValueError("every source mapping requires one analyst decision")
    for source, decision in decisions.items():
        if decision.get("decision") != "approve_with_controls" or len(str(decision.get("rationale") or "").strip()) < 20:
            raise ValueError(f"source mapping {source} requires approve_with_controls and a rationale")
    attestation_hash = hashlib.sha256(
        json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    mappings = {source: {**mapping, "compatibility": "approved_with_controls"}
                for source, mapping in packet["source_mappings"].items()}
    artifact = {
        "schema_version": APPROVED_SCHEMA,
        "harmonization_id": packet["harmonization_id"],
        "version": "1.0.0",
        "target": packet["canonical_research_target"],
        "review_status": "analyst_approved",
        "controlling_market_rent_target": False,
        "source_mappings": mappings,
        "required_controls": packet["required_controls"],
        "limitations": packet["limitations"],
        "review_packet_hash": packet["artifact_hash"],
        "analyst_attestation_hash": attestation_hash,
        "approved_by": attestation["analyst_identity"],
        "analyst_rationale": attestation["rationale"],
        "approved_at": attestation["signed_at"],
    }
    artifact["artifact_hash"] = _hash(artifact)
    directory = paths.contained(Path("manifests") / "target_harmonization" / HARMONIZATION_ID)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{artifact['artifact_hash']}.json"
    if destination.exists():
        raise FileExistsError("approved target harmonization artifact is immutable")
    destination.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "APPROVED_TARGET_HARMONIZATION_CREATED", "path": str(destination),
            "artifact_hash": artifact["artifact_hash"], "analyst_attestation_hash": attestation_hash}


def approved_target_harmonizations(paths: WarehousePaths) -> list[dict]:
    root = paths.contained(Path("manifests") / "target_harmonization")
    output = []
    for path in sorted(root.glob("*/*.json")) if root.exists() else ():
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if artifact.get("schema_version") != APPROVED_SCHEMA or artifact.get("artifact_hash") != _hash(artifact):
            raise ValueError(f"target harmonization artifact integrity failure: {path}")
        output.append(artifact)
    return output


def target_harmonization_status(paths: WarehousePaths) -> dict:
    artifacts = approved_target_harmonizations(paths)
    matching = [item for item in artifacts if item.get("harmonization_id") == HARMONIZATION_ID]
    latest = max(matching, key=lambda item: item["approved_at"]) if matching else None
    return {"status": "APPROVED" if matching else "AWAITING_TARGET_HARMONIZATION_ATTESTATION",
            "harmonization_id": HARMONIZATION_ID, "approved_artifacts": len(matching),
            "latest_artifact_hash": latest["artifact_hash"] if latest else None,
            "latest_version": latest["version"] if latest else None}
