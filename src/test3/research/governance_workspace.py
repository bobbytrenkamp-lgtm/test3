from __future__ import annotations

import json
from pathlib import Path

from test3.cre_data.maa_governance import MAA_REVIEW_PACKET_SCHEMA, inspect_maa_review_packet
from test3.cre_data.maa_markets import MARKET_CANDIDATE_SCHEMA, inspect_market_definition_candidates
from test3.warehouse.storage import WarehousePaths


MAX_ARTIFACTS = 500
MAX_JSON_BYTES = 10_000_000


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def approval_workspace(paths: WarehousePaths) -> dict:
    """Inventory local human-governance artifacts without granting or implying approval."""
    data_root = paths.root.parent.resolve()
    reports_root = (data_root / "cre_reports").resolve()
    if reports_root != data_root and data_root not in reports_root.parents:
        raise ValueError("CRE report directory escapes the configured data root")
    review_packets, market_candidates, errors = [], [], []
    if reports_root.is_dir():
        candidates = sorted(path for path in reports_root.rglob("*.json")
                            if path.is_file() and not path.is_symlink())[:MAX_ARTIFACTS]
        for path in candidates:
            if path.stat().st_size > MAX_JSON_BYTES:
                continue
            try:
                header = json.loads(path.read_text(encoding="utf-8"))
                schema = header.get("schema_version")
                if schema == MAA_REVIEW_PACKET_SCHEMA:
                    review_packets.append({"path": _relative(path, data_root), **inspect_maa_review_packet(path)})
                elif schema == MARKET_CANDIDATE_SCHEMA:
                    market_candidates.append({"path": _relative(path, data_root), **inspect_market_definition_candidates(path)})
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append({"path": _relative(path, data_root), "error": str(exc)})
    review_packets.sort(key=lambda item: (item.get("source") or "", item["path"]))
    market_candidates.sort(key=lambda item: item["path"])
    action_queue = []
    for packet in review_packets:
        action_queue.append({
            "gate": f"{packet.get('source') or 'CRE source'} target review",
            "status": "AWAITING_ANALYST_ATTESTATION",
            "action": "Review warnings and deterministic spot checks, then complete the blank hash-bound attestation.",
            "artifact": packet["path"], "human_action_required": True,
        })
    for candidate in market_candidates:
        status = "AWAITING_MARKET_EVIDENCE" if candidate["unresolved"] else "AWAITING_MARKET_DEFINITION_APPROVAL"
        action = ("Supply source-backed property/county evidence before review; unresolved definitions cannot be approved."
                  if candidate["unresolved"] else
                  "Review county weights, evidence, effective dates, and complete the blank market attestation.")
        action_queue.append({"gate": "Market definitions", "status": status, "action": action,
                             "artifact": candidate["path"], "human_action_required": True})
    return {
        "status": "HUMAN_GOVERNANCE_ACTION_REQUIRED" if action_queue else "NO_LOCAL_REVIEW_ARTIFACTS",
        "authoritative": False, "review_packets": review_packets, "market_definition_candidates": market_candidates,
        "action_queue": action_queue, "artifact_errors": errors,
        "safety": {
            "can_approve": False, "auto_fills_identity": False, "auto_fills_signature": False,
            "candidate_market_definitions_are_feature_eligible": False,
        },
    }
