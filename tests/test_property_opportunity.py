from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test3.opportunity import analyze_property_opportunity, parse_sale_comps
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


class PropertyOpportunityTests(unittest.TestCase):
    def test_descriptive_screen_is_deterministic_traceable_and_not_underwriting(self):
        subject, rents, sales, metadata = _inputs()
        first = analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                             source_metadata=metadata)
        second = analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                              source_metadata=metadata)
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
        subject["purchase_price"] = "-1"
        metadata["rent_comps"]["licensing_notes"] = "Fictional test fixture"
        with self.assertRaisesRegex(ValueError, "purchase_price"):
            analyze_property_opportunity(subject, rents, sales, analysis_as_of="2026-06-30",
                                         source_metadata=metadata)

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


if __name__ == "__main__":
    unittest.main()
