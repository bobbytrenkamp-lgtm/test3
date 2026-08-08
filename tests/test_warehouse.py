from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test3.warehouse.catalog import SOURCE_CATALOG
from test3.warehouse.duckdb_engine import WarehouseEngine
from test3.warehouse.ingestion import ingest_observations
from test3.warehouse.quality import profile_parquet
from test3.warehouse.schemas import normalize_observation
from test3.warehouse.storage import WAREHOUSE_DIRS, WarehousePaths
from test3.warehouse.temporal import normalize_period


FIXTURE = Path(__file__).parent / "fixtures" / "warehouse" / "fictional_observations.jsonl"


def fixture_rows():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


class WarehouseTests(unittest.TestCase):
    def test_warehouse_creation_and_path_containment(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            paths.initialize()
            self.assertTrue(all((paths.root / item).is_dir() for item in WAREHOUSE_DIRS))
            with self.assertRaisesRegex(ValueError, "escapes"):
                paths.contained("../outside")

    def test_source_catalog_is_non_billable_and_governed(self):
        self.assertLessEqual({"census_acs", "bls_laus_ces", "bea_regional", "fred_public", "census_bps", "test1_local", "user_import"}, SOURCE_CATALOG.keys())
        self.assertTrue(all(not source.payment_method_required and not source.can_become_billable for source in SOURCE_CATALOG.values()))
        self.assertTrue(all(source.fingerprint for source in SOURCE_CATALOG.values()))

    def test_temporal_normalization_does_not_inflate_frequency(self):
        self.assertEqual(normalize_period("2025").period_type, "annual")
        self.assertEqual(normalize_period("2025-Q2").observation_date.isoformat(), "2025-04-01")
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_period("2025", "monthly")

    def test_canonical_schema_preserves_lineage_and_nulls(self):
        row = normalize_observation(fixture_rows()[0])
        self.assertEqual(row["observation_id"], row["normalized_row_hash"].removeprefix("sha256:"))
        self.assertTrue(row["raw_source_reference"].startswith("fixture://"))
        self.assertIsNone(row["submarket"])
        with self.assertRaisesRegex(ValueError, "finite"):
            normalize_observation({**fixture_rows()[0], "value": "NaN"})

    def test_parquet_ingestion_manifest_query_and_quality(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            result = ingest_observations(paths, source_id="user_import", dataset_id="fictional_market_panel",
                                         source_version="fixture-v1", domain="rent", rows=fixture_rows(), batch_size=1)
            self.assertEqual(result.row_count, 2)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_hash"], result.manifest_hash)
            engine = WarehouseEngine(paths)
            rows = engine.query_observations(metrics=["vacancy_rate"], columns=["metric", "value", "raw_source_reference"])
            self.assertEqual(rows[0]["metric"], "vacancy_rate")
            self.assertEqual(engine.summary()["rows"], 2)
            self.assertEqual(profile_parquet(result.parquet_path)["unique_observation_ids"], 2)
            with self.assertRaisesRegex(FileExistsError, "immutable"):
                ingest_observations(paths, source_id="user_import", dataset_id="fictional_market_panel",
                                    source_version="fixture-v1", domain="rent", rows=fixture_rows())
            next_rows = [{**row, "source_version": "fixture-v2", "observation_id": None, "normalized_row_hash": None} for row in fixture_rows()]
            second = ingest_observations(paths, source_id="user_import", dataset_id="fictional_market_panel",
                                         source_version="fixture-v2", domain="rent", rows=next_rows)
            second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(second_manifest["predecessor_manifest_hash"], result.manifest_hash)
            self.assertTrue(result.parquet_path.exists(), "publishing v2 must retain the prior snapshot")

    def test_duplicate_or_invalid_ingest_never_publishes_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            rows = fixture_rows()
            with self.assertRaises(Exception):
                ingest_observations(paths, source_id="user_import", dataset_id="fictional_market_panel",
                                    source_version="fixture-v1", domain="rent", rows=[rows[0], rows[0]])
            self.assertFalse(list(paths.root.rglob("*.parquet")))
            self.assertFalse(list(paths.root.rglob("*.json")))
