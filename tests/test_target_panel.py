from __future__ import annotations

import csv
from io import StringIO
import tempfile
import unittest
from pathlib import Path

import duckdb

from test3.cre_data.importer import import_cre_csv
from test3.features.manifests import FEATURE_MANIFEST_VERSION, feature_file_entry, write_feature_manifest
from test3.research.target_panel import (_eligible_rows_from_reports, ReadinessPolicy,
                                         build_target_panel, target_readiness)
from test3.warehouse.storage import WarehousePaths


FIELDS = ("market", "geography_type", "geography_id", "cbsa", "period", "frequency", "property_type",
          "property_subtype", "metric", "value", "unit", "source_name", "source_identifier", "source_period",
          "release_date", "retrieved_at", "methodology", "vintage", "licensing_notes",
          "redistribution_permitted", "verification_status", "source_class", "sample_count", "notes")


def _csv(rows):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def _row(market, cbsa, period, value):
    return {"market": market, "geography_type": "market", "geography_id": market.lower(), "cbsa": cbsa,
            "period": period, "frequency": "quarterly", "property_type": "multifamily", "property_subtype": "market_rate",
            "metric": "rent_growth_yoy", "value": value, "unit": "decimal_fraction", "source_name": "Licensed Analyst File",
            "source_identifier": "fixture://licensed-history", "source_period": period, "release_date": f"{period[:4]}-{int(period[-1])*3:02d}-28",
            "retrieved_at": "2026-08-09T00:00:00Z", "methodology": "market_yoy", "vintage": "original",
            "licensing_notes": "Fictional test fixture only.", "redistribution_permitted": "yes",
            "verification_status": "analyst_verified", "source_class": "analyst_owned", "sample_count": "10",
            "notes": "Fictional synthetic test; never production eligible."}


def _feature_panel(paths, rows):
    directory = paths.contained(Path("features/cbsa_quarter/version=fixture-v1")); directory.mkdir(parents=True)
    panel = directory / "panel.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute("CREATE TABLE feature(geography_type VARCHAR,geography_id VARCHAR,state_fips VARCHAR,county_fips VARCHAR,cbsa VARCHAR,period_start DATE,year INTEGER,quarter INTEGER,population_growth_yoy DOUBLE,population_growth_yoy__available_at DATE)")
        connection.executemany("INSERT INTO feature VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        connection.execute("COPY feature TO ? (FORMAT PARQUET)", [str(panel)])
    write_feature_manifest(directory / "feature_manifest.json", {
        "manifest_version": FEATURE_MANIFEST_VERSION, "feature_table_version": "fixture-v1", "table_name": "cbsa_quarter",
        "created_at": "2026-08-09T00:00:00+00:00", "features": ["population_growth_yoy"],
        "availability_columns": ["population_growth_yoy__available_at"], "input_manifest_hashes": ["source-manifest-1"],
        "files": [feature_file_entry(panel)], "quality": {"panel_rows": len(rows), "feature_values": len(rows)},
    })


class TargetPanelTests(unittest.TestCase):
    def test_readiness_and_immutable_target_panel_use_only_approved_targets(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            rows = [_row("Market A", "11111", "2024-Q1", ".03"), _row("Market B", "22222", "2024-Q1", ".04"),
                    _row("Market A", "11111", "2024-Q2", ".035"), _row("Market B", "22222", "2024-Q2", ".045")]
            import_cre_csv(paths, _csv(rows), dataset_id="fictional_targets", source_version="v1",
                           evaluated_at="2026-08-09", analyst_review_confirmed=True)
            _feature_panel(paths, [
                ("cbsa", "11111", None, None, "11111", "2024-01-01", 2024, 1, .01, "2024-03-15"),
                ("cbsa", "22222", None, None, "22222", "2024-01-01", 2024, 1, .02, "2024-03-15"),
                ("cbsa", "11111", None, None, "11111", "2024-04-01", 2024, 2, .011, "2024-06-15"),
                ("cbsa", "22222", None, None, "22222", "2024-04-01", 2024, 2, .021, "2024-06-15"),
            ])
            readiness = next(item for item in target_readiness(paths, policy=ReadinessPolicy(2, 2, 4))
                             if item["property_type"] == "multifamily" and item["target"] == "rent_growth_yoy")
            self.assertEqual((readiness["status"], readiness["model_eligible_observations"]), ("ready", 4))
            result = build_target_panel(paths, property_type="multifamily", target="rent_growth_yoy")
            self.assertEqual((result.rows, result.markets, result.periods), (4, 2, 2))
            self.assertTrue(result.panel_path.is_file()); self.assertTrue(result.target_dataset_hashes)
            repeated = build_target_panel(paths, property_type="multifamily", target="rent_growth_yoy")
            self.assertEqual((repeated.status, repeated.manifest_hash), ("unchanged", result.manifest_hash))

    def test_unreviewed_and_unresolved_multiple_sources_are_not_ready(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            first = _row("Market A", "11111", "2024-Q1", ".03")
            second = {**first, "source_name": "Second Source", "source_identifier": "fixture://second", "value": ".031"}
            import_cre_csv(paths, _csv([first, second]), dataset_id="conflicted", source_version="v1",
                           evaluated_at="2026-08-09", analyst_review_confirmed=True)
            report = next(item for item in target_readiness(paths, policy=ReadinessPolicy(1, 1, 1))
                          if item["property_type"] == "multifamily" and item["target"] == "rent_growth_yoy")
            self.assertEqual(report["status"], "not_ready")
            self.assertEqual(report["model_eligible_observations"], 0)
            self.assertEqual(report["exclusions"]["unresolved_multiple_sources"], 2)

    def test_methodology_change_spans_distinct_quarterly_documents(self):
        first = _row("Market A", "11111", "2024-Q1", ".03")
        second = {**_row("Market A", "11111", "2024-Q2", ".04"),
                  "source_identifier": "fixture://different-quarterly-report",
                  "methodology": "changed_market_yoy"}
        rows = []
        for item in (first, second):
            item = {**item, "observation_id": item["source_identifier"] + item["period"],
                    "model_eligible": True, "verification_findings": []}
            rows.append(item)
        eligible, exclusions = _eligible_rows_from_reports([
            {"raw_snapshot": {"sha256": "a" * 64}, "warehouse_manifest_hash": "b" * 64,
             "observations": rows}], "multifamily", "rent_growth_yoy")
        self.assertEqual(eligible, [])
        self.assertEqual(exclusions["longitudinal_methodology_change"], 2)


if __name__ == "__main__":
    unittest.main()
