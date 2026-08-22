from __future__ import annotations

import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from test3.api import Handler, ThreadingHTTPServer
from test3.auth import SigninLimiter, hash_password
from test3.backup import create_backup, verify_backup
from test3.db import now
from test3.permissions import require
from test3.service import Service


HASH = "a" * 64


def evidence(**updates):
    value = {
        "analysis_as_of": "2026-06-30",
        "subject_rent": "1000.00", "market_rent": "1125.00", "rent_unit": "USD/unit/month",
        "acquisition_basis": "150000.00", "comparable_sale_basis": "170000.00", "basis_unit": "USD/unit",
        "current_noi": "1000000.00", "stabilized_noi": "1100000.00",
        "subject_cap_rate": "0.0600", "market_cap_rate": "0.0525",
        "subject_vacancy": "0.0800", "market_vacancy": "0.0500",
        "rent_comp_count": 3, "sale_comp_count": 2, "location_evidence_complete": True,
        "evidence_hashes": {item: [HASH] for item in ("rent", "basis", "noi", "cap_rate", "vacancy", "comparables", "location")},
        "evidence_dates": {item: "2026-06-01" for item in ("rent", "basis", "noi", "cap_rate", "vacancy", "comparables", "location")},
    }
    value.update(updates)
    return value


class OpportunityPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.temp.name))
        self.user = self.service.seed()

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, **updates):
        payload = {"property_type": "multifamily", "display_name": "Fictional Lakes",
                   "address": "1 Example Street", "market": "Raleigh", "origin_type": "manual"}
        payload.update(updates)
        return self.service.create_opportunity_candidate(self.user["organization_id"], self.user["id"], payload)

    def test_lifecycle_is_immutable_lossless_and_auditable(self):
        candidate = self.candidate()
        self.assertIsNone(candidate["deal_id"])
        self.assertFalse(candidate["deal_created"])
        version = self.service.create_opportunity_candidate_version(
            self.user["organization_id"], self.user["id"], candidate["id"], evidence())
        self.assertEqual(version["content"]["inputs"]["subject_rent"], "1000.00")
        run = self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], candidate["id"], {})
        self.assertEqual(run["result"]["screeningTier"], "HIGH_PRIORITY_REVIEW")
        self.assertEqual(run["result"]["evidenceFreshnessDays"], 29)
        self.assertEqual(run["result"]["evidenceFreshnessDetail"]["newestEvidenceAgeDays"], 29)
        detail = self.service.opportunity_candidate(self.user["organization_id"], candidate["id"])
        self.assertEqual(len(detail["versions"]), 1)
        self.assertEqual(len(detail["screening_runs"]), 1)
        history = self.service.opportunity_candidate_history(self.user["organization_id"], candidate["id"])
        self.assertEqual([item["type"] for item in history["timeline"]],
                         ["candidate_created", "evidence_version_created", "screening_run_created"])
        with self.service.db.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE opportunity_candidate_versions SET version=2 WHERE id=?", (version["id"],))
            actions = {row[0] for row in connection.execute("SELECT action FROM audit_events")}
        self.assertTrue({"opportunity.candidate_created", "opportunity.candidate_version_created", "opportunity.screened"} <= actions)

    def test_client_results_float_precision_future_date_and_duplicates_are_rejected(self):
        candidate = self.candidate()
        with self.assertRaisesRegex(ValueError, "server-derived"):
            self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"],
                                                              {**evidence(), "screeningTier": "HIGH_PRIORITY_REVIEW"})
        with self.assertRaisesRegex(ValueError, "JSON float"):
            self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"],
                                                              evidence(subject_rent=1000.01))
        self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], evidence())
        with self.assertRaisesRegex(ValueError, "exact"):
            self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], evidence())
        future = self.candidate(display_name="Future", address="2 Example Street")
        with self.assertRaisesRegex(ValueError, "cannot be after"):
            self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], future["id"], evidence(analysis_as_of="2099-01-01"))
        duplicate = self.candidate(display_name="Same normalized address", address="  1  EXAMPLE street ")
        self.assertEqual(duplicate["warnings"], ["POSSIBLE_DUPLICATE_CANDIDATE"])

    def test_organization_scope_filters_pagination_and_latest_screening(self):
        first = self.candidate()
        second = self.candidate(display_name="Other", address="2 Main", market="Charlotte")
        for item in (first, second):
            self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], item["id"], evidence())
            self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], item["id"], {})
        page = self.service.list_opportunity_candidates(self.user["organization_id"], {"market": "Raleigh", "limit": 1,
                                                                                       "sort": "evidence_completeness", "direction": "desc"})
        self.assertEqual((page["pagination"]["total"], len(page["items"])), (1, 1))
        self.assertEqual(page["items"][0]["current_screening"]["screening_tier"], "HIGH_PRIORITY_REVIEW")
        with self.assertRaises(LookupError):
            self.service.opportunity_candidate("different-organization", first["id"])
        with self.assertRaises(ValueError):
            self.service.list_opportunity_candidates(self.user["organization_id"], {"sort": "drop table"})

    def test_concurrent_version_numbers_are_unique_and_sequential(self):
        candidate = self.candidate()
        errors = []
        def create(index):
            try:
                self.service.create_opportunity_candidate_version(
                    self.user["organization_id"], self.user["id"], candidate["id"],
                    evidence(subject_rent=str(1000 + index)))
            except Exception as error:  # pragma: no cover - assertion reports unexpected concurrency errors
                errors.append(error)
        workers = [threading.Thread(target=create, args=(index,)) for index in range(8)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(errors, [])
        detail = self.service.opportunity_candidate(self.user["organization_id"], candidate["id"])
        self.assertEqual([item["version"] for item in detail["versions"]], list(range(1, 9)))

    def test_integrity_detects_tamper_and_backup_contains_new_evidence(self):
        candidate = self.candidate()
        version = self.service.create_opportunity_candidate_version(self.user["organization_id"], self.user["id"], candidate["id"], evidence())
        self.service.screen_opportunity_candidate(self.user["organization_id"], self.user["id"], candidate["id"], {})
        archive = Path(self.temp.name) / "opportunities.zip"
        create_backup(Path(self.temp.name), archive)
        report = verify_backup(archive)
        self.assertEqual(report["format"], "test3-backup/10.0")
        self.assertEqual(report["counts"]["opportunity_candidate_versions"], 1)
        with self.service.db.connect() as connection:
            connection.execute("DROP TRIGGER opportunity_candidate_versions_no_update")
            connection.execute("UPDATE opportunity_candidate_versions SET content_sha256=? WHERE id=?", ("0" * 64, version["id"]))
        integrity = self.service.operational_integrity(self.user["organization_id"])
        self.assertFalse(integrity["ok"])
        self.assertEqual(integrity["opportunityFinder"]["versionMismatches"], 1)

    def test_permissions_are_separate_from_review(self):
        require("analyst", "opportunity.create")
        require("analyst", "opportunity.screen")
        require("analyst", "opportunity.archive")
        with self.assertRaises(PermissionError): require("reviewer", "opportunity.create")
        with self.assertRaises(PermissionError): require("reviewer", "opportunity.screen")
        with self.assertRaises(PermissionError): require("reviewer", "opportunity.archive")
        require("reviewer", "opportunity.review")


class OpportunityApiTests(unittest.TestCase):
    def test_http_lifecycle_and_reviewer_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            Handler.service = Service(Path(temporary)); admin = Handler.service.seed()
            with Handler.service.db.connect() as connection:
                reviewer_id = "reviewer-id"
                connection.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (reviewer_id, admin["organization_id"],
                                   "reviewer@example.test", "Review Person", "reviewer", hash_password("reviewer-password"), now()))
            Handler.signin_limiter = SigninLimiter(); Handler.signin_address_limiter = SigninLimiter(max_failures=20)
            Handler.secure_cookie = False
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            def signin(email, password):
                connection.request("POST", "/api/signin", json.dumps({"email": email, "password": password}), {"Content-Type": "application/json"})
                response = connection.getresponse(); body = json.loads(response.read())
                cookie = response.getheader("Set-Cookie").split(";", 1)[0]
                connection.request("GET", "/api/bootstrap", headers={"Cookie": cookie})
                bootstrap = json.loads(connection.getresponse().read())
                return cookie, bootstrap["user"]["csrf_token"]
            def request(method, path, cookie, csrf=None, payload=None):
                headers = {"Cookie": cookie, "Content-Type": "application/json"}
                if csrf: headers["X-CSRF-Token"] = csrf
                connection.request(method, path, json.dumps(payload) if payload is not None else None, headers)
                response = connection.getresponse(); return response.status, json.loads(response.read())
            try:
                cookie, csrf = signin("analyst@example.test", "fictional-demo")
                status, candidate = request("POST", "/api/opportunities", cookie, csrf,
                                            {"property_type": "multifamily", "display_name": "API Candidate", "address": "3 Main"})
                self.assertEqual(status, 201)
                self.assertEqual(request("POST", f"/api/opportunities/{candidate['id']}/versions", cookie, csrf, evidence())[0], 201)
                self.assertEqual(request("POST", f"/api/opportunities/{candidate['id']}/versions", cookie, csrf, evidence())[0], 409)
                self.assertEqual(request("POST", f"/api/opportunities/{candidate['id']}/screen", cookie, csrf, {})[0], 201)
                listing = request("GET", "/api/opportunities?limit=1&sort=screening_tier", cookie)[1]
                self.assertEqual(listing["pagination"]["total"], 1)
                self.assertEqual(listing["items"][0]["screening_currency_status"], "CURRENT")
                self.assertIsInstance(listing["items"][0]["rent_gap_pct"], str)
                self.assertEqual(request("GET", f"/api/opportunities/{candidate['id']}", cookie)[1]["candidate"]["id"], candidate["id"])
                self.assertEqual(len(request("GET", f"/api/opportunities/{candidate['id']}/history", cookie)[1]["timeline"]), 3)
                status, artifact = request("POST", f"/api/opportunities/{candidate['id']}/review-artifacts", cookie, csrf, {})
                self.assertEqual(status, 201)
                self.assertFalse(artifact["content"]["candidate"]["deal_id"])
                reviewer_cookie, reviewer_csrf = signin("reviewer@example.test", "reviewer-password")
                self.assertEqual(request("GET", "/api/opportunities", reviewer_cookie)[0], 200)
                review_items = request("GET", "/api/opportunity-candidate-review-artifacts", reviewer_cookie)[1]["items"]
                self.assertEqual(review_items[0]["id"], artifact["id"])
                status, decision = request("POST", f"/api/opportunity-candidate-review-artifacts/{artifact['id']}/review",
                                           reviewer_cookie, reviewer_csrf,
                                           {"decision": "approved", "rationale": "Independent API evidence review completed.",
                                            "acknowledgements": {"evidence_reviewed": True, "source_rights_reviewed": True,
                                                                 "limitations_acknowledged": True, "test2_advisory_only": True}})
                self.assertEqual((status, decision["decision"], decision["automatic_deal_creation"]), (201, "approved", False))
                self.assertEqual(request("POST", "/api/opportunities", reviewer_cookie, reviewer_csrf,
                                         {"property_type": "multifamily", "display_name": "Denied"})[0], 401)
                self.assertEqual(request("POST", f"/api/opportunities/{candidate['id']}/archive", reviewer_cookie, reviewer_csrf, {})[0], 401)
                archived = request("POST", f"/api/opportunities/{candidate['id']}/archive", cookie, csrf, {})
                self.assertEqual((archived[0], archived[1]["status"]), (200, "archived"))
                self.assertEqual(request("GET", f"/api/opportunities/{candidate['id']}", cookie)[1]["candidate"]["status"], "archived")
                self.assertEqual(len(request("GET", f"/api/opportunities/{candidate['id']}/history", cookie)[1]["timeline"]), 4)
            finally:
                connection.close(); server.shutdown(); server.server_close(); worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
