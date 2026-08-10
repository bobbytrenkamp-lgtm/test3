from pathlib import Path
import unittest

from test3.cre_data.sources.catalog import CRE_TARGET_SOURCES
from test3.cre_data.sources.sec_maa import parse_maa_accessibility_snapshot
from test3.cre_data.verification import verify_observations


FIXTURE = Path(__file__).parent / "fixtures" / "fictional_maa_snapshot.txt"


class Milestone6Tests(unittest.TestCase):
    def test_maa_snapshot_extracts_source_reported_outcomes_without_approval(self):
        result = parse_maa_accessibility_snapshot(
            FIXTURE.read_text(encoding="utf-8"),
            filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
            filing_date="2025-07-30",
            retrieved_at="2026-08-09T12:00:00+00:00",
        )
        self.assertEqual(result.period, "2025-Q2")
        self.assertEqual((result.effective_rent_rows, result.rent_growth_rows, result.occupancy_rows, result.vacancy_rows), (1, 1, 1, 1))
        values = {row["metric"]: row["value"] for row in result.observations}
        self.assertEqual(values, {
            "effective_rent": "1500", "rent_growth_yoy": "0.034",
            "occupancy_rate": "0.955", "vacancy_rate": "0.045",
        })
        checked = verify_observations(list(result.observations), analyst_review_confirmed=False)
        self.assertEqual(checked["summary"]["model_eligible"], 0)
        self.assertEqual(checked["summary"]["unverified"], 4)

    def test_sec_maa_source_is_real_target_but_local_only(self):
        source = CRE_TARGET_SOURCES["sec_maa_same_store"]
        self.assertEqual(source.target_classification, "institutional_target")
        self.assertFalse(source.requires_payment)
        self.assertTrue(source.automation_permitted)
        self.assertEqual(source.redistribution_permitted, "no")

    def test_maa_parser_accepts_governed_2026_heading_drift(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace(
            "QUARTER OVER QUARTER COMPARISONS", "QUARTERLY COMPARISONS"
        ).replace("SEQUENTIAL QUARTER COMPARISONS", "SEQUENTIAL QUARTERLY COMPARISONS")
        result = parse_maa_accessibility_snapshot(
            snapshot,
            filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
            filing_date="2025-07-30",
        )
        self.assertEqual(result.rent_growth_rows, 1)

    def test_maa_parser_fails_when_reported_growth_disagrees_with_rent_levels(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace("1,450 3.4 %", "1,450 9.9 %")
        with self.assertRaisesRegex(ValueError, "rent-growth cross-check failed"):
            parse_maa_accessibility_snapshot(
                snapshot,
                filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                filing_date="2025-07-30",
            )
