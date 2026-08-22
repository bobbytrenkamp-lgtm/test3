from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from test3.cre_data.maa_governance import inspect_maa_review_packet, prepare_maa_rent_growth_review
from test3.cre_data.maa_markets import inspect_market_definition_candidates, prepare_maa_market_definitions
from test3.cre_data.sources.sec_maa import SNAPSHOT_SCHEMA, write_review_csv
from test3.research.governance_workspace import approval_workspace
from test3.warehouse.storage import WarehousePaths


FIXTURE = Path(__file__).parent / "fixtures" / "fictional_maa_snapshot.txt"


def _candidate_csv(folder: Path) -> Path:
    source = FIXTURE.read_bytes()
    snapshot = folder / "filing.snapshot.txt"
    snapshot.write_bytes(source)
    (folder / "filing.json").write_text(json.dumps({
        "schema_version": SNAPSHOT_SCHEMA, "snapshot_file": snapshot.name,
        "sha256": hashlib.sha256(source).hexdigest(),
        "filing_url": "https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
        "filing_date": "2025-07-30", "retrieved_at": "2026-08-09T12:00:00+00:00",
    }), encoding="utf-8")
    review = folder / "maa-candidates.csv"
    write_review_csv(folder, review)
    return review


class GovernanceWorkspaceTests(unittest.TestCase):
    def test_workspace_surfaces_verified_packets_and_human_only_actions(self):
        with tempfile.TemporaryDirectory() as root:
            data_root = Path(root)
            reports = data_root / "cre_reports"
            reports.mkdir()
            candidate = _candidate_csv(reports)
            review = reports / "maa-review.json"
            definitions = reports / "maa-markets.json"
            prepare_maa_rent_growth_review(candidate, review)
            prepare_maa_market_definitions(candidate, definitions)

            packet_summary = inspect_maa_review_packet(review)
            market_summary = inspect_market_definition_candidates(definitions)
            workspace = approval_workspace(WarehousePaths.from_data_root(data_root))

            self.assertEqual(packet_summary["integrity_status"], "passed")
            self.assertEqual(packet_summary["attestation_state"], "BLANK_HUMAN_ATTESTATION_TEMPLATE")
            self.assertFalse(packet_summary["template_has_identity"])
            self.assertEqual((market_summary["markets"], market_summary["evidence_ready"], market_summary["unresolved"]),
                             (1, 0, 1))
            self.assertEqual(workspace["status"], "HUMAN_GOVERNANCE_ACTION_REQUIRED")
            self.assertFalse(workspace["safety"]["can_approve"])
            self.assertFalse(workspace["safety"]["auto_fills_identity"])
            self.assertEqual({item["status"] for item in workspace["action_queue"]},
                             {"AWAITING_ANALYST_ATTESTATION", "AWAITING_MARKET_EVIDENCE"})

    def test_tampered_packet_is_reported_and_never_displayed_as_valid(self):
        with tempfile.TemporaryDirectory() as root:
            data_root = Path(root)
            reports = data_root / "cre_reports"
            reports.mkdir()
            candidate = _candidate_csv(reports)
            review = reports / "maa-review.json"
            prepare_maa_rent_growth_review(candidate, review)
            payload = json.loads(review.read_text(encoding="utf-8"))
            payload["dataset_summary"]["candidate_observations"] += 1
            review.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "integrity"):
                inspect_maa_review_packet(review)
            workspace = approval_workspace(WarehousePaths.from_data_root(data_root))
            self.assertEqual(workspace["review_packets"], [])
            self.assertEqual(len(workspace["artifact_errors"]), 1)
            self.assertFalse(workspace["safety"]["can_approve"])


if __name__ == "__main__":
    unittest.main()
