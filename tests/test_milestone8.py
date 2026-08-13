from __future__ import annotations

import unittest

from test3.cre_data.sources.sec_avb import AVBSchemaDriftError, COMPATIBILITY, methodology_comparison_artifact, parse_avb_html
from test3.research.cross_source import company_bias, cross_source_gate, cross_source_generalization
from test3.research.datasets import prepare_panel


AVB_FIXTURE = """
<table><tr><th>AvalonBay Communities, Inc.</th></tr>
<tr><th>Quarterly Residential Revenue and Occupancy Changes - Same Store</th></tr>
<tr><th>Apartment Homes</th><th>Average Monthly Revenue Per Occupied Home</th>
<th>Economic Occupancy</th><th>Residential Revenue ($000s)</th></tr>
<tr><th>Market</th><th>Apartment Homes</th><th>Q1 26</th><th>Q1 25</th><th>% Change</th>
<th>Q1 26</th><th>Q1 25</th><th>% Change</th><th>Q1 26</th><th>Q1 25</th><th>% Change</th></tr>
<tr><td>Boston, MA</td><td>9,697</td><td>3,425</td><td>3,383</td><td>1.2</td>
<td>95.4</td><td>96.2</td><td>(0.8)</td><td>95,057</td><td>94,686</td><td>0.4</td></tr>
</table>
"""


class Milestone8Tests(unittest.TestCase):
    def test_avb_parser_preserves_distinct_methodology_and_reconciles(self):
        result = parse_avb_html(AVB_FIXTURE,
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
            filing_date="2026-04-27", retrieved_at="2026-04-28T00:00:00+00:00")
        self.assertEqual(result.period, "2026-Q1")
        self.assertEqual(result.markets, 1)
        self.assertEqual(len(result.observations), 6)
        by_metric = {row["metric"]: row for row in result.observations}
        self.assertEqual(by_metric["occupancy_rate"]["methodology"], "economic_occupancy")
        self.assertEqual(by_metric["economic_vacancy_rate"]["value"], "0.046")
        self.assertEqual(by_metric["average_monthly_revenue_growth_yoy"]["value"], "0.012")
        self.assertEqual(COMPATIBILITY["average_monthly_revenue_growth_yoy"]["classification"],
                         "comparable_with_limitation")
        self.assertEqual(by_metric["average_monthly_revenue_growth_yoy"]["verification_status"], "unverified")

    def test_avb_schema_drift_fails_closed(self):
        broken = AVB_FIXTURE.replace("Economic Occupancy", "Physical Occupancy")
        with self.assertRaisesRegex(AVBSchemaDriftError, "REVIEW_REQUIRED_SCHEMA_DRIFT"):
            parse_avb_html(broken,
                filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
                filing_date="2026-04-27")

    def test_cross_source_generalization_is_bidirectional_and_auditable(self):
        rows = []
        for source, offset in (("MAA", 0.0), ("AVB", 0.01)):
            for entity_index in range(2):
                entity = f"{source.lower()}-{entity_index}"
                for quarter in range(1, 9):
                    feature = quarter / 100
                    rows.append({"market_id": entity, "period": f"202{(quarter-1)//4}-Q{(quarter-1)%4+1}",
                                 "property_type": "multifamily", "rent_growth_yoy": offset + 2 * feature,
                                 "employment_growth": feature})
        panel = prepare_panel(rows, target="rent_growth_yoy", features=("employment_growth",),
                              required_property_type="multifamily")
        source_map = {entity: entity.split("-")[0].upper() for entity in panel.entities}
        result = cross_source_generalization(panel, source_map)
        self.assertEqual(result["status"], "EVALUATED")
        self.assertEqual({(item["train_source"], item["test_source"]) for item in result["experiments"]},
                         {("AVB", "MAA"), ("MAA", "AVB")})
        self.assertTrue(result["artifact_hash"])
        self.assertEqual(len(company_bias([row for item in result["experiments"] for row in item["predictions"]])), 2)

    def test_cross_source_gate_rejects_single_source(self):
        gate = cross_source_gate({"status": "INSUFFICIENT_INDEPENDENT_SOURCES", "experiments": []})
        self.assertFalse(gate["passed"])
        self.assertIn("two independently approved", gate["reasons"][0])

    def test_no_avb_metric_is_silently_directly_comparable(self):
        artifact = methodology_comparison_artifact()
        self.assertTrue(artifact["artifact_hash"])
        self.assertNotIn("directly_comparable", {row["classification"] for row in artifact["metrics"]})


if __name__ == "__main__":
    unittest.main()
