from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from test3.cre_data.sources.sec_avb import (AVBSchemaDriftError, COMPATIBILITY,
                                            methodology_comparison_artifact, parse_avb_html,
                                            series_continuity_artifact, write_avb_series_review_csv)
from test3.research.cross_source import (company_bias, cross_source_gate, cross_source_generalization,
                                         exact_horizon_pairs)
from test3.research.test2_evidence import build_test2_assumption_evidence
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

AVB_RENT_RELIEF_FIXTURE = AVB_FIXTURE.replace(
    "<th>Q1 26</th><th>Q1 25</th><th>% Change</th></tr>",
    "<th>Q1 26</th><th>Q1 25</th><th>% Change</th><th>% Change Excluding Rent Relief</th></tr>",
).replace("<td>95,057</td><td>94,686</td><td>0.4</td></tr>",
          "<td>95,057</td><td>94,686</td><td>0.4</td><td>0.6</td></tr>")

AVB_CASH_BASIS_FIXTURE = AVB_FIXTURE.replace(
    "Average Monthly Revenue Per Occupied Home", "Average Rental Rates"
).replace(
    "<th>Q1 26</th><th>Q1 25</th><th>% Change</th></tr>",
    "<th>Q1 26</th><th>Q1 25</th><th>% Change</th><th>% Change on a Cash Basis</th></tr>",
).replace("<td>95,057</td><td>94,686</td><td>0.4</td></tr>",
          "<td>95,057</td><td>94,686</td><td>0.4</td><td>0.5</td></tr>")


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
        self.assertEqual(by_metric["average_monthly_revenue_growth_yoy"]["source_geography_role"],
                         "leaf_or_standalone")
        self.assertEqual(by_metric["average_monthly_revenue_growth_yoy"]["release_date_evidence_status"],
                         "manifest_asserted_review_required")

    def test_avb_release_date_must_match_embedded_evidence(self):
        content = "<p>For Immediate News Release April 27, 2026</p>" + AVB_FIXTURE
        result = parse_avb_html(content,
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
            filing_date="2026-04-27", retrieved_at="2026-04-28T00:00:00+00:00")
        self.assertEqual(result.observations[0]["release_date_evidence_status"],
                         "embedded_release_date_verified")
        with self.assertRaisesRegex(ValueError, "does not match embedded"):
            parse_avb_html(content,
                filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
                filing_date="2026-04-28", retrieved_at="2026-04-29T00:00:00+00:00")

    def test_avb_overlapping_rollup_is_explicitly_non_leaf(self):
        rollup = AVB_FIXTURE.replace("Boston, MA", "Metro NY/NJ")
        result = parse_avb_html(rollup,
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
            filing_date="2026-04-27", retrieved_at="2026-04-28T00:00:00+00:00")
        self.assertEqual(result.observations[0]["source_geography_role"], "overlapping_region_rollup")

    def test_avb_punctuation_alias_preserves_source_label_with_stable_identity(self):
        old = parse_avb_html(AVB_FIXTURE.replace("Boston, MA", "Oakland-East Bay, CA"),
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
            filing_date="2026-04-27")
        new = parse_avb_html(AVB_FIXTURE.replace("Boston, MA", "East Bay"),
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
            filing_date="2026-04-27")
        self.assertEqual(old.observations[0]["geography_id"], new.observations[0]["geography_id"])
        self.assertNotEqual(old.observations[0]["source_market_name"], new.observations[0]["source_market_name"])

    def test_avb_schema_drift_fails_closed(self):
        broken = AVB_FIXTURE.replace("Economic Occupancy", "Physical Occupancy")
        with self.assertRaisesRegex(AVBSchemaDriftError, "REVIEW_REQUIRED_SCHEMA_DRIFT"):
            parse_avb_html(broken,
                filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
                filing_date="2026-04-27")

    def test_avb_rent_relief_methodology_is_preserved_separately(self):
        result = parse_avb_html(AVB_RENT_RELIEF_FIXTURE,
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
            filing_date="2026-04-27")
        self.assertEqual(result.schema_version, "avb-attachment-4/rent-relief-adjusted-v1")
        by_metric = {row["metric"]: row for row in result.observations}
        self.assertEqual(by_metric["revenue_growth_yoy_excluding_rent_relief"]["value"], "0.006")
        self.assertEqual(len(result.observations), 7)

    def test_avb_legacy_cash_basis_schema_cannot_be_silently_pooled(self):
        result = parse_avb_html(AVB_CASH_BASIS_FIXTURE,
            filing_url="https://www.sec.gov/Archives/edgar/data/915912/000091591222000009/q12022ex-992.htm",
            filing_date="2026-04-27")
        self.assertEqual(result.schema_version, "avb-attachment-4/legacy-rental-rate-cash-basis-v1")
        by_metric = {row["metric"]: row for row in result.observations}
        self.assertIn("average_rental_rate_growth_yoy", by_metric)
        self.assertNotIn("average_monthly_revenue_growth_yoy", by_metric)
        self.assertEqual(by_metric["revenue_growth_yoy_cash_basis"]["value"], "0.005")
        self.assertIn(result.schema_version, by_metric["average_rental_rate"]["notes"])

    def test_series_continuity_surfaces_gaps_universe_and_schema_breaks(self):
        observations = [
            {"period": "2022-Q1", "market": "A", "metric": "average_rental_rate_growth_yoy"},
            {"period": "2022-Q1", "market": "B", "metric": "average_rental_rate_growth_yoy"},
            {"period": "2022-Q3", "market": "A", "metric": "average_monthly_revenue_growth_yoy"},
            {"period": "2022-Q3", "market": "C", "metric": "average_monthly_revenue_growth_yoy"},
        ]
        evidence = [
            {"period": "2022-Q1", "schema_version": "legacy"},
            {"period": "2022-Q3", "schema_version": "current"},
        ]
        result = series_continuity_artifact(observations, evidence)
        self.assertEqual(result["period_gaps"][0]["missing_quarters"], 1)
        self.assertEqual(result["market_transitions"][0]["added"], ["C"])
        self.assertEqual(result["market_transitions"][0]["removed"], ["B"])
        self.assertFalse(result["schema_transitions"][0]["pooling_permitted"])
        self.assertFalse(result["automatic_harmonization_permitted"])

    def test_avb_series_manifest_is_immutable_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "q1.html"; source.write_text(AVB_FIXTURE, encoding="utf-8")
            destination = Path(folder) / "review.csv"
            filing = {"path": str(source),
                      "filing_url": "https://www.sec.gov/Archives/edgar/data/915912/000091591226000010/q12026ex-992.htm",
                      "filing_date": "2026-04-27", "retrieved_at": "2026-04-28T00:00:00+00:00"}
            result = write_avb_series_review_csv([filing], destination)
            self.assertEqual(result["periods"], ["2026-Q1"])
            self.assertEqual(result["observations"], 6)
            with self.assertRaises(FileExistsError):
                write_avb_series_review_csv([filing], destination)
            with self.assertRaisesRegex(ValueError, "duplicate AVB observations"):
                write_avb_series_review_csv([filing, filing], Path(folder) / "duplicate.csv")

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
        gate = cross_source_gate(result)
        self.assertFalse(gate["passed"])
        self.assertIn("harmonization", " ".join(gate["reasons"]))

    def test_cross_source_gate_rejects_single_source(self):
        gate = cross_source_gate({"status": "INSUFFICIENT_INDEPENDENT_SOURCES", "experiments": []})
        self.assertFalse(gate["passed"])
        self.assertIn("two independently approved", gate["reasons"][0])

    def test_no_avb_metric_is_silently_directly_comparable(self):
        artifact = methodology_comparison_artifact()
        self.assertTrue(artifact["artifact_hash"])
        self.assertNotIn("directly_comparable", {row["classification"] for row in artifact["metrics"]})

    def test_exact_horizon_pairs_do_not_row_shift_across_gaps(self):
        rows = [{"market_id": "a", "period": "2024-Q1", "target": 1, "target_observation_id": "1"},
                {"market_id": "a", "period": "2024-Q3", "target": 3, "target_observation_id": "3"},
                {"market_id": "a", "period": "2025-Q1", "target": 5, "target_observation_id": "5"}]
        self.assertEqual(exact_horizon_pairs(rows, horizon=1), [])
        pairs = exact_horizon_pairs(rows, horizon=2)
        self.assertEqual([(row["forecast_origin_period"], row["target_period"]) for row in pairs],
                         [("2024-Q1", "2024-Q3"), ("2024-Q3", "2025-Q1")])

    def test_test2_evidence_is_advisory_and_requires_validated_lineage(self):
        forecast = {"status": "validated_production", "model_id": "m1", "model_version": "1",
                    "market": "m", "property_type": "multifamily", "target": "rent_growth_yoy",
                    "forecast_period": "2026-Q4", "estimate": 0.02,
                    "validation": {"walk_forward_mae": .01, "best_baseline_mae": .02,
                                   "market_holdout_mae": .015},
                    "lineage_hashes": {"target_dataset_hash": "a", "feature_panel_hash": "b",
                                       "market_definition_hash": "c", "model_result_hash": "d"}}
        evidence = build_test2_assumption_evidence(forecast)
        self.assertTrue(evidence["advisory_only"])
        self.assertFalse(evidence["test2_assumption_overwritten"])
        self.assertEqual(evidence["application_status"], "analyst_review_required")
        with self.assertRaisesRegex(ValueError, "validated_production"):
            build_test2_assumption_evidence({**forecast, "status": "candidate"})


if __name__ == "__main__":
    unittest.main()
