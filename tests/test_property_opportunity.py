from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test3.opportunity import analyze_property_opportunity, parse_location_evidence, parse_sale_comps
from test3.backup import create_backup, verify_backup
from test3.research.comparables import parse_csv_records
from test3.service import Service


FIXTURES = Path(__file__).parent / "fixtures" / "opportunity"


def _inputs() -> tuple[dict, list[dict], list[dict], dict]:
    subject = {
        "address": "1 Fictional Subject", "latitude": 35.78, "longitude": -78.64,
        "property_type": "multifamily", "units": 100, "year_built": 2017,
        "purchase_price": "10000000", "renovation_budget": "500000",
        "closing_costs": "250000", "holding_costs": "250000",
    }
    rents = parse_csv_records((FIXTURES / "fictional_rent_comps.csv").read_text(encoding="utf-8"), "comps")
    sales = parse_sale_comps((FIXTURES / "fictional_sale_comps.csv").read_text(encoding="utf-8"))
    metadata = {
        "rent_comps": {"source_name": "Fictional analyst rent file", "licensing_notes": "Fictional test fixture",
                       "rights_status": "user_owned"},
        "sale_comps": {"source_name": "Fictional analyst sales file", "licensing_notes": "Fictional test fixture",
                       "rights_status": "user_owned"},
    }
    return subject, rents, sales, metadata


def _economic_inputs() -> list[dict]:
    values = {
        "purchase_price": ("10000000", "USD"),
        "renovation_budget": ("500000", "USD"),
        "closing_costs": ("250000", "USD"),
        "holding_costs": ("250000", "USD"),
        "annual_property_taxes": ("200000", "USD/year"),
        "annual_insurance": ("100000", "USD/year"),
        "annual_utilities": ("120000", "USD/year"),
        "annual_other_operating_costs": ("80000", "USD/year"),
        "vacancy_rate": ("0.05", "decimal_fraction"),
        "concessions_rate": ("0.01", "decimal_fraction"),
        "loan_amount": ("7000000", "USD"),
        "interest_rate": ("0.06", "decimal_fraction"),
        "amortization_years": ("30", "years"),
        "loan_term_years": ("10", "years"),
    }
    return [{"field": field, "value": value, "unit": unit, "source_type": "analyst_entered",
             "source_reference": f"fictional://economic-input/{field}",
             "licensing_notes": "Fictional analyst test input", "as_of_date": "2026-06-15"}
            for field, (value, unit) in values.items()]


