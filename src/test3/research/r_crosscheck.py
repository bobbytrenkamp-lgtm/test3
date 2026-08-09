from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .datasets import PanelDataset
from .linear import LinearModel
from .reference import CrossCheckTolerances


def cross_check_r(panel: PanelDataset, native: LinearModel, *, entity_fixed_effects: bool, time_fixed_effects: bool,
                  covariance: str, script_path: Path | None = None,
                  tolerances: CrossCheckTolerances = CrossCheckTolerances()) -> dict:
    runtime = shutil.which("Rscript")
    script = script_path or Path(__file__).resolve().parents[3] / "research" / "R" / "validate_python_model.R"
    if runtime is None:
        return {"status": "not_available", "reason": "Optional local Rscript runtime is not installed.",
                "tolerances": tolerances.__dict__}
    if not script.is_file():
        return {"status": "failed", "reason": "Governed R validation script is missing.",
                "tolerances": tolerances.__dict__}
    columns = [panel.entity_column, panel.time_column, panel.target, *panel.features]
    with tempfile.TemporaryDirectory() as root:
        source, output = Path(root) / "panel.csv", Path(root) / "result.json"
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader(); writer.writerows({name: row[name] for name in columns} for row in panel.rows)
        completed = subprocess.run(
            [runtime, "--vanilla", str(script), str(source), str(output), panel.target, ",".join(panel.features),
             panel.entity_column, panel.time_column, str(entity_fixed_effects).lower(), str(time_fixed_effects).lower(), covariance],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if completed.returncode != 0 or not output.is_file():
            message = (completed.stderr or completed.stdout or "R validation failed").strip()[:1000]
            status = "not_available" if completed.returncode == 3 else "failed"
            return {"status": status, "reason": message, "tolerances": tolerances.__dict__}
        payload = json.loads(output.read_text(encoding="utf-8"))
        r_coefficients = [float(value) for value in payload.get("coefficients", [])]
        r_standard_errors = [float(value) for value in payload.get("standard_errors", [])]
        if len(r_coefficients) != len(native.coefficients) or len(r_standard_errors) != len(native.standard_errors):
            return {"status": "failed", "reason": "R and Python produced different parameter counts.",
                    "tolerances": tolerances.__dict__}
        coefficient_difference = max(abs(left - right) for left, right in zip(r_coefficients, native.coefficients, strict=True))
        se_difference = max(abs(left - right) for left, right in zip(r_standard_errors, native.standard_errors, strict=True))
        r_squared_difference = abs(float(payload["r_squared"]) - float(native.diagnostics["r_squared"]))
        payload["coefficient_max_difference"] = coefficient_difference
        payload["se_max_difference"] = se_difference
        payload["r_squared_difference"] = r_squared_difference
        payload["status"] = "passed" if (coefficient_difference <= tolerances.coefficient_absolute and
                                                   se_difference <= tolerances.standard_error_absolute and
                                                   r_squared_difference <= tolerances.r_squared_absolute) else "failed"
        payload["result_hash"] = hashlib.sha256(output.read_bytes()).hexdigest()
        payload["script_sha256"] = hashlib.sha256(script.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        payload["tolerances"] = tolerances.__dict__
        return payload
