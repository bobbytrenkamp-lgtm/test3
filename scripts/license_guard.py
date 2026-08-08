#!/usr/bin/env python3
"""Dependency/license guard for the dependency-free core."""
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
declared = set(tomllib.loads(pyproject)["project"].get("dependencies", []))
approved_dependencies = {"defusedxml==0.7.1", "duckdb==1.5.5", "et_xmlfile==2.0.0", "openpyxl==3.1.5", "Pillow==12.3.0", "pypdfium2==5.12.1"}
if declared != approved_dependencies:
    raise SystemExit(f"LICENSE CHECK FAILED: dependency allowlist mismatch: {sorted(declared ^ approved_dependencies)}")
if set(tomllib.loads(pyproject).get("build-system", {}).get("requires", [])) != {"setuptools==83.0.0"}:
    raise SystemExit("LICENSE CHECK FAILED: build dependency allowlist mismatch")
for manifest in ("requirements.txt", "Pipfile", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
    if (ROOT / manifest).exists():
        raise SystemExit(f"LICENSE CHECK FAILED: unaudited manifest {manifest}")
workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
allowed_actions = {"actions/checkout@v4", "actions/setup-python@v5"}
declared_actions = {line.split("uses:", 1)[1].strip() for line in workflow.splitlines() if "uses:" in line}
unknown = declared_actions - allowed_actions
if unknown:
    raise SystemExit(f"LICENSE CHECK FAILED: unaudited workflow actions: {sorted(unknown)}")
print("LICENSE CHECK PASSED: all pinned dependencies and workflow actions match the audited permissive-license allowlist.")
