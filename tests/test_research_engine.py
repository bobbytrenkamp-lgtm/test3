from __future__ import annotations

import unittest

from test3.research import (
    create_lagged_records,
    evaluate_candidate_lags,
    fit_ols,
    market_holdout_validate,
    prepare_panel,
    regression_diagnostics,
    train_panel_candidate,
    walk_forward_validate,
)


def synthetic_panel(markets=4, periods=12):
    rows = []
    effects = {f"M{index}": index * .002 for index in range(markets)}
    for market, effect in effects.items():
        prior_driver = 0.0
        for year in range(2010, 2010 + periods):
            driver = .01 + ((year * 7 + int(market[1:]) * 3) % 11) * .001
            supply = .02 + ((year + int(market[1:])) % 3) * .003
            rent_growth = .015 + 1.5 * prior_driver - .4 * supply + effect
            rows.append({"market_id": market, "period": str(year), "property_type": "multifamily",
                         "rent_growth": rent_growth, "employment_growth": driver, "supply_growth": supply,
                         "employment_growth__available_at": str(year)})
            prior_driver = driver
    return rows


class ResearchEngineTests(unittest.TestCase):
    def test_ols_fixed_effects_clustered_inference_and_diagnostics(self):
        panel = prepare_panel(synthetic_panel(), target="rent_growth",
                              features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        model = fit_ols(panel, entity_fixed_effects=True, time_fixed_effects=False,
                        covariance="cluster_entity")
        self.assertEqual(model.diagnostics["sample_size"], 48)
        self.assertEqual(model.diagnostics["entities"], 4)
        self.assertEqual(model.covariance_type, "cluster_entity")
        self.assertIn("employment_growth", model.as_dict()["coefficients"])
        diagnostics = regression_diagnostics(panel)
        self.assertEqual(set(diagnostics["vif"]), {"employment_growth", "supply_growth"})
        self.assertIsNotNone(diagnostics["correlations"]["employment_growth"]["rent_growth"])

    def test_walk_forward_and_market_holdout_are_out_of_sample(self):
        panel = prepare_panel(synthetic_panel(), target="rent_growth",
                              features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        walk = walk_forward_validate(panel, minimum_training_periods=5)
        self.assertFalse(walk["look_ahead"])
        self.assertGreater(walk["metrics"]["model"]["sample_size"], 0)
        self.assertIn("last_observation", walk["metrics"])
        holdout = market_holdout_validate(panel)
        self.assertEqual(len(holdout["markets"]), 4)
        self.assertEqual(holdout["metrics"]["sample_size"], 48)
        self.assertFalse(holdout["entity_fixed_effects"])

    def test_model_governance_never_promotes_synthetic_data(self):
        panel = prepare_panel(synthetic_panel(periods=14), target="rent_growth",
                              features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        result = train_panel_candidate(panel, time_fixed_effects=False, minimum_training_periods=5,
                                       data_status="fictional_synthetic")
        self.assertFalse(result["governance"]["eligible_for_controlling_forecast"])
        self.assertNotEqual(result["governance"]["status"], "validated")
        self.assertEqual(result["training_data_hash"], panel.dataset_hash)
        self.assertTrue(result["walk_forward"]["metrics"]["last_observation"])

    def test_lags_use_exact_periods_and_rank_by_walk_forward_mae(self):
        rows = synthetic_panel(periods=14)
        lagged, names = create_lagged_records(rows, feature="employment_growth", lags=(1, 2))
        first_market_2011 = next(row for row in lagged if row["market_id"] == "M0" and row["period"] == "2011")
        original_2010 = next(row for row in rows if row["market_id"] == "M0" and row["period"] == "2010")
        self.assertEqual(first_market_2011[names[0]], original_2010["employment_growth"])
        findings = evaluate_candidate_lags(rows, target="rent_growth", feature="employment_growth",
                                           lags=(1, 2), minimum_training_periods=5,
                                           required_property_type="multifamily")
        self.assertEqual(findings[0]["lag"], 1)
        self.assertLessEqual(findings[0]["walk_forward"]["mae"], findings[1]["walk_forward"]["mae"])

    def test_model_failure_guards_reject_leakage_duplicates_and_mixed_property_types(self):
        rows = synthetic_panel()
        with self.assertRaisesRegex(ValueError, "target cannot"):
            prepare_panel(rows, target="rent_growth", features=("rent_growth",))
        future = [dict(row) for row in rows]
        future[0]["employment_growth__available_at"] = "2030"
        with self.assertRaisesRegex(ValueError, "future leakage"):
            prepare_panel(future, target="rent_growth", features=("employment_growth",))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prepare_panel([rows[0], rows[0]], target="rent_growth", features=("employment_growth",),
                          required_property_type="multifamily")
        mixed = [dict(rows[0]), dict(rows[1])]
        mixed[1]["property_type"] = "office"
        with self.assertRaisesRegex(ValueError, "mixed property"):
            prepare_panel(mixed, target="rent_growth", features=("employment_growth",))

    def test_missing_values_are_omitted_not_zero_filled(self):
        rows = synthetic_panel()
        rows[0] = {**rows[0], "supply_growth": None}
        panel = prepare_panel(rows, target="rent_growth", features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        self.assertEqual(panel.excluded_missing, 1)
        self.assertEqual(len(panel.rows), len(rows) - 1)


if __name__ == "__main__":
    unittest.main()
