#!/usr/bin/env python3
"""Dependency/license guard for the dependency-free core."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
if re.search(r"(?m)^dependencies\s*=\s*\[[^]]*\S[^]]*\]", pyproject):
    raise SystemExit("LICENSE CHECK FAILED: dependencies require explicit allowlist and audit")
for manifest in ("requirements.txt", "Pipfile", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
    if (ROOT / manifest).exists():
        raise SystemExit(f"LICENSE CHECK FAILED: unaudited manifest {manifest}")
workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
allowed_actions = {"actions/checkout@v4", "actions/setup-python@v5"}
declared_actions = {line.split("uses:", 1)[1].strip() for line in workflow.splitlines() if "uses:" in line}
unknown = declared_actions - allowed_actions
if unknown:
    raise SystemExit(f"LICENSE CHECK FAILED: unaudited workflow actions: {sorted(unknown)}")
print("LICENSE CHECK PASSED: core has no third-party runtime dependencies; project license is MIT.")
