from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
REQUIRED = {"model_name","model_version","target_assumption","training_data_snapshot_hash","feature_schema_version","training_window","validation_window","property_types","geographic_coverage","sample_size","coefficients","standard_errors","model_metrics","residual_diagnostics","limitations","source_code_path","source_code_sha256","repository_commit_sha","r_version","data_status","model_card_path","validation_results_path","input_schema_path"}


def validate_promotion_evidence(artifact: dict) -> None:
    if artifact.get("data_status") == "fictional_synthetic" and artifact.get("validation_state") == "validated":
        raise ValueError("fictional synthetic artifacts can never be validated")
    if artifact.get("validation_state") != "validated":
        return
    metrics = artifact.get("model_metrics") or {}
    governance = metrics.get("governance") or {}
    forecast = metrics.get("forecast") or {}
    required_evidence = {
        "real data": artifact.get("data_status") == "real",
        "validated promotion gates": governance.get("status") == "validated" and governance.get("eligible_for_controlling_forecast") is True,
        "Python reference pass": metrics.get("python_reference_status") == "passed",
        "R reference status": metrics.get("r_cross_check_status") in {"passed", "not_available"},
        "source manifest hashes": bool(metrics.get("source_manifest_hashes")),
        "target dataset hashes": bool(metrics.get("target_dataset_hashes")),
        "feature table hash": bool(metrics.get("feature_table_hash")),
        "model result hash": bool(metrics.get("model_result_hash")),
        "candidate-only forecast": forecast.get("candidate_only") is True and forecast.get("analyst_approval_required") is True,
    }
    failed = [name for name, passed in required_evidence.items() if not passed]
    if failed:
        raise ValueError("validated model artifact is missing promotion evidence: " + ", ".join(failed))


def _portable_source_digest(content: bytes) -> str:
    """Hash source text canonically so Git's CRLF checkout policy cannot invalidate it."""
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def load_artifact(path: Path, repository_root: Path) -> dict:
    resolved, root = path.resolve(), repository_root.resolve()
    if root not in resolved.parents or not resolved.is_file() or resolved.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Model artifact path is missing, unsafe or oversized")
    content = resolved.read_bytes()
    try:
        artifact = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Model artifact is not valid JSON") from error
    missing = sorted(REQUIRED - set(artifact))
    if missing:
        raise ValueError(f"Model artifact is missing fields: {', '.join(missing)}")
    source = (root / artifact["source_code_path"]).resolve()
    if root not in source.parents or not source.is_file() or _portable_source_digest(source.read_bytes()) != artifact["source_code_sha256"]:
        raise ValueError("Model source path or SHA-256 does not validate")
    validate_promotion_evidence(artifact)
    canonical = json.dumps(artifact, sort_keys=True, separators=(",",":"), ensure_ascii=False)
    return {**artifact, "artifact_content_hash":hashlib.sha256(canonical.encode()).hexdigest()}
