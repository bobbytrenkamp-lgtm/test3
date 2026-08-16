from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from test3.auth import hash_password
from test3.backup import create_backup, verify_backup
from test3.db import now
from test3.permissions import require
from test3.service import Service


FIXTURES = Path(__file__).parent / "fixtures" / "opportunity"
ACKNOWLEDGEMENTS = {
    "evidence_reviewed": True,
    "source_rights_reviewed": True,
    "limitations_acknowledged": True,
    "test2_advisory_only": True,
}


def _candidate(service: Service, organization_id: str, user_id: str, deal_id: str) -> dict:
    return service.property_opportunity_analysis(organization_id, user_id, deal_id, {
        "subject": {"address": "1 Fictional Subject", "latitude": 35.78, "longitude": -78.64,
                    "property_type": "multifamily", "units": 100, "year_built": 2017},
        "rent_comps_csv": (FIXTURES / "fictional_rent_comps.csv").read_text(encoding="utf-8"),
        "sale_comps_csv": (FIXTURES / "fictional_sale_comps.csv").read_text(encoding="utf-8"),
        "analysis_as_of": "2026-06-30",
        "source_metadata": {
            "rent_comps": {"source_name": "Fictional analyst rent file", "licensing_notes": "Fictional fixture", "rights_status": "user_owned"},
            "sale_comps": {"source_name": "Fictional analyst sale file", "licensing_notes": "Fictional fixture", "rights_status": "user_owned"},
        },
    })


