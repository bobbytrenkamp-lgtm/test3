from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
import uuid

from test3.db import now
from test3.opportunity import DEFAULT_SCREENING_POLICY, registered_screening_policy
from test3.service import Service


HASH = "b" * 64


def compact_evidence(*, rent=("1000", "1000"), basis=("100", "100"), extra=None):
    value = {
        "analysis_as_of": "2026-06-30", "subject_rent": rent[0], "market_rent": rent[1],
        "rent_unit": "USD/unit/month", "acquisition_basis": basis[0], "comparable_sale_basis": basis[1],
        "basis_unit": "USD/unit", "rent_comp_count": 3,
        "evidence_hashes": {item: [HASH] for item in ("rent", "basis", "comparables")},
        "evidence_dates": {item: "2026-06-01" for item in ("rent", "basis", "comparables")},
    }
    value.update(extra or {})
    return value


class OpportunityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.temp.name)); self.user = self.service.seed()

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, name, address=None, market="Raleigh"):
        return self.service.create_opportunity_candidate(self.user["organization_id"], self.user["id"], {
            "property_type": "multifamily", "display_name": name, "address": address or f"{name} Example St",
            "market": market, "origin_type": "manual"})

    def add_and_screen(self, candidate, payload):
        self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], payload)
        return self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], candidate["id"], {})

    def test_tier_sort_uses_workflow_priority_and_places_unscreened_last(self):
        high = self.candidate("High")
        high_payload = compact_evidence(rent=("1000", "1200"), basis=("100", "120"), extra={
            "current_noi": "100", "stabilized_noi": "120", "subject_cap_rate": "0.06", "market_cap_rate": "0.05",
            "evidence_hashes": {item: [HASH] for item in ("rent", "basis", "noi", "cap_rate", "comparables")},
            "evidence_dates": {item: "2026-06-01" for item in ("rent", "basis", "noi", "cap_rate", "comparables")},
        })
        worth = self.candidate("Worth"); low = self.candidate("Low"); insufficient = self.candidate("Insufficient")
        never = self.candidate("Never")
        self.add_and_screen(high, high_payload)
        self.add_and_screen(worth, compact_evidence(rent=("1000", "1060")))
        self.add_and_screen(low, compact_evidence())
        self.add_and_screen(insufficient, {
            "analysis_as_of": "2026-06-30", "subject_rent": "1000", "market_rent": "1200",
            "rent_unit": "USD/unit/month", "evidence_hashes": {"rent": [HASH]},
            "evidence_dates": {"rent": "2026-06-01"}})
        page = self.service.list_opportunity_candidates(self.user["organization_id"], {"sort": "screening_tier"})
        self.assertEqual([(item["display_name"], item["screening_priority_rank"]) for item in page["items"]],
                         [("High", 1), ("Worth", 2), ("Low", 3), ("Insufficient", 4), ("Never", 5)])
        self.assertIsNone(page["items"][-1]["screening_tier"])

    def test_creation_rejects_future_chronology_before_persistence(self):
        candidate = self.candidate("Dates")
        for payload, message in (
            ({**compact_evidence(), "analysis_as_of": "2099-01-01"}, "current UTC"),
            (compact_evidence(extra={"evidence_dates": {"rent": "2026-07-01"}}), "evidence_dates.rent"),
            (compact_evidence(extra={"insurance_evidence_date": "2026-07-01"}), "insurance_evidence_date"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], payload)
        self.assertEqual(self.service.opportunity_candidate(self.user["organization_id"], candidate["id"])["versions"], [])

    def test_screening_currency_tracks_latest_evidence_without_rewriting_history(self):
        candidate = self.candidate("Currency")
        before = self.service.list_opportunity_candidates(self.user["organization_id"], {})["items"][0]
        self.assertEqual(before["screening_currency_status"], "NOT_SCREENED")
        self.add_and_screen(candidate, compact_evidence())
        current = self.service.opportunity_candidate(self.user["organization_id"], candidate["id"])
        self.assertEqual((current["latest_evidence_version"], current["latest_screened_version"], current["screening_currency_status"]), (1, 1, "CURRENT"))
        self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], compact_evidence(rent=("999", "1000")))
        outdated = self.service.list_opportunity_candidates(self.user["organization_id"], {"screening_currency_status": "OUTDATED_EVIDENCE"})["items"][0]
        self.assertEqual((outdated["latest_evidence_version"], outdated["latest_screened_version"], outdated["screening_currency_status"]), (2, 1, "OUTDATED_EVIDENCE"))
        self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], candidate["id"], {})
        final = self.service.opportunity_candidate(self.user["organization_id"], candidate["id"])
        self.assertEqual(final["screening_currency_status"], "CURRENT")
        self.assertEqual(len(final["screening_runs"]), 2)

    def test_projection_is_ui_ready_exact_and_filters_are_server_side(self):
        candidate = self.candidate("Oak Ridge", "10 Oak Ridge Avenue", "Charlotte")
        result = self.add_and_screen(candidate, compact_evidence(rent=("1000", "1125"), basis=("150", "170"), extra={
            "current_noi": "1000000.00", "stabilized_noi": "1100000.00",
            "evidence_hashes": {item: [HASH] for item in ("rent", "basis", "noi", "comparables")},
            "evidence_dates": {item: "2026-06-01" for item in ("rent", "basis", "noi", "comparables")},
        }))
        expected = result["result"]["derivedMetrics"]
        query = {"q": "oak ridge", "screening_currency_status": "CURRENT", "evidence_completeness_min": "0.5",
                 "rent_gap_min": "0.11", "basis_discount_min": "0.11", "freshness_max_days": "30", "limit": "1"}
        item = self.service.list_opportunity_candidates(self.user["organization_id"], query)["items"][0]
        self.assertEqual(item["rent_gap_pct"], expected["rentGapPct"])
        self.assertEqual(item["basis_discount_pct"], expected["basisDiscountPct"])
        self.assertEqual(item["evidence_supported_noi_delta"], "100000.00")
        self.assertIsInstance(item["rent_gap_pct"], str)
        self.assertEqual(item["validated_score_status"], "NO_VALIDATED_OPPORTUNITY_SCORE")
        self.assertGreater(item["warning_count"], 0)
        self.assertEqual(self.service.list_opportunity_candidates(self.user["organization_id"], {"q": "%_"})["pagination"]["total"], 0)

    def test_conservative_address_normalization_and_archive_transition(self):
        first = self.candidate("First", "123 Main Street")
        with self.service.db.connect() as connection:
            connection.execute("UPDATE opportunity_candidates SET normalized_address_sha256=? WHERE id=?", ("f" * 64, first["id"]))
        for address in ("123 MAIN ST.", " 123  Main   St "):
            duplicate = self.candidate(address, address)
            self.assertEqual(duplicate["warnings"], ["POSSIBLE_DUPLICATE_CANDIDATE"])
        apt2 = self.candidate("Apt 2", "123 Main St Apt 2")
        apt3 = self.candidate("Apt 3", "123 Main St Apt 3")
        self.assertEqual(apt2["warnings"], [])
        self.assertEqual(apt3["warnings"], [])
        self.add_and_screen(first, compact_evidence())
        archived = self.service.archive_opportunity_candidate(self.user["organization_id"], self.user["id"], first["id"])
        self.assertEqual(archived["status"], "archived")
        detail = self.service.opportunity_candidate(self.user["organization_id"], first["id"])
        self.assertEqual((detail["candidate"]["status"], len(detail["versions"]), len(detail["screening_runs"])), ("archived", 1, 1))
        self.assertEqual(self.service.list_opportunity_candidates(self.user["organization_id"], {"status": "archived"})["pagination"]["total"], 1)
        with self.assertRaisesRegex(ValueError, "already archived"):
            self.service.archive_opportunity_candidate(self.user["organization_id"], self.user["id"], first["id"])
        with self.assertRaisesRegex(ValueError, "active candidates"):
            self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], first["id"], compact_evidence(rent=("999", "1000")))
        with self.assertRaisesRegex(ValueError, "active candidates"):
            self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], first["id"], {})

    def test_policy_registry_is_exact_and_immutable(self):
        policy = registered_screening_policy(DEFAULT_SCREENING_POLICY.policy_id, DEFAULT_SCREENING_POLICY.version,
                                             DEFAULT_SCREENING_POLICY.content_hash)
        self.assertIs(policy, DEFAULT_SCREENING_POLICY)
        self.assertIsNone(registered_screening_policy(DEFAULT_SCREENING_POLICY.policy_id, "1.1.0"))
        self.assertIsNone(registered_screening_policy(DEFAULT_SCREENING_POLICY.policy_id,
                                                      DEFAULT_SCREENING_POLICY.version, "0" * 64))

    def test_10000_candidate_query_uses_bounded_projection(self):
        created = now()
        rows = [(str(uuid.uuid4()), self.user["organization_id"], None, self.user["id"], "multifamily",
                 f"Candidate {index}", f"{index} Scale Test Rd", None, "Scale Market", None,
                 "candidate", "manual", created) for index in range(10_000)]
        with self.service.db.connect() as connection:
            connection.executemany("INSERT INTO opportunity_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        started = time.perf_counter()
        page = self.service.list_opportunity_candidates(self.user["organization_id"], {"q": "Scale Market", "limit": 25})
        elapsed = time.perf_counter() - started
        self.assertEqual((page["pagination"]["total"], page["pagination"]["returned"]), (10_000, 25))
        self.assertLess(elapsed, 5.0)

    def test_every_screening_binding_tamper_fails_integrity(self):
        mutations = {
            "policy_id": "'unknown-policy'", "policy_version": "'9.9.9'", "policy_sha256": "'" + "0" * 64 + "'",
            "input_snapshot_sha256": "'" + "1" * 64 + "'", "evidence_sha256": "'" + "2" * 64 + "'",
            "screening_tier": "'HIGH_PRIORITY_REVIEW'", "evaluated_at": "'2026-07-01T00:00:00+00:00'",
            "result_json": "'{\"tampered\":true}'",
        }
        for field, expression in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                service = Service(Path(root)); user = service.seed()
                candidate = service.create_opportunity_candidate(user["organization_id"], user["id"], {
                    "property_type": "multifamily", "display_name": "Tamper", "address": "1 Tamper Rd"})
                service.create_opportunity_candidate_version(user["organization_id"], user["id"], candidate["id"], compact_evidence())
                service.screen_opportunity_candidate(user["organization_id"], user["id"], candidate["id"], {})
                with service.db.connect() as connection:
                    connection.execute("DROP TRIGGER opportunity_screening_runs_no_update")
                    connection.execute(f"UPDATE opportunity_screening_runs SET {field}={expression}")
                report = service.operational_integrity(user["organization_id"])
                self.assertFalse(report["ok"])
                self.assertEqual(report["opportunityFinder"]["screeningRunMismatches"], 1)
                if field in {"policy_id", "policy_version", "policy_sha256"}:
                    self.assertEqual(report["opportunityFinder"]["policyImplementationUnavailable"], 1)

    def test_candidate_version_link_tamper_fails_integrity(self):
        candidate = self.candidate("Link")
        first = self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], compact_evidence())
        self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], candidate["id"], {})
        second = self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], compact_evidence(rent=("999", "1000")))
        with self.service.db.connect() as connection:
            connection.execute("DROP TRIGGER opportunity_screening_runs_no_update")
            connection.execute("UPDATE opportunity_screening_runs SET candidate_version_id=? WHERE candidate_version_id=?", (second["id"], first["id"]))
        self.assertFalse(self.service.operational_integrity(self.user["organization_id"])["ok"])


if __name__ == "__main__":
    unittest.main()
