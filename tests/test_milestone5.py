from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from io import BytesIO
import tempfile
import unittest

from openpyxl import Workbook

from test3.assumptions.model_recommendation import recommend_from_model
from test3.cre_data.candidates import approve_document_candidates, save_document_candidates
from test3.cre_data.geography import MarketDefinition, market_definitions, save_market_definition
from test3.cre_data.mappings import ImportMappingTemplate, apply_mapping, load_mapping, save_mapping
from test3.cre_data.schema import normalize_cre_record, parse_cre_file
from test3.cre_data.sources import CRE_TARGET_SOURCES
from test3.cre_data.verification import verify_observations
from test3.research.datasets import prepare_panel
from test3.research.governance import ValidationPolicy, assess_model
from test3.research.specifications import MODEL_SPECIFICATIONS, ModelSpecification
from test3.research.target_panel import target_readiness_for_specification
from test3.warehouse.storage import WarehousePaths


def _panel(markets: int, periods: int):
    rows = []
    for market in range(markets):
        for period in range(periods):
            rows.append({"market": f"M{market}", "period": str(2000 + period),
                         "target": .01 + market * .001 + period * .0001, "feature": period + market})
    return prepare_panel(rows, target="target", features=("feature",), entity_column="market")


def _passed_validation():
    return ({"look_ahead": False, "model_beats_best_baseline": True,
             "metrics": {"model": {"sample_size": 10}}},
            {"metrics": {"sample_size": 10}})


def _spec(**changes):
    base = ModelSpecification("governed_test", "1", "target", "multifamily", "annual", ("feature",),
                              False, False, "hc1", 100, 5, 20, "fixture")
    return replace(base, **changes)


def _governance(panel, spec, **changes):
    walk, holdout = _passed_validation()
    values = dict(source_manifest_hashes=("source",), data_status="real",
                  policy=ValidationPolicy.from_model_specification(spec),
                  python_reference={"status": "passed"}, r_reference={"status": "not_available"},
                  target_dataset_hashes=("target",), feature_table_hash="feature",
                  model_mode="validated_production", model_specification=spec)
    values.update(changes)
    return assess_model(panel, walk, holdout, **values)


def _raw(period="2024-Q1", methodology="market_vacancy"):
    return {"market": "Test Market", "geography_type": "market", "geography_id": "test-market",
            "cbsa": "99999", "period": period, "frequency": "quarterly", "property_type": "multifamily",
            "property_subtype": "market_rate", "metric": "vacancy_rate", "value": ".05",
            "unit": "decimal_fraction", "source_name": "Test Source", "source_identifier": "fixture://source",
            "source_period": period, "release_date": f"{period[:4]}-{int(period[-1]) * 3:02d}-28",
            "retrieved_at": "2026-08-09", "methodology": methodology, "vintage": "original",
            "licensing_notes": "Fictional test evidence.", "redistribution_permitted": "no",
            "verification_status": "analyst_verified", "source_class": "analyst_owned"}


class Milestone5GovernanceTests(unittest.TestCase):
    def test_model_specification_controls_all_three_minimums(self):
        result = _governance(_panel(5, 12), _spec())
        self.assertIn("sample size 60 is below 100", result["failures"])
        result = _governance(_panel(4, 30), _spec())
        self.assertIn("market count 4 is below 5", result["failures"])
        result = _governance(_panel(6, 19), _spec())
        self.assertIn("period count 19 is below 20", result["failures"])

    def test_promotion_requires_longitudinal_depth_in_each_required_market(self):
        records = []
        for market in range(5):
            for period in range(4):
                records.append({"market": f"M{market}", "period": str(2000 + market * 4 + period),
                                "target": .01, "feature": 1.0})
        panel = prepare_panel(records, target="target", features=("feature",), entity_column="market")
        result = _governance(panel, _spec(minimum_sample=20))
        self.assertIn("markets meeting 20-period depth 0 is below 5", result["failures"])

    def test_generic_real_research_cannot_become_controlling(self):
        walk, holdout = _passed_validation()
        result = assess_model(_panel(5, 20), walk, holdout, data_status="real",
                              source_manifest_hashes=("source",), target_dataset_hashes=("target",),
                              feature_table_hash="feature", python_reference={"status": "passed"},
                              r_reference={"status": "not_available"})
        self.assertEqual(result["status"], "research")
        self.assertFalse(result["eligible_for_controlling_forecast"])

    def test_cross_check_failures_block_but_optional_missing_r_is_disclosed(self):
        panel, spec = _panel(5, 20), _spec()
        allowed = _governance(panel, spec)
        self.assertNotIn("R cross-check failed", allowed["failures"])
        failed_r = _governance(panel, spec, r_reference={"status": "failed"})
        self.assertIn("R cross-check failed", failed_r["failures"])
        failed_python = _governance(panel, spec, python_reference={"status": "failed"})
        self.assertIn("independent Python reference validation did not pass", failed_python["failures"])

    def test_readiness_is_model_specific(self):
        with tempfile.TemporaryDirectory() as root:
            result = target_readiness_for_specification(WarehousePaths.from_data_root(root),
                                                        MODEL_SPECIFICATIONS["mf_rent_growth_combined"])
        self.assertEqual(result["model_specification"], "mf_rent_growth_combined")
        self.assertEqual(result["policy"], {"minimum_markets": 5, "minimum_periods": 20,
                                             "minimum_observations": 100})
        self.assertEqual(result["status"], "not_ready")
        expense = MODEL_SPECIFICATIONS["mf_operating_expense_growth_macro"]
        self.assertEqual(expense.target, "operating_expense_growth_yoy")
        self.assertEqual(expense.features, ("cpi_growth_yoy", "personal_income_growth_yoy"))

    def test_recommendation_policy_is_versioned_deterministic_and_quality_aware(self):
        historical = {"median": ".03", "q1": ".01", "q3": ".05"}
        weak = {"model": {"estimate": .06}, "range": {"low": .02, "high": .07},
                "validation": {"walk_forward_mae": .019, "baseline_mae": .02, "market_holdout_mae": .04}}
        strong = {**weak, "validation": {"walk_forward_mae": .005, "baseline_mae": .02, "market_holdout_mae": .006}}
        first = recommend_from_model(historical=historical, recent=Decimal(".04"), forecast=weak)
        repeated = recommend_from_model(historical=historical, recent=Decimal(".04"), forecast=weak)
        better = recommend_from_model(historical=historical, recent=Decimal(".04"), forecast=strong)
        self.assertEqual(first, repeated)
        self.assertEqual((first["recommendation_policy_id"], first["recommendation_policy_version"]),
                         ("mf-rent-growth", "1.0.0"))
        self.assertNotEqual(first["policy"]["model_weight"], better["policy"]["model_weight"])


