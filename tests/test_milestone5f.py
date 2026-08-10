from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test3.cre_data.audit import coverage_matrix, target_data_audit, target_readiness_funnel
from test3.cre_data.derivations import derive_rent_growth_yoy, derive_vacancy_from_occupancy
from test3.cre_data.report_inbox import save_report_discovery
from test3.cre_data.report_tables import (ReportMappingProfile, extract_table_candidates,
                                          load_report_profile, save_report_profile)
from test3.cre_data.schema import normalize_cre_record
from test3.cre_data.sources import discovery_catalog
from test3.warehouse.storage import WarehousePaths


def _raw(*, period="2024-Q1", metric="asking_rent", value="1600", unit="USD_per_unit_month",
         methodology="asking_rent"):
    return {"market": "Test Market", "geography_type": "market", "geography_id": "test-market", "cbsa": "99999",
            "period": period, "frequency": "quarterly", "property_type": "multifamily", "property_subtype": "market_rate",
            "metric": metric, "value": value, "unit": unit, "source_name": "Test Source",
            "source_identifier": f"fixture://{period}/{metric}", "source_period": period, "release_date": f"{period[:4]}-12-31",
            "retrieved_at": "2026-08-09", "methodology": methodology, "vintage": "original",
            "licensing_notes": "Fictional local-only fixture.", "redistribution_permitted": "no",
            "verification_status": "analyst_verified", "source_class": "analyst_owned",
            "target_classification": "institutional_target"}


class Milestone5FTests(unittest.TestCase):
    def test_source_ranking_keeps_proxies_separate(self):
        catalog = discovery_catalog()
        self.assertEqual(catalog[0]["source_id"], "user_owned_history")
        classes = {row["source_id"]: row["classification"] for row in catalog}
        self.assertEqual(classes["freddie_aimi"], "market_proxy")
        self.assertEqual(classes["zillow_zori"], "market_proxy")
        self.assertTrue(all("paid" not in row["access"].lower() for row in catalog))

    def test_report_inbox_hashes_groups_and_finds_missing_quarter(self):
        with tempfile.TemporaryDirectory() as root:
            inbox = Path(root) / "inbox"; inbox.mkdir()
            (inbox / "Colliers Raleigh Multifamily Q1 2024.pdf").write_bytes(b"not-a-real-pdf")
            (inbox / "Colliers Raleigh Multifamily Q3 2024.pdf").write_bytes(b"not-a-real-pdf")
            report = save_report_discovery(inbox)
            self.assertEqual(len(report["documents"]), 2)
            self.assertEqual(report["series"][0]["periods_missing"], ["2024-Q2"])
            self.assertTrue(Path(report["manifest_path"]).exists())
            self.assertTrue(all(item["analyst_review_required"] for item in report["documents"]))

    def test_table_profiles_detect_drift_and_preserve_cell_evidence(self):
        profile = ReportMappingProfile("broker_v1", "1", ("Vacancy", "Avg Asking Rent"), {
            "Vacancy": ("vacancy_rate", "decimal_fraction", "market_vacancy"),
            "Avg Asking Rent": ("asking_rent", "USD_per_unit_month", "asking_rent")})
        with tempfile.TemporaryDirectory() as root:
            saved = save_report_profile(WarehousePaths.from_data_root(root), profile)
            self.assertEqual(load_report_profile(saved), profile)
        context = _raw(); context.pop("metric"); context.pop("value"); context.pop("unit"); context.pop("methodology")
        result = extract_table_candidates(rows=[{"Vacancy": "6.2%", "Avg Asking Rent": "$1,684"}],
            profile=profile, context=context, document_sha256="a" * 64, page=2, table="market-statistics")
        self.assertEqual(result["status"], "candidate_only")
        self.assertEqual(result["candidates"][0]["observation"]["value"], "0.062")
        self.assertEqual(result["candidates"][1]["evidence"]["original_value"], "$1,684")
        long = extract_table_candidates(rows=[{"Metric": "Vacancy", "Value": "6.2%"},
                                                {"Metric": "Avg Asking Rent", "Value": "$1,684"}],
            profile=profile, context=context, document_sha256="a" * 64, page=3, table="long",
            long_label_column="Metric", long_value_column="Value")
        self.assertEqual(len(long["candidates"]), 2)
        drift = extract_table_candidates(rows=[{"Vacancy": "6.2%"}], profile=profile, context=context,
            document_sha256="a" * 64, page=2, table="changed")
        self.assertEqual(drift["status"], "review_required")
        self.assertEqual(drift["candidates"], [])

    def test_exact_derivations_never_fill_missing_periods_or_auto_verify(self):
        first = normalize_cre_record(_raw(period="2023-Q1", value="1600"), row_number=2)
        current = normalize_cre_record(_raw(period="2024-Q1", value="1648"), row_number=3)
        result = derive_rent_growth_yoy([first, current])
        self.assertEqual(result[0]["value"], "0.03")
        self.assertEqual(result[0]["verification_status"], "unverified")
        self.assertEqual(derive_rent_growth_yoy([first]), [])
        occupancy = normalize_cre_record(_raw(metric="occupancy_rate", value=".942", unit="decimal_fraction",
                                                methodology="physical_occupancy"), row_number=4)
        vacancy = derive_vacancy_from_occupancy([occupancy])[0]
        self.assertEqual(vacancy["value"], "0.058")
        self.assertEqual(vacancy["methodology"], "physical_vacancy")

    def test_machine_audit_funnel_and_matrix_use_actual_verification_rows(self):
        row = normalize_cre_record(_raw(metric="rent_growth_yoy", value=".03", unit="decimal_fraction",
                                        methodology="market_yoy"), row_number=2)
        row.update({"model_eligible": True, "verification_findings": [], "confidence": .9})
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            destination = paths.contained(Path("verification/cre/dataset=fixture/version=1/verification.json"))
            destination.parent.mkdir(parents=True)
            destination.write_text(json.dumps({"dataset_id": "fixture", "source_version": "1", "invalid_rows": [],
                                               "observations": [row], "findings": [], "summary": {}}), encoding="utf-8")
            audit = target_data_audit(paths)
            installed = next(item for item in audit if item["metric"] == "rent_growth_yoy" and item["source"] == "Test Source")
            self.assertEqual((installed["observations"], installed["model_eligible"]), (1, 1))
            self.assertTrue(any(item["observations"] == 0 for item in audit))
            funnel = target_readiness_funnel(paths, property_type="multifamily", metric="rent_growth_yoy")
            self.assertEqual(funnel["stages"][-1]["count"], 1)
            matrix = coverage_matrix(paths, property_type="multifamily", metric="rent_growth_yoy")
            self.assertEqual(matrix["cells"][0]["eligible"], 1)


if __name__ == "__main__":
    unittest.main()
