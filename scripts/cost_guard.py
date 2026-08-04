#!/usr/bin/env python3
"""Fail when an unapproved potentially billable provider appears in repository text."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".md", ".html", ".css", ".env", ".example"}
BLOCKED = {
    "hosted-ai": re.compile(r"(?i)api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY"),
    "cloud": re.compile(r"(?i)amazonaws\.com|azure\.com|cloud\.google\.com|api\.mapbox\.com|arcgis\.com|supabase\.co|firebaseio\.com"),
    "payments": re.compile(r"(?i)stripe_secret|STRIPE_API_KEY|billing_account|credit_card"),
}
POLICY_ONLY = {
    Path("docs/cost-and-billing-audit.md"), Path("docs/zero-cost-operation.md"), Path("docs/security-model.md"),
    Path("AI_CONTEXT.md"), Path("AI_CHANGELOG.md"), Path("BUG_TRACKER.md"), Path("README.md"), Path("scripts/cost_guard.py"),
}
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "data", "node_modules"}


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS or part.endswith(".egg-info") for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == ".env.example":
            yield path


def main() -> int:
    violations = []
    scanned = 0
    for path in iter_text_files():
        scanned += 1
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in BLOCKED.items():
            for match in pattern.finditer(text):
                if relative in POLICY_ONLY:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{relative}:{line}: {label}: {match.group(0)}")
    if violations:
        print("ZERO-COST CHECK FAILED: potentially billable integration detected")
        print("\n".join(violations))
        return 1
    print(f"Scanned {scanned} source, configuration, environment and documentation files.")
    print("ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

