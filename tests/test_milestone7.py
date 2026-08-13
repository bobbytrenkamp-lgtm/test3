from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from test3.cre_data.geography import MarketDefinition, save_market_definition
from test3.research.governance import ValidationPolicy, assess_model
from test3.research.milestone7 import analyst_attestation_status, feature_compatibility, market_definition_coverage
from test3.research.specifications import MODEL_SPECIFICATIONS, ModelSpecification
from test3.research.datasets import prepare_panel
from test3.warehouse.storage import WarehousePaths


def _candidate_report(paths: WarehousePaths) -> None:
    destination = paths.contained(Path("verification/cre/dataset=maa/version=v1/verification.json"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        "dataset_id": "maa", "source_version": "v1", "created_at": "2026-08-13T00:00:00Z",
        "observations": [{"source_name": "Mid-America Apartment Communities SEC supplemental",
                          "property_type": "multifamily", "geography_id": "maa-atlanta-ga",
                          "verification_status": "unverified", "period": "2025-Q2"}],
    }), encoding="utf-8")


class Milestone7Tests(unittest.TestCase):
    def test_candidate_data_stops_at_awaiting_human_attestation(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root); _candidate_report(paths)
            status = analyst_attestation_status(paths)
            self.assertEqual(status["status"], "AWAITING_ANALYST_ATTESTATION")
            self.assertEqual(status["approved_observations"], 0)

    def test_market_definition_requires_exact_nonduplicated_weights(self):
        base = MarketDefinition("maa-atlanta-ga", "Atlanta", "multifamily", "Source boundary", "2020-01-01", None,
                                ({"county_fips": "13089", "weight": ".5"},
                                 {"county_fips": "13121", "weight": ".5"}))
        with self.assertRaisesRegex(ValueError, "total one exactly"):
            replace(base, counties=({"county_fips": "13089", "weight": ".999999"},)).validate()
        with self.assertRaisesRegex(ValueError, "repeat"):
            replace(base, counties=({"county_fips": "13089", "weight": ".5"},
                                    {"county_fips": "13089", "weight": ".5"})).validate()

    def test_draft_market_definition_is_visible_but_not_feature_eligible(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root); _candidate_report(paths)
            save_market_definition(paths, MarketDefinition(
                "maa-atlanta-ga", "Atlanta", "multifamily", "Draft boundary", "2020-01-01", None,
                ({"county_fips": "13089", "weight": "1"},), source_market_name="Atlanta"))
            item = market_definition_coverage(paths)[0]
            self.assertFalse(item["feature_eligible"])
            self.assertIn("not analyst approved", item["reason_if_excluded"])

    def test_forecast_specification_rejects_future_time_effect(self):
        with self.assertRaisesRegex(ValueError, "future time fixed effects"):
            ModelSpecification("bad", "1", "rent_growth_yoy", "multifamily", "quarterly", (),
                               True, True, "cluster_entity", purpose="forecast")
        self.assertTrue(all(not spec.time_fixed_effects for spec in MODEL_SPECIFICATIONS.values()
                            if spec.purpose == "forecast"))

    def test_inference_specification_cannot_validate_as_forward_model(self):
        rows = [{"market": f"M{market}", "period": str(2000 + period), "target": period, "feature": period + market}
                for market in range(5) for period in range(20)]
        panel = prepare_panel(rows, target="target", features=("feature",), entity_column="market")
        spec = ModelSpecification("inference", "1", "target", "multifamily", "annual", ("feature",),
                                  True, True, "cluster_entity", 100, 5, 20, "fixture")
        result = assess_model(panel, {"look_ahead": False, "model_beats_best_baseline": True,
                                      "metrics": {"model": {"sample_size": 10}}},
                              {"metrics": {"sample_size": 10}}, data_status="real",
                              source_manifest_hashes=("s",), target_dataset_hashes=("t",),
                              feature_table_hash="f", python_reference={"status": "passed"},
                              r_reference={"status": "not_available"}, model_mode="validated_production",
                              model_specification=spec, policy=ValidationPolicy.from_model_specification(spec))
        self.assertIn("inference-only specifications", " ".join(result["failures"]))
        self.assertFalse(result["eligible_for_controlling_forecast"])

    def test_feature_compatibility_discloses_annual_carry_forward(self):
        rows = feature_compatibility(MODEL_SPECIFICATIONS["mf_rent_growth_demand_forecast"])
        population = next(item for item in rows if item["feature"] == "population_growth_yoy")
        self.assertTrue(population["eligible"])
        self.assertIn("annual carry-forward", population["transformation"])


if __name__ == "__main__":
    unittest.main()