class OpportunityReviewTests(unittest.TestCase):
    def _workspace(self, root: str):
        service = Service(Path(root))
        creator = service.seed()
        reviewer_id = str(uuid.uuid4())
        with service.db.connect() as connection:
            deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            connection.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (
                reviewer_id, creator["organization_id"], "reviewer@example.test", "Independent Reviewer",
                "reviewer", hash_password("fictional-reviewer-password"), now(),
            ))
        return service, creator, reviewer_id, deal_id

    def test_review_is_segregated_hash_bound_append_only_and_advisory(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer_id, deal_id = self._workspace(root)
            run = _candidate(service, creator["organization_id"], creator["id"], deal_id)
            approval = {"decision": "approved", "rationale": "Reviewed every evidence category and limitation.",
                        "acknowledgements": ACKNOWLEDGEMENTS}
            with self.assertRaisesRegex(ValueError, "creator cannot approve"):
                service.review_property_opportunity(creator["organization_id"], creator["id"], run["runId"], approval)
            incomplete = {**approval, "acknowledgements": {**ACKNOWLEDGEMENTS, "source_rights_reviewed": False}}
            with self.assertRaisesRegex(ValueError, "Every institutional acknowledgement"):
                service.review_property_opportunity(creator["organization_id"], reviewer_id, run["runId"], incomplete)
            decision = service.review_property_opportunity(creator["organization_id"], reviewer_id, run["runId"], approval)
            self.assertEqual(decision["decision"], "approved")
            self.assertFalse(decision["automatic_test2_apply"])
            detail = service.deal(deal_id, creator["organization_id"])
            self.assertEqual(detail["opportunity_runs"][0]["status"], "research_candidate")
            self.assertEqual(detail["opportunity_runs"][0]["review_state"], "approved")
            self.assertEqual(detail["opportunity_runs"][0]["decisions"][0]["artifact_sha256"], run["artifactHash"])
            with service.db.connect() as connection:
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("UPDATE opportunity_decisions SET rationale='changed' WHERE id=?", (decision["id"],))
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("DELETE FROM opportunity_decisions WHERE id=?", (decision["id"],))
            self.assertTrue(service.operational_integrity(creator["organization_id"])["ok"])
            archive = Path(root) / "review.zip"
            create_backup(Path(root), archive)
            report = verify_backup(archive)
            self.assertEqual(report["format"], "test3-backup/9.0")
            self.assertEqual(report["counts"]["opportunity_decisions"], 1)

    def test_test2_handoff_requires_latest_approval_and_remains_advisory(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer_id, deal_id = self._workspace(root)
            run = _candidate(service, creator["organization_id"], creator["id"], deal_id)
            with self.assertRaisesRegex(ValueError, "latest independent opportunity decision"):
                service.create_opportunity_test2_handoff(creator["organization_id"], creator["id"], run["runId"])
            approval = service.review_property_opportunity(creator["organization_id"], reviewer_id, run["runId"], {
                "decision": "approved", "rationale": "Independent evidence review completed for advisory handoff.",
                "acknowledgements": ACKNOWLEDGEMENTS,
            })
            handoff = service.create_opportunity_test2_handoff(creator["organization_id"], creator["id"], run["runId"])
            content = handoff["content"]
            self.assertEqual(content["status"], "ADVISORY_APPROVED_EVIDENCE_NOT_APPLIED")
            self.assertFalse(content["automaticApply"])
            self.assertEqual(content["controllingUnderwritingEngine"], "test2")
            self.assertEqual(content["approval"]["decisionHash"], approval["decision_hash"])
            self.assertEqual(content["opportunityArtifactSha256"], run["artifactHash"])
            self.assertEqual(content["opportunityScore"]["status"], "NO_VALIDATED_OPPORTUNITY_SCORE")
            self.assertGreaterEqual(len(content["comparableEvidence"]["rent"]), 3)
            self.assertTrue(all(item["referenceHash"] for item in content["comparableEvidence"]["sale"]))
            retrieved = service.opportunity_handoff(creator["organization_id"], handoff["artifact"]["id"])
            self.assertEqual(retrieved["content_sha256"], handoff["artifact"]["content_sha256"])
            with self.assertRaises(LookupError):
                service.opportunity_handoff("different-organization", handoff["artifact"]["id"])
            with self.assertRaisesRegex(ValueError, "already exists"):
                service.create_opportunity_test2_handoff(creator["organization_id"], creator["id"], run["runId"])
            with service.db.connect() as connection:
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("UPDATE opportunity_handoffs SET content_json='{}' WHERE id=?", (handoff["artifact"]["id"],))
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("DELETE FROM opportunity_handoffs WHERE id=?", (handoff["artifact"]["id"],))
            self.assertTrue(service.operational_integrity(creator["organization_id"])["ok"])

    def test_change_request_is_structured_and_never_mutates_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer_id, deal_id = self._workspace(root)
            run = _candidate(service, creator["organization_id"], creator["id"], deal_id)
            original = service.deal(deal_id, creator["organization_id"])["opportunity_runs"][0]["content"]
            request = service.review_property_opportunity(creator["organization_id"], reviewer_id, run["runId"], {
                "decision": "changes_requested", "rationale": "Sale comparable selection needs a documented correction.",
                "modifications": [{"path": "/saleEvidence/comparables/0", "proposed_value": "exclude",
                                   "rationale": "The source property is outside the governed market boundary."}],
            })
            self.assertEqual(request["decision"], "changes_requested")
            detail = service.deal(deal_id, creator["organization_id"])
            self.assertEqual(detail["opportunity_runs"][0]["content"], original)
            self.assertEqual(detail["opportunity_runs"][0]["review_state"], "changes_requested")

    def test_reviewer_permission_is_explicit_and_analyst_cannot_review(self):
        require("reviewer", "opportunity.review")
        with self.assertRaises(PermissionError):
            require("analyst", "opportunity.review")

    def test_tampered_decision_fails_operational_integrity(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer_id, deal_id = self._workspace(root)
            run = _candidate(service, creator["organization_id"], creator["id"], deal_id)
            decision = service.review_property_opportunity(creator["organization_id"], reviewer_id, run["runId"], {
                "decision": "rejected", "rationale": "Evidence is insufficient for institutional reliance.",
            })
            with service.db.connect() as connection:
                connection.execute("DROP TRIGGER opportunity_decisions_no_update")
                connection.execute("UPDATE opportunity_decisions SET rationale='tampered' WHERE id=?", (decision["id"],))
            report = service.operational_integrity(creator["organization_id"])
            self.assertFalse(report["ok"])
            self.assertEqual(report["propertyOpportunity"]["decisionMismatches"], 1)


if __name__ == "__main__":
    unittest.main()
