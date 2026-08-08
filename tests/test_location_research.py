from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test3.research.comparables import analyze_location, distance_miles, parse_csv_records
from test3.service import Service

FIXTURES = Path(__file__).parent / "fixtures" / "location"


class LocationResearchTests(unittest.TestCase):
    def rows(self):
        comps = parse_csv_records((FIXTURES / "fictional_rent_comps.csv").read_text(encoding="utf-8"), "comps")
        pois = parse_csv_records((FIXTURES / "fictional_pois.csv").read_text(encoding="utf-8"), "pois")
        return comps, pois

    def test_distance_similarity_rents_and_area_evidence(self):
        comps, pois = self.rows()
        result = analyze_location({"address": "1 Fictional Subject", "latitude": 35.78, "longitude": -78.64,
                                   "property_type": "multifamily", "units": 200, "year_built": 2017}, comps, pois)
        self.assertEqual([row["address"] for row in result["rentComparables"]], ["10 Fictional Oak Street", "20 Fictional Pine Street"])
        self.assertEqual(result["rentBenchmark"], {"count": 2, "rentUnit": "USD/unit/month", "minimum": "1775", "median": "1812.5", "maximum": "1850"})
        self.assertGreater(distance_miles(35.78, -78.64, 35.79, -78.65), 0)
        self.assertIn("school", {row["factor"] for row in result["areaPositives"]})
        self.assertIn("hospital", {row["factor"] for row in result["areaConsiderations"]})
        self.assertEqual(result["rejectedComparables"]["property_type_mismatch"], 1)
        self.assertEqual(result["rejectedComparables"]["outside_radius"], 1)

    def test_missing_poi_is_disclosed_not_treated_as_absence(self):
        comps, _ = self.rows()
        result = analyze_location({"latitude": 35.78, "longitude": -78.64, "property_type": "multifamily"}, comps, [])
        self.assertTrue(all("absence is not proof" in row["statement"] for row in result["areaConsiderations"]))

    def test_service_is_deal_scoped_audited_and_hashes_inputs(self):
        comps = (FIXTURES / "fictional_rent_comps.csv").read_text(encoding="utf-8")
        pois = (FIXTURES / "fictional_pois.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as root:
            service = Service(Path(root))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            result = service.location_analysis(user["organization_id"], user["id"], deal_id,
                {"subject": {"latitude": 35.78, "longitude": -78.64, "units": 200, "year_built": 2017}, "comps_csv": comps, "pois_csv": pois})
            self.assertEqual(len(result["provenance"]["compsFileSha256"]), 64)
            with service.db.connect() as connection:
                event = connection.execute("SELECT action,details_json FROM audit_events WHERE action='research.location_analysis'").fetchone()
            self.assertIsNotNone(event)

    def test_bad_coordinates_and_incompatible_units_fail_safely(self):
        comps, pois = self.rows()
        with self.assertRaisesRegex(ValueError, "outside"):
            analyze_location({"latitude": 100, "longitude": 0, "property_type": "multifamily"}, comps, pois)
        mixed = [dict(comps[0]), {**comps[1], "rent_unit": "USD/sf/year"}]
        result = analyze_location({"latitude": 35.78, "longitude": -78.64, "property_type": "multifamily"}, mixed, pois)
        self.assertIsNone(result["rentBenchmark"], "incompatible rent units must never be pooled")
