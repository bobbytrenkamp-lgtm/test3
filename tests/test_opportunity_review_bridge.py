from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from test3.auth import hash_password
from test3.backup import create_backup, verify_backup
from test3.db import now
from test3.service import ConflictError, Service


HASH = "a" * 64
ACKS = {"evidence_reviewed": True, "source_rights_reviewed": True,
        "limitations_acknowledged": True, "test2_advisory_only": True}


def evidence(complete: bool = True) -> dict:
    payload = {"analysis_as_of": "2026-08-22", "rent_unit": "USD/unit/month",
               "subject_rent": "1800", "market_rent": "2027", "basis_unit": "USD/unit",
               "acquisition_basis": "210000", "comparable_sale_basis": "235000",
               "current_noi": "1200000", "stabilized_noi": "1600000",
               "subject_cap_rate": "0.061", "market_cap_rate": "0.052",
               "subject_vacancy": "0.08", "market_vacancy": "0.05",
               "rent_comp_count": 6, "sale_comp_count": 5,
               "location_evidence_complete": True, "renovation_budget_verified": True}
    if complete:
        dimensions = ("rent", "basis", "noi", "cap_rate", "vacancy", "comparables", "location")
        payload["evidence_hashes"] = {key: [HASH] for key in dimensions}
        payload["evidence_dates"] = {key: "2026-08-22" for key in dimensions}
    return payload


class OpportunityReviewBridgeTests(unittest.TestCase):
    def workspace(self, root: str):
        service, creator = Service(Path(root)), None
        creator = service.seed()
        reviewer = str(uuid.uuid4())
        with service.db.connect() as connection:
            connection.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (reviewer, creator["organization_id"],
                               "bridge-reviewer@example.test", "Bridge Reviewer", "reviewer",
                               hash_password("fictional-reviewer-password"), now()))
        candidate = service.create_opportunity_candidate(creator["organization_id"], creator["id"],
                    {"property_type": "multifamily", "display_name": "Fictional Bridge", "market": "Raleigh", "origin_type": "manual"})
        return service, creator, reviewer, candidate

    def test_current_screening_generates_hash_bound_artifact_and_independent_approval(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer, candidate = self.workspace(root)
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], evidence())
            service.screen_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"], {})
            artifact = service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            self.assertEqual(artifact["content"]["screeningCurrencyStatus"], "CURRENT")
            self.assertFalse(artifact["content"]["candidate"]["deal_id"])
            with self.assertRaisesRegex(ValueError, "creator cannot approve"):
                service.review_candidate_artifact(creator["organization_id"], creator["id"], artifact["id"],
                    {"decision": "approved", "rationale": "Creator approval must remain segregated.", "acknowledgements": ACKS})
            decision = service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "approved", "rationale": "Independent source evidence review completed.", "acknowledgements": ACKS})
            self.assertFalse(decision["automatic_deal_creation"])
            self.assertFalse(decision["automatic_underwrite_apply"])
            self.assertEqual(service.candidate_review_artifacts(creator["organization_id"])[0]["review_state"], "approved")
            promotion = service.promote_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"])
            self.assertFalse(promotion["automatic_underwrite_apply"])
            promoted = service.opportunity_candidate(creator["organization_id"], candidate["id"])["candidate"]
            self.assertEqual((promoted["status"], promoted["deal_id"]), ("promoted_to_diligence", promotion["deal_id"]))
            with self.assertRaisesRegex(ConflictError, "closed review"):
                service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "rejected", "rationale": "Post-promotion mutation must be blocked."})
            self.assertEqual(service.opportunity_candidate_history(creator["organization_id"], candidate["id"])["timeline"][-1]["type"], "candidate_promoted")
            with service.db.connect() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM manual_assumptions WHERE deal_id=?", (promotion["deal_id"],)).fetchone()[0], 0)
            integrity = service.operational_integrity(creator["organization_id"])
            self.assertTrue(integrity["ok"])
            self.assertEqual(integrity["opportunityCandidateReview"], {
                "artifactCount": 1, "artifactMismatches": 0,
                "decisionCount": 1, "decisionMismatches": 0,
                "promotionCount": 1, "promotionMismatches": 0,
            })
            with service.db.connect() as connection:
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("UPDATE opportunity_candidate_review_artifacts SET content_json='{}' WHERE id=?", (artifact["id"],))
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("DELETE FROM opportunity_candidate_review_decisions WHERE id=?", (decision["id"],))
            archive = Path(root) / "bridge.zip"; create_backup(Path(root), archive)
            report = verify_backup(archive)
            self.assertEqual(report["format"], "test3-backup/11.0")
            self.assertEqual(report["counts"]["opportunity_candidate_review_artifacts"], 1)
            self.assertEqual(report["counts"]["opportunity_candidate_promotions"], 1)

    def test_generation_fails_closed_for_missing_outdated_and_duplicate_screening(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, _, candidate = self.workspace(root)
            with self.assertRaisesRegex(ValueError, "current immutable screening"):
                service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], evidence())
            service.screen_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"], {})
            artifact = service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            with self.assertRaises(ConflictError):
                service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], evidence(False))
            with self.assertRaisesRegex(ValueError, "current immutable screening"):
                service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            self.assertTrue(artifact["content_sha256"])

    def test_approval_fails_closed_when_artifact_is_no_longer_current(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer, candidate = self.workspace(root)
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], evidence())
            service.screen_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"], {})
            artifact = service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            changed = evidence(); changed["subject_rent"] = "1810"
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], changed)
            with self.assertRaisesRegex(ValueError, "no longer current"):
                service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "approved", "rationale": "This retained artifact is now stale.", "acknowledgements": ACKS})
            rejected = service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "rejected", "rationale": "Superseded by a newer evidence version."})
            self.assertEqual(rejected["decision"], "rejected")

    def test_promotion_requires_current_independent_approval(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer, candidate = self.workspace(root)
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], evidence())
            service.screen_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"], {})
            artifact = service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            with self.assertRaisesRegex(ValueError, "independent approval"):
                service.promote_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"])
            service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "approved", "rationale": "Independent review supports diligence intake.", "acknowledgements": ACKS})
            service.promote_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"])
            with self.assertRaises(ConflictError):
                service.promote_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"])

    def test_insufficient_evidence_artifact_can_be_rejected_but_not_approved(self):
        with tempfile.TemporaryDirectory() as root:
            service, creator, reviewer, candidate = self.workspace(root)
            service.create_opportunity_candidate_version(creator["organization_id"], creator["id"], candidate["id"], evidence(False))
            service.screen_opportunity_candidate(creator["organization_id"], creator["id"], candidate["id"], {})
            artifact = service.create_candidate_review_artifact(creator["organization_id"], creator["id"], candidate["id"])
            with self.assertRaisesRegex(ValueError, "Insufficient-evidence"):
                service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "approved", "rationale": "This should be blocked as insufficient.", "acknowledgements": ACKS})
            rejected = service.review_candidate_artifact(creator["organization_id"], reviewer, artifact["id"],
                    {"decision": "rejected", "rationale": "Evidence remains insufficient for reliance."})
            self.assertEqual(rejected["decision"], "rejected")


if __name__ == "__main__":
    unittest.main()
