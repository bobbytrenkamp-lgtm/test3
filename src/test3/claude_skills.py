"""Offline validation boundary for manually produced Claude Skill candidates.

This module never starts Claude, reads credentials, or makes a network request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

MAX_CANDIDATE_BYTES = 2 * 1024 * 1024
ALLOWED_CANDIDATE_TYPES = {"market_observation", "deal_fact", "lease_fact", "debt_term"}


class SkillCandidateError(ValueError):
    pass


def _strict_object(raw: str) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SkillCandidateError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=unique_pairs)
    except json.JSONDecodeError as exc:
        raise SkillCandidateError("candidate output is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SkillCandidateError("candidate output must be a JSON object")
    return payload


def validate_candidate_file(path: str | Path, *, expected_document_sha256: str) -> dict:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > MAX_CANDIDATE_BYTES:
        raise SkillCandidateError("candidate file is missing or exceeds 2 MiB")
    payload = _strict_object(source.read_text(encoding="utf-8"))
    required = {"schema_version", "candidate_only", "document_sha256", "skill_name", "generated_at", "candidates", "limitations"}
    if set(payload) != required:
        raise SkillCandidateError("candidate output fields do not match the governed schema")
    if payload["schema_version"] != "test3-skill-candidates/1.0" or payload["candidate_only"] is not True:
        raise SkillCandidateError("Skill output must be explicitly candidate-only schema version 1.0")
    if payload["document_sha256"] != expected_document_sha256 or not _sha256(expected_document_sha256):
        raise SkillCandidateError("candidate document hash does not match the reviewed input")
    if not isinstance(payload["candidates"], list) or len(payload["candidates"]) > 10_000:
        raise SkillCandidateError("candidates must be a bounded JSON array")
    for index, candidate in enumerate(payload["candidates"]):
        fields = {"candidate_id", "candidate_type", "field_name", "raw_value", "normalized_value", "unit", "currency", "source_page", "source_excerpt", "confidence", "methodology_notes"}
        if not isinstance(candidate, dict) or set(candidate) != fields:
            raise SkillCandidateError(f"candidate {index} fields do not match the governed schema")
        if candidate["candidate_type"] not in ALLOWED_CANDIDATE_TYPES:
            raise SkillCandidateError(f"candidate {index} has an unsupported type")
        if not isinstance(candidate["confidence"], (int, float)) or isinstance(candidate["confidence"], bool) or not 0 <= candidate["confidence"] <= 1:
            raise SkillCandidateError(f"candidate {index} confidence must be between zero and one")
        if not isinstance(candidate["source_page"], int) or candidate["source_page"] < 1 or not str(candidate["source_excerpt"]).strip():
            raise SkillCandidateError(f"candidate {index} requires page-level source evidence")
    if not isinstance(payload["limitations"], list):
        raise SkillCandidateError("limitations must be an array")
    payload["output_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    payload["provider_mode"] = "manual-claude-skill"
    payload["authoritative"] = False
    return payload


def _sha256(value: object) -> bool:
    text = str(value)
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a manually generated, candidate-only Claude Skill JSON file")
    parser.add_argument("candidate_file")
    parser.add_argument("--document-sha256", required=True)
    args = parser.parse_args(argv)
    result = validate_candidate_file(args.candidate_file, expected_document_sha256=args.document_sha256)
    print(json.dumps({"valid": True, "candidate_count": len(result["candidates"]), "output_sha256": result["output_sha256"],
                      "candidate_only": True, "authoritative": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