class Milestone5TargetDataTests(unittest.TestCase):
    def test_source_registry_never_mislabels_proxies_as_targets(self):
        self.assertEqual(CRE_TARGET_SOURCES["census_hvs"].target_classification, "residential_proxy")
        self.assertEqual(CRE_TARGET_SOURCES["hud_fmr"].target_classification, "market_proxy")
        self.assertEqual(CRE_TARGET_SOURCES["user_owned_cre_history"].target_classification, "institutional_target")
        self.assertFalse(any(item.requires_payment for item in CRE_TARGET_SOURCES.values()))

    def test_saved_mapping_requires_exact_schema_and_parses_xlsx(self):
        template = ImportMappingTemplate("fixture", "1", ("Market", "Quarter", "Vacancy"),
            {"Market": "market", "Quarter": "period", "Vacancy": "value"},
            {**_raw(), "market": None, "period": None, "source_period": "2024-Q1", "value": None},
            "Test Source", "Fictional local-only fixture")
        with tempfile.TemporaryDirectory() as root:
            saved = save_mapping(WarehousePaths.from_data_root(root), template)
            loaded = load_mapping(saved)
            self.assertEqual(loaded, template)
        workbook = Workbook(); sheet = workbook.active
        sheet.append(["Market", "Quarter", "Vacancy"]); sheet.append(["Test Market", "2024-Q1", .05])
        stream = BytesIO(); workbook.save(stream)
        parsed, errors, metadata = parse_cre_file(stream.getvalue(), suffix=".xlsx", mapping=template)
        self.assertFalse(errors); self.assertEqual(parsed[0]["value"], "0.05"); self.assertEqual(metadata["format"], "xlsx")
        with self.assertRaisesRegex(ValueError, "exactly match"):
            apply_mapping([{"Wrong": 1}], template)

    def test_market_definitions_are_versioned_and_weighted(self):
        definition = MarketDefinition("test-market", "Test Market", "multifamily", "Analyst-defined fixture",
                                      "2024-01-01", None, ({"county_fips": "37183", "cbsa": "39580", "weight": ".6"},
                                                            {"county_fips": "37063", "cbsa": "39580", "weight": ".4"}))
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root); first = save_market_definition(paths, definition)
            second = save_market_definition(paths, definition)
            self.assertEqual(first, second); self.assertEqual(market_definitions(paths)[0]["market_id"], "test-market")
        with self.assertRaisesRegex(ValueError, "total one"):
            replace(definition, counties=({"county_fips": "37183", "weight": ".9"},)).validate()

    def test_methodology_change_and_unknown_market_block_model_eligibility(self):
        rows = [normalize_cre_record(_raw(), row_number=2),
                normalize_cre_record(_raw("2024-Q2", "economic_vacancy"), row_number=3)]
        checked = verify_observations(rows, analyst_review_confirmed=True,
                                      governed_market_ids=frozenset({"different-market"}))
        codes = {item["code"] for item in checked["findings"]}
        self.assertTrue({"methodology_change", "market_geography_mismatch"} <= codes)
        self.assertEqual(checked["summary"]["model_eligible"], 0)

    def test_document_candidates_cannot_detach_evidence_or_self_approve(self):
        digest = "a" * 64
        candidate = {"status": "candidate", "observation": _raw(), "evidence": {
            "document_sha256": digest, "page": 4, "table": 2, "row": 3, "column": 5,
            "original_label": "Vac %", "original_value": "5.0%"}}
        with tempfile.TemporaryDirectory() as root:
            path = save_document_candidates(WarehousePaths.from_data_root(root), document_sha256=digest,
                                            candidates=[candidate])
            approved = approve_document_candidates(path, approved_indexes=(0,), analyst_rationale="Checked against table")
        self.assertEqual(approved[0]["verification_status"], "analyst_verified")
        self.assertIn("page=4", approved[0]["source_identifier"])
        with self.assertRaisesRegex(ValueError, "detached"):
            save_document_candidates(WarehousePaths.from_data_root(tempfile.mkdtemp()), document_sha256=digest,
                                     candidates=[{**candidate, "evidence": {}}])


if __name__ == "__main__":
    unittest.main()
