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
from test3.research.forecasting import create_forecast
from test3.research.reference import cross_check_statsmodels
from test3.research.specifications import MODEL_SPECIFICATIONS
from test3.features.registry import FEATURE_REGISTRY
from test3.assumptions.artifacts import validate_promotion_evidence


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
        delayed = prepare_panel(future, target="rent_growth", features=("employment_growth",))
        result = walk_forward_validate(delayed, minimum_training_periods=5,
                                       enforce_feature_availability=True)
        self.assertGreater(result["excluded_unavailable_training_features"], 0)
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

    def test_target_release_dates_are_enforced_in_walk_forward_training(self):
        rows = synthetic_panel(periods=12)
        for row in rows:
            row["rent_growth__available_at"] = row["period"]
        rows[0]["rent_growth__available_at"] = "2030-01-01"
        panel = prepare_panel(rows, target="rent_growth", features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        result = walk_forward_validate(panel, minimum_training_periods=5)
        self.assertTrue(result["target_availability_enforced"])
        self.assertGreater(result["excluded_unreleased_targets"], 0)

    def test_forecast_origin_excludes_test_period_features_released_later(self):
        rows = synthetic_panel(periods=12)
        for row in rows:
            year = int(row["period"])
            row["employment_growth__available_at"] = f"{year}-06-30"
            row["supply_growth__available_at"] = f"{year}-06-30"
            row["rent_growth__available_at"] = f"{year + 1}-01-01"
        panel = prepare_panel(rows, target="rent_growth", features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        result = walk_forward_validate(panel, minimum_training_periods=5,
                                       enforce_feature_availability=True)
        self.assertTrue(result["feature_availability_enforced"])
        self.assertEqual(result["metrics"]["model"]["sample_size"], 0)
        self.assertGreater(result["excluded_unavailable_prediction_features"], 0)
        self.assertTrue(all(item["code"] == "feature_not_available_at_forecast_origin"
                            for item in result["prediction_exclusions"]))

    def test_formal_forecast_rejects_unvalidated_model_and_uses_empirical_errors(self):
        candidate = {"governance": {"status": "candidate", "eligible_for_controlling_forecast": False}}
        with self.assertRaisesRegex(ValueError, "validated"):
            create_forecast(model_result=candidate, feature_row={}, market="M1", period="2027-Q1",
                            property_type="multifamily", target="rent_growth_yoy", data_as_of="2026-12-31")
        validated = {
            "model_id": "model-1", "model_version": "1.0", "governance": {"status": "validated", "eligible_for_controlling_forecast": True},
            "model": {"coefficients": {"intercept": .02, "employment_growth": 1.5}},
            "walk_forward": {"metrics": {"model": {"mae": .01}, "last_observation": {"mae": .02}},
                             "predictions": [{"actual": .03, "prediction": .02}, {"actual": .01, "prediction": .02}]},
            "market_holdout": {"metrics": {"mae": .015}}, "limitations": [],
        }
        forecast = create_forecast(model_result=validated, feature_row={"employment_growth": .01}, market="M1",
                                   period="2027-Q1", property_type="multifamily", target="rent_growth_yoy", data_as_of="2026-12-31")
        self.assertAlmostEqual(forecast["model"]["estimate"], .035)
        self.assertEqual(forecast["range"]["method"], "empirical_walk_forward_residual_p25_p75")
        self.assertTrue(forecast["analyst_approval_required"])

    def test_model_specifications_use_only_governed_features_and_reference_status_is_explicit(self):
        self.assertTrue(MODEL_SPECIFICATIONS)
        for specification in MODEL_SPECIFICATIONS.values():
            self.assertTrue(set(specification.features) <= set(FEATURE_REGISTRY))
        panel = prepare_panel(synthetic_panel(), target="rent_growth",
                              features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        native = fit_ols(panel, covariance="hc1")
        reference = cross_check_statsmodels(panel, native)
        self.assertIn(reference["status"], {"passed", "not_available"})
        self.assertIn("tolerances", reference)

    def test_artifact_promotion_rejects_synthetic_and_incomplete_real_evidence(self):
        with self.assertRaisesRegex(ValueError, "fictional synthetic"):
            validate_promotion_evidence({"data_status": "fictional_synthetic", "validation_state": "validated"})
        with self.assertRaisesRegex(ValueError, "promotion evidence"):
            validate_promotion_evidence({"data_status": "real", "validation_state": "validated", "model_metrics": {}})

    def test_model_result_hash_is_deterministic(self):
        panel = prepare_panel(synthetic_panel(periods=14), target="rent_growth",
                              features=("employment_growth", "supply_growth"),
                              required_property_type="multifamily")
        first = train_panel_candidate(panel, time_fixed_effects=False, minimum_training_periods=5,
                                      data_status="fictional_synthetic", code_commit="fixture")
        second = train_panel_candidate(panel, time_fixed_effects=False, minimum_training_periods=5,
                                       data_status="fictional_synthetic", code_commit="fixture")
        self.assertEqual(first["model_result_hash"], second["model_result_hash"])


if __name__ == "__main__":
    unittest.main()
