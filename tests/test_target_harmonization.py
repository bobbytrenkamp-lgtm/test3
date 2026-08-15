from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test3.research.cross_source import validate_target_harmonization
from test3.research.milestone8 import milestone8_status
from test3.research.target_harmonization import (
    ACKNOWLEDGEMENTS,
    approve_target_harmonization,
    approved_target_harmonizations,
    prepare_target_harmonization_review,
    target_harmonization_status,
)
from test3.warehouse.storage import WarehousePaths


class TargetHarmonizationTests(unittest.TestCase):
    def _completed_attestation(self, packet: dict) -> dict:
        attestation = packet["attestation_template"]
        attestation.update({
            "analyst_identity": "fixture-analyst",
            "analyst_signature": "fixture-signature",
            "signed_at": "2026-08-14T09:00:00-04:00",
            "rationale": "Reviewed the distinct issuer methodologies and approved controlled external-validity research only.",
            "decision": "approve_with_controls",
            "acknowledgements": {name: True for name in ACKNOWLEDGEMENTS},
            "source_mapping_decisions": {
                source: {"decision": "approve_with_controls",
                         "rationale": "Retain the issuer-specific definition and require separate source performance."}
                for source in packet["source_mappings"]
            },
        })
        return attestation

    def test_prepare_is_blank_hash_bound_and_non_authoritative(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "review.json"
            result = prepare_target_harmonization_review(output)
            packet = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "AWAITING_TARGET_HARMONIZATION_ATTESTATION")
            self.assertEqual(packet["attestation_template"]["review_packet_hash"], packet["artifact_hash"])
            self.assertEqual(packet["attestation_template"]["analyst_identity"], "")
            self.assertFalse(packet["controlling_market_rent_target"])
            self.assertEqual(packet["source_mappings"]["AVB"]["compatibility"], "review_required")

    def test_real_attestation_creates_immutable_approved_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            packet_path, attestation_path = Path(root) / "review.json", Path(root) / "attestation.json"
            prepare_target_harmonization_review(packet_path)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            attestation_path.write_text(json.dumps(self._completed_attestation(packet)), encoding="utf-8")
            result = approve_target_harmonization(paths, packet_path, attestation_path)
            artifact = approved_target_harmonizations(paths)[0]
            self.assertEqual(result["status"], "APPROVED_TARGET_HARMONIZATION_CREATED")
            self.assertFalse(artifact["controlling_market_rent_target"])
            self.assertTrue(validate_target_harmonization(artifact, sources=["MAA", "AVB"])["passed"])
            self.assertEqual(target_harmonization_status(paths)["status"], "APPROVED")
            with self.assertRaises(FileExistsError):
                approve_target_harmonization(paths, packet_path, attestation_path)

    def test_missing_human_acknowledgement_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            packet_path, attestation_path = Path(root) / "review.json", Path(root) / "attestation.json"
            prepare_target_harmonization_review(packet_path)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            attestation = self._completed_attestation(packet)
            attestation["acknowledgements"][ACKNOWLEDGEMENTS[0]] = False
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "acknowledgements are incomplete"):
                approve_target_harmonization(paths, packet_path, attestation_path)

    def test_milestone_status_exposes_harmonization_blocker(self):
        with tempfile.TemporaryDirectory() as root:
            status = milestone8_status(WarehousePaths.from_data_root(root))
            self.assertEqual(status["target_harmonization"]["status"],
                             "AWAITING_TARGET_HARMONIZATION_ATTESTATION")
            self.assertIn("AWAITING_CROSS_SOURCE_TARGET_HARMONIZATION_APPROVAL", status["blockers"])


if __name__ == "__main__":
    unittest.main()
