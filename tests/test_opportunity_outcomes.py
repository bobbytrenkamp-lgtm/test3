from __future__ import annotations

import csv
from datetime import date
import json
import tempfile
import unittest
from pathlib import Path

from test3.opportunity.outcomes import (ACKNOWLEDGEMENTS, ATTESTATION_SCHEMA, CANDIDATE_FIELDS,
                                        approve_outcome_review, approved_outcome_readiness,
                                        prepare_outcome_review)


def row(**changes) -> dict:
    value = {
        "observation_id": "real-1", "property_id": "property-1", "market_id": "market-1",
        "period": "2025-Q1", "property_type": "multifamily", "forecast_origin": "2025-01-01",
        "feature_available_at": "2024-12-31", "outcome_realized_at": "2026-01-01",
        "outcome_released_at": "2026-02-01", "outcome": "realized_total_return",
        "outcome_value": "0.10", "data_status": "real", "source_hash": "a" * 64,
        "feature_hash": "b" * 64, "source_name": "Analyst-owned performance ledger",
        "source_record_id": "ledger-row-1", "licensing_notes": "Internal analysis rights confirmed",
        "methodology": "Realized unlevered total return through disposition",
    }
    value.update(changes)
    return value


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CANDIDATE_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


class RealizedOutcomeWorkflowTests(unittest.TestCase):
    def test_review_is_non_authoritative_exception_first_and_deterministic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            write_csv(source, [row()])
            result = prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "AWAITING_ANALYST_ATTESTATION")
            self.assertFalse(payload["authoritative"])
            self.assertEqual(payload["summary"]["blocking_findings"], 0)
            self.assertEqual(payload["deterministic_spot_check"][0]["observation_id"], "real-1")
            self.assertEqual(payload["attestation_template"]["analyst_identity"], "")
            with self.assertRaises(FileExistsError):
                prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))

    def test_future_release_and_duplicate_identity_block_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            write_csv(source, [row(), row(observation_id="real-2", outcome_released_at="2027-01-01")])
            prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            payload = json.loads(packet.read_text(encoding="utf-8"))
            codes = {item["code"] for item in payload["findings"]}
            self.assertIn("duplicate_property_origin_outcome", codes)
            self.assertIn("outcome_not_released_as_of_review", codes)

    def test_invalid_hash_and_period_fail_before_human_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            write_csv(source, [row(period="2025-Q5", source_hash="g" * 64)])
            prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            codes = {item["code"] for item in json.loads(packet.read_text(encoding="utf-8"))["findings"]}
            self.assertEqual(codes, {"lineage_hash_invalid", "period_invalid"})

    def test_completed_attestation_creates_separate_immutable_approved_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            attestation = root / "attestation.json"; approved = root / "approved.csv"
            write_csv(source, [row()])
            prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            template = json.loads(packet.read_text(encoding="utf-8"))["attestation_template"]
            template.update({"analyst_identity": "analyst-7", "signed_at": "2026-08-22T16:00:00-04:00",
                             "rationale": "Verified the ledger evidence and realized-return methodology.",
                             "approved_outcomes": ["realized_total_return"],
                             "acknowledgements": {name: True for name in ACKNOWLEDGEMENTS}})
            attestation.write_text(json.dumps(template), encoding="utf-8")
            result = approve_outcome_review(source, attestation, approved, as_of=date(2026, 8, 22))
            self.assertEqual(result["observations"], 1)
            self.assertTrue(source.exists())
            with approved.open(encoding="utf-8", newline="") as stream:
                approved_row = next(csv.DictReader(stream))
            self.assertEqual(approved_row["analyst_verified"], "true")
            self.assertEqual(approved_row["rights_documented"], "true")
            readiness = approved_outcome_readiness(approved, as_of=date(2026, 8, 22))
            self.assertEqual(readiness["eligibleObservations"], 1)
            self.assertFalse(readiness["readyForCandidateBacktest"])
            with self.assertRaises(FileExistsError):
                approve_outcome_review(source, attestation, approved, as_of=date(2026, 8, 22))

    def test_changed_candidate_invalidates_attestation_and_tamper_breaks_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            attestation = root / "attestation.json"; approved = root / "approved.csv"
            write_csv(source, [row()]); prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            template = json.loads(packet.read_text(encoding="utf-8"))["attestation_template"]
            template.update({"analyst_identity": "analyst-7", "signed_at": "2026-08-22T16:00:00-04:00",
                             "rationale": "Verified the ledger evidence and realized-return methodology.",
                             "approved_outcomes": ["realized_total_return"],
                             "acknowledgements": {name: True for name in ACKNOWLEDGEMENTS}})
            attestation.write_text(json.dumps(template), encoding="utf-8")
            write_csv(source, [row(outcome_value="0.11")])
            with self.assertRaisesRegex(ValueError, "different candidate bytes"):
                approve_outcome_review(source, attestation, approved, as_of=date(2026, 8, 22))

    def test_modified_approval_sidecar_fails_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            attestation = root / "attestation.json"; approved = root / "approved.csv"
            write_csv(source, [row()]); prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            template = json.loads(packet.read_text(encoding="utf-8"))["attestation_template"]
            template.update({"analyst_identity": "analyst-7", "signed_at": "2026-08-22T16:00:00-04:00",
                             "rationale": "Verified the ledger evidence and realized-return methodology.",
                             "approved_outcomes": ["realized_total_return"],
                             "acknowledgements": {name: True for name in ACKNOWLEDGEMENTS}})
            attestation.write_text(json.dumps(template), encoding="utf-8")
            result = approve_outcome_review(source, attestation, approved, as_of=date(2026, 8, 22))
            sidecar = Path(result["attestation_sidecar"])
            metadata = json.loads(sidecar.read_text(encoding="utf-8")); metadata["attestation"]["rationale"] = "tampered"
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity check failed"):
                approved_outcome_readiness(approved, as_of=date(2026, 8, 22))

    def test_attestation_schema_is_explicit(self):
        self.assertEqual(ATTESTATION_SCHEMA, "test3-opportunity-outcome-attestation/1.0.0")

    def test_approval_cannot_change_the_attested_review_vintage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "outcomes.csv"; packet = root / "review.json"
            attestation = root / "attestation.json"; approved = root / "approved.csv"
            write_csv(source, [row()]); prepare_outcome_review(source, packet, as_of=date(2026, 8, 22))
            template = json.loads(packet.read_text(encoding="utf-8"))["attestation_template"]
            template.update({"analyst_identity": "analyst-7", "signed_at": "2026-08-22T16:00:00-04:00",
                             "rationale": "Verified the ledger evidence and realized-return methodology.",
                             "approved_outcomes": ["realized_total_return"],
                             "acknowledgements": {name: True for name in ACKNOWLEDGEMENTS}})
            attestation.write_text(json.dumps(template), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from the attested review vintage"):
                approve_outcome_review(source, attestation, approved, as_of=date(2026, 8, 23))


if __name__ == "__main__":
    unittest.main()
