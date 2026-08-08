from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test3.claude_skills import SkillCandidateError, main, validate_candidate_file


class ClaudeSkillBoundaryTests(unittest.TestCase):
    def payload(self):
        return {
            "schema_version": "test3-skill-candidates/1.0", "candidate_only": True,
            "document_sha256": "a" * 64, "skill_name": "test3-cre-candidate-extraction",
            "generated_at": "2026-08-08T12:00:00Z", "limitations": ["Fictional fixture."],
            "candidates": [{"candidate_id": "fictional-1", "candidate_type": "market_observation",
                            "field_name": "vacancy_rate", "raw_value": "5.2%", "normalized_value": "0.052",
                            "unit": "ratio", "currency": None, "source_page": 7,
                            "source_excerpt": "Fictional vacancy was 5.2%.", "confidence": 0.9,
                            "methodology_notes": "Converted percent to ratio."}],
        }

    def test_manual_candidate_is_bounded_non_authoritative_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "candidate.json"
            path.write_text(json.dumps(self.payload()), encoding="utf-8")
            result = validate_candidate_file(path, expected_document_sha256="a" * 64)
            self.assertFalse(result["authoritative"])
            self.assertEqual(result["provider_mode"], "manual-claude-skill")
            self.assertEqual(len(result["output_sha256"]), 64)

    def test_wrong_document_or_unbacked_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "candidate.json"
            path.write_text(json.dumps(self.payload()), encoding="utf-8")
            with self.assertRaisesRegex(SkillCandidateError, "does not match"):
                validate_candidate_file(path, expected_document_sha256="b" * 64)
            payload = self.payload()
            payload["candidates"][0]["source_excerpt"] = ""
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(SkillCandidateError, "source evidence"):
                validate_candidate_file(path, expected_document_sha256="a" * 64)

    def test_validation_cli_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "candidate.json"
            path.write_text(json.dumps(self.payload()), encoding="utf-8")
            self.assertEqual(main([str(path), "--document-sha256", "a" * 64]), 0)