class PropertyOpportunityTests(unittest.TestCase):
    @staticmethod
    def _test1_fixture(root: Path) -> None:
        (root / "platform_metadata.json").write_text(json.dumps({
            "_schema": "platform_metadata_v1", "_generated_at": "2026-06-01T00:00:00Z",
            "methodology_version": "fictional-1", "disclaimers": ["Fictional test data."],
        }), encoding="utf-8")
        (root / "map_data.json").write_text(json.dumps({
            "generated_at": "2026-06-01T00:00:00Z", "source_last_updated": "2026-06-01",
            "counties": {"37183": {"name": "Fictional County", "state": "NC", "level": "county",
                                      "pipeline_verified": True, "sources": []}},
        }), encoding="utf-8")

    def test_descriptive_screen_is_deterministic_traceable_and_not_underwriting(self):
        subject, rents, sales, metadata = _inputs()
        first = analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                             source_metadata=metadata, economic_inputs=_economic_inputs())
        second = analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                              source_metadata=metadata, economic_inputs=_economic_inputs())
        self.assertEqual(first["artifactHash"], second["artifactHash"])
        self.assertEqual(first["rentEvidence"]["benchmark"]["median"], "1850")
        self.assertEqual(first["rentEvidence"]["grossPotentialRentProxy"]["annual"], "2220000")
        self.assertEqual(first["saleEvidence"]["benchmark"]["impliedSubjectValueMedian"], "12500000")
        self.assertEqual(first["screeningScenarios"]["totalEstimatedBasis"], "11000000")
        self.assertEqual(first["screeningScenarios"]["cases"]["base"]["estimatedEquityWedge"], "1500000")
        self.assertTrue(first["screeningScenarios"]["notAConfidenceInterval"])
        self.assertFalse(first["governance"]["eligibleForAutomaticUnderwriting"])
        self.assertFalse(first["governance"]["test2AssumptionsOverwritten"])
        self.assertFalse(first["governance"]["scoreProduced"])
        self.assertEqual(first["quality"]["scope"], "comparable_selection_quality")
        self.assertEqual(first["readiness"]["status"], "RESEARCH_EVIDENCE_ONLY")
        self.assertFalse(first["readiness"]["analystApprovalReady"])
        self.assertEqual(first["quality"]["components"]["futureEvidenceExcluded"], 2)
        self.assertEqual(first["quality"]["components"]["staleEvidenceExcluded"], 2)

    def test_incompatible_sale_units_withhold_value_scenarios(self):
        subject, rents, sales, metadata = _inputs()
        sales[0]["price_unit"] = "USD/property"
        result = analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                              source_metadata=metadata)
        self.assertIsNone(result["saleEvidence"]["benchmark"])
        self.assertIsNone(result["screeningScenarios"])
        self.assertFalse(result["quality"]["components"]["saleUnitsConsistent"])

    def test_source_rights_and_required_fields_fail_conservatively(self):
        subject, rents, sales, metadata = _inputs()
        metadata["rent_comps"]["licensing_notes"] = ""
        with self.assertRaisesRegex(ValueError, "licensing notes"):
            analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                         source_metadata=metadata)
        metadata["rent_comps"]["licensing_notes"] = "Fictional test fixture"
        economic_inputs = _economic_inputs()
        economic_inputs[0]["value"] = "-1"
        with self.assertRaisesRegex(ValueError, "purchase_price"):
            analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                         source_metadata=metadata, economic_inputs=economic_inputs)

    def test_service_persists_immutable_candidate_and_audit_event(self):
        subject, _, _, metadata = _inputs()
        rent_text = (FIXTURES / "fictional_rent_comps.csv").read_text(encoding="utf-8")
        sale_text = (FIXTURES / "fictional_sale_comps.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as root:
            service = Service(Path(root))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            payload = {"subject": subject, "rent_comps_csv": rent_text, "sale_comps_csv": sale_text,
                       "analysis_as_of": "2026-06-30", "source_metadata": metadata}
            result = service.property_opportunity_analysis(user["organization_id"], user["id"], deal_id, payload)
            self.assertEqual(result["status"], "RESEARCH_CANDIDATE_NOT_UNDERWRITING")
            detail = service.deal(deal_id, user["organization_id"])
            self.assertEqual(detail["opportunity_runs"][0]["content_sha256"], result["artifactHash"])
            self.assertEqual(detail["opportunity_runs"][0]["status"], "research_candidate")
            with self.assertRaisesRegex(ValueError, "already exists"):
                service.property_opportunity_analysis(user["organization_id"], user["id"], deal_id, payload)
            with service.db.connect() as connection:
                run_id = result["runId"]
                with self.assertRaises(Exception):
                    connection.execute("UPDATE opportunity_runs SET status='analyst_approved' WHERE id=?", (run_id,))
                event = connection.execute(
                    "SELECT details_json FROM audit_events WHERE action='research.property_opportunity_created'"
                ).fetchone()
            self.assertEqual(json.loads(event[0])["artifact_hash"], result["artifactHash"])
            backup = Path(root) / "property-opportunity-backup.zip"
            create_backup(Path(root), backup)
            report = verify_backup(backup)
            self.assertEqual(report["counts"]["opportunity_runs"], 1)

    def test_location_evidence_and_test1_context_are_factual_local_and_governed(self):
        subject, rents, sales, metadata = _inputs()
        location_text = (FIXTURES / "fictional_location_evidence.csv").read_text(encoding="utf-8")
        location = parse_location_evidence(location_text)
        metadata["location_evidence"] = {
            "source_name": "Fictional public POI export",
            "licensing_notes": "Fictional open test fixture",
            "rights_status": "public_open",
        }
        direct = analyze_property_opportunity(
            subject, rents, sales, analysis_as_of="2026-06-30", source_metadata=metadata,
            location_evidence=location,
        )
        changed_threshold = analyze_property_opportunity(
            subject, rents, sales, analysis_as_of="2026-06-30", source_metadata=metadata,
            location_evidence=location, location_thresholds={"school": 0.1},
        )
        self.assertNotEqual(direct["analysisInputHash"], changed_threshold["analysisInputHash"])
        self.assertNotEqual(direct["artifactHash"], changed_threshold["artifactHash"])
        findings = {item["category"]: item for item in direct["locationEvidence"]["findings"]}
        self.assertEqual(findings["school"]["state"], "within_analyst_threshold")
        self.assertEqual(findings["shopping_center"]["state"], "coverage_missing")
        self.assertEqual(direct["locationEvidence"]["rejected"]["future_evidence"], 1)
        self.assertEqual(direct["locationEvidence"]["rejected"]["expired"], 1)
        self.assertEqual(direct["locationEvidence"]["rejected"]["unsupported_category"], 1)
        self.assertFalse(direct["locationEvidence"]["methodology"]["travelTimeAvailable"])
        self.assertIn("crime_or_safety", direct["locationEvidence"]["methodology"]["prohibitedInferences"])

        with tempfile.TemporaryDirectory() as root:
            data_root, test1_root = Path(root) / "app", Path(root) / "test1"
            test1_root.mkdir()
            self._test1_fixture(test1_root)
            service = Service(data_root, test1_data_dir=test1_root)
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            payload = {
                "subject": {**subject, "county_fips": "37183"},
                "rent_comps_csv": (FIXTURES / "fictional_rent_comps.csv").read_text(encoding="utf-8"),
                "sale_comps_csv": (FIXTURES / "fictional_sale_comps.csv").read_text(encoding="utf-8"),
                "location_evidence_csv": location_text,
                "analysis_as_of": "2026-06-30",
                "source_metadata": metadata,
            }
            gated = service.property_opportunity_analysis(user["organization_id"], user["id"], deal_id, payload)
            self.assertEqual(gated["test1Context"]["status"], "input_approval_required")
            assumption = service.create_assumption(
                user["organization_id"], user["id"], deal_id,
                {"field_name": "county_fips", "proposed_value": "37183", "rationale": "Fictional reviewed geography"},
            )
            service.review_assumption(user["organization_id"], user["id"], assumption["id"],
                                      "approved", "37183", "Reviewed fictional geography")
            approved = service.property_opportunity_analysis(user["organization_id"], user["id"], deal_id, payload)
            self.assertEqual(approved["test1Context"]["status"], "matched")
            self.assertEqual(approved["test1Context"]["networkRequests"], 0)
            self.assertEqual(approved["test1Context"]["results"]["countyFips"], "37183")
            self.assertEqual(approved["sources"]["location_evidence"]["fileSha256"],
                             __import__("hashlib").sha256(location_text.encode()).hexdigest())

    def test_economic_evidence_is_source_linked_partial_and_test2_advisory(self):
        subject, rents, sales, metadata = _inputs()
        without_evidence = analyze_property_opportunity(
            subject, rents, sales, analysis_as_of="2026-06-30", source_metadata=metadata,
        )
        self.assertIsNone(without_evidence["screeningScenarios"])
        self.assertNotIn("purchase_price", without_evidence["subject"])
        self.assertEqual(without_evidence["economicEvidence"]["status"], "not_provided")
        result = analyze_property_opportunity(
            subject, rents, sales, analysis_as_of="2026-06-30", source_metadata=metadata,
            economic_inputs=_economic_inputs(),
        )
        economics = result["economicEvidence"]
        self.assertEqual(economics["basis"]["totalEstimatedBasis"], "11000000")
        self.assertEqual(economics["basis"]["basisPerUnit"], "110000")
        self.assertEqual(economics["basis"]["renovationPerUnit"], "5000")
        self.assertEqual(economics["financingScreen"]["loanToBasis"],
                         "0.6363636363636363636363636364")
        self.assertFalse(economics["financingScreen"]["debtServiceCalculated"])
        self.assertEqual(economics["knownOperatingCostScreen"]["knownAnnualOperatingCosts"], "500000")
        self.assertFalse(economics["knownOperatingCostScreen"]["completeOperatingStatement"])
        self.assertEqual(economics["test2CandidateInputs"]["status"], "ADVISORY_UNAPPROVED")
        self.assertFalse(economics["test2CandidateInputs"]["automaticApply"])
        self.assertTrue(all(item["reviewStatus"] == "candidate_unapproved" for item in economics["evidence"]))

        incomplete = [item for item in _economic_inputs() if item["field"] != "holding_costs"]
        partial = analyze_property_opportunity(
            subject, rents, sales, analysis_as_of="2026-06-30", source_metadata=metadata,
            economic_inputs=incomplete,
        )
        self.assertFalse(partial["economicEvidence"]["basis"]["complete"])
        self.assertIsNone(partial["economicEvidence"]["basis"]["totalEstimatedBasis"])
        self.assertEqual(partial["economicEvidence"]["basis"]["missingComponents"], ["holding_costs"])
        self.assertIsNone(partial["screeningScenarios"])

        future = _economic_inputs()
        future[0]["as_of_date"] = "2026-07-01"
        with self.assertRaisesRegex(ValueError, "future evidence"):
            analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                         source_metadata=metadata, economic_inputs=future)


if __name__ == "__main__":
    unittest.main()
