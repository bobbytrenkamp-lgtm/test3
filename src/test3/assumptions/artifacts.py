from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
REQUIRED = {"model_name","model_version","target_assumption","training_data_snapshot_hash","feature_schema_version","training_window","validation_window","property_types","geographic_coverage","sample_size","coefficients","standard_errors","model_metrics","residual_diagnostics","limitations","source_code_path","source_code_sha256","repository_commit_sha","r_version","data_status","model_card_path","validation_results_path","input_schema_path"}


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
    if root not in source.parents or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != artifact["source_code_sha256"]:
        raise ValueError("Model source path or SHA-256 does not validate")
    canonical = json.dumps(artifact, sort_keys=True, separators=(",",":"), ensure_ascii=False)
    return {**artifact, "artifact_content_hash":hashlib.sha256(canonical.encode()).hexdigest()}
