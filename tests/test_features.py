from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from test3.features.builder import build_feature_table
from test3.features.frequency import lagged_period, validate_frequency_conversion
from test3.features.growth import exact_growth, ratio_per_1000
from test3.features.manifests import verify_feature_manifest
from test3.features.panel import FeaturePanel
from test3.features.registry import FEATURE_REGISTRY, FeatureSpec, registry_fingerprint
from test3.warehouse.ingestion import ingest_observations
from test3.warehouse.storage import WarehousePaths


def observation(*, source_id, dataset, version, series, geography_id, metric, value, year,
                unit, cbsa=None, subtype=None, period_type="annual", observed=None):
    fingerprint = hashlib.sha256(f"{source_id}|{dataset}|{series}|{geography_id}|{metric}|{year}|{value}".encode()).hexdigest()
    return {
        "observation_id": None, "source_id": source_id, "source_dataset": dataset,
        "source_series": series, "source_version": version, "retrieved_at": "2026-08-09T12:00:00Z",
        "as_of_date": f"{year}-12-31", "geography_type": "national" if geography_id == "US" else "county",
        "geography_id": geography_id, "state_fips": None if geography_id == "US" else geography_id[:2],
        "county_fips": None if geography_id == "US" else geography_id, "cbsa": cbsa, "city": None,
        "submarket": None, "property_type": "multifamily" if subtype else None, "property_subtype": subtype,
        "observation_date": observed or str(year), "period_type": period_type, "metric": metric,
        "value": str(value), "unit": unit, "currency": None, "sample_count": None,
        "quality_level": "high", "methodology": "Fictional synthetic feature fixture",
        "transformation_version": "fixture/1", "raw_source_reference": f"fixture://{fingerprint}",
        "raw_row_hash": f"sha256:{fingerprint}", "normalized_row_hash": None,
    }


def seed_feature_warehouse(paths: WarehousePaths):
    counties = ("01001", "01003")
    census = []
    for year, populations in ((2020, (100, 200)), (2021, (110, 220)), (2022, (121, 242)), (2023, (133.1, 266.2))):
        for county, population in zip(counties, populations):
            for metric, value, unit, series in (
                ("population", population, "persons", "B01003_001E"),
                ("households", float(population) / 2, "households", "B11001_001E"),
                ("housing_units", float(population) * .6, "units", "B25001_001E"),
            ):
                census.append(observation(source_id="census_acs", dataset="fixture_acs", version="v1", series=series,
                                          geography_id=county, metric=metric, value=value, year=year, unit=unit))
    ingest_observations(paths, source_id="census_acs", dataset_id="fixture_acs", source_version="v1", domain="demographics", rows=census)
    permits = []
    for year, values in ((2020, (10, 20)), (2021, (12, 22)), (2022, (14, 24)), (2023, (16, 26))):
        for county, value in zip(counties, values):
            permits.append(observation(source_id="census_bps", dataset="fixture_bps", version="v1", series="units_5_plus",
                                       geography_id=county, metric="multifamily_5_plus_units_authorized", value=value, year=year, unit="units"))
    ingest_observations(paths, source_id="census_bps", dataset_id="fixture_bps", source_version="v1", domain="construction", rows=permits)
    macro = []
    for year, values in ((2020, (1.0, 1.2)), (2021, (1.5, 1.7)), (2022, (2.0, 2.3)), (2023, (3.5, 4.0))):
        for month, value in ((1, values[0]), (12, values[1])):
            macro.append(observation(source_id="fred_public", dataset="fixture_dgs10", version="v1", series="DGS10",
                                     geography_id="US", metric="treasury_10y", value=value, year=year, unit="percent",
                                     period_type="daily", observed=f"{year}-{month:02d}-15"))
    ingest_observations(paths, source_id="fred_public", dataset_id="fixture_dgs10", source_version="v1", domain="capital_markets", rows=macro)
    cpi = []
    for year, value in ((2020, 100), (2021, 110), (2022, 121), (2023, 133.1)):
        cpi.append(observation(source_id="fred_public", dataset="fixture_cpi", version="v1", series="CPIAUCSL",
                               geography_id="US", metric="cpi", value=value, year=year,
                               unit="index_1982_1984_100", period_type="monthly", observed=f"{year}-12"))
    ingest_observations(paths, source_id="fred_public", dataset_id="fixture_cpi", source_version="v1",
                        domain="capital_markets", rows=cpi)
    crosswalk = [observation(source_id="census_cbsa_crosswalk", dataset="fixture_crosswalk", version="v1", series="OMB2023",
                             geography_id=county, metric="county_cbsa_membership", value=1, year=2023, unit="membership", cbsa="12345",
                             period_type="irregular", observed="2023-07-21") for county in counties]
    ingest_observations(paths, source_id="census_cbsa_crosswalk", dataset_id="fixture_crosswalk", source_version="v1", domain="geography", rows=crosswalk)
    fmr = [observation(source_id="hud_public", dataset="fixture_fmr", version="v1", series="FMR2BR",
                       geography_id="01001", metric="fair_market_rent", value=value, year=year, unit="USD_per_month",
                       subtype="two_bedroom") for year, value in ((2020, 900), (2021, 945), (2022, 1000), (2023, 1050))]
    ingest_observations(paths, source_id="hud_public", dataset_id="fixture_fmr", source_version="v1", domain="rent", rows=fmr)


class FeatureTableTests(unittest.TestCase):
    def test_registry_frequency_and_growth_are_governed(self):
        self.assertEqual(len(registry_fingerprint()), 64)
        self.assertEqual(FEATURE_REGISTRY["fair_market_rent_2br"].input_metrics, ("fair_market_rent",))
        self.assertEqual(FEATURE_REGISTRY["cpi_growth_yoy"].input_features, ("cpi_period_end",))
        with self.assertRaisesRegex(ValueError, "cannot be registered"):
            FeatureSpec("market_rent", "bad", ("fair_market_rent",), source_ids=("hud_public",))
        validate_frequency_conversion("annual", "quarterly", "annual_carry_forward")
        with self.assertRaisesRegex(ValueError, "ungoverned"):
            validate_frequency_conversion("annual", "quarterly", "period_mean_broadcast")
        self.assertEqual(lagged_period(date(2025, 1, 1), "quarterly", 2), date(2024, 7, 1))
        self.assertEqual(exact_growth("121", "100", years=2), exact_growth("110", "100"))
        self.assertEqual(ratio_per_1000("10", "200"), ratio_per_1000("5", "100"))
        self.assertIsNone(ratio_per_1000("10", "0"))

    def test_real_feature_snapshots_are_wide_immutable_and_source_linked(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root); seed_feature_warehouse(paths)
            annual = build_feature_table(paths, geography="county", frequency="annual")
            self.assertEqual((annual.status, annual.row_count), ("succeeded", 8))
            same = build_feature_table(paths, geography="county", frequency="annual")
            self.assertEqual((same.status, same.manifest_hash), ("unchanged", annual.manifest_hash))
            panel = FeaturePanel(paths, "county_year")
            rows = panel.query(columns=("geography_id", "period_start", "population", "population_growth_yoy",
                                        "multifamily_permits_per_1000_population", "fair_market_rent_2br",
                                        "cpi_growth_yoy"), limit=100)
            county = next(row for row in rows if row["geography_id"] == "01001" and str(row["period_start"]) == "2021-01-01")
            self.assertAlmostEqual(county["population_growth_yoy"], .1)
            self.assertAlmostEqual(county["multifamily_permits_per_1000_population"], 12 / 110 * 1000)
            self.assertEqual(county["fair_market_rent_2br"], 945)
            self.assertAlmostEqual(county["cpi_growth_yoy"], .1)
            self.assertNotIn("market_rent", panel.latest()["features"])
            lineage_rows = panel.latest()["quality"]["feature_values"]
            self.assertGreater(lineage_rows, annual.row_count)
            self.assertTrue(panel.query(limit=1), "default projection must quote reserved year/quarter columns")
            import duckdb
            with duckdb.connect(":memory:") as db:
                growth_lineage = db.execute("SELECT lineage_id FROM read_parquet(?) WHERE geography_id='01001' AND period_start='2021-01-01' AND feature_name='population_growth_yoy'", [str(annual.lineage_path)]).fetchone()[0]
            trace = panel.trace_lineage(growth_lineage)
            self.assertEqual(len(trace["input_observation_ids"]), 2)
            self.assertTrue(trace["input_manifest_hashes"])
            manifest = verify_feature_manifest(annual.manifest_path)
            self.assertTrue(manifest["input_manifest_hashes"])
            population_definition = next(item for item in manifest["feature_definitions"] if item["name"] == "population")
            self.assertTrue(population_definition["input_dataset_versions"])
            with annual.panel_path.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "integrity"):
                panel.latest()

    def test_quarterly_carry_forward_is_explicit_and_missing_is_not_zero_filled(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root); seed_feature_warehouse(paths)
            result = build_feature_table(paths, geography="county", frequency="quarterly")
            panel = FeaturePanel(paths, "county_quarter")
            rows = panel.query(columns=("geography_id", "period_start", "population", "population__available_at", "treasury_10y_mean"), limit=100)
            q2 = next(row for row in rows if row["geography_id"] == "01001" and str(row["period_start"]) == "2021-04-01")
            self.assertEqual(q2["population"], 110)
            self.assertEqual(str(q2["population__available_at"]), "2021-12-31")
            self.assertIsNone(q2["treasury_10y_mean"], "missing Q2 macro evidence must remain null")
            import duckdb
            with duckdb.connect(":memory:") as db:
                lineage_id = db.execute(f"SELECT lineage_id FROM read_parquet(?) WHERE geography_id='01001' AND period_start='2021-04-01' AND feature_name='population'", [str(result.lineage_path)]).fetchone()[0]
            lineage = panel.lineage(lineage_id)
            self.assertIn("annual_carry_forward", lineage["transformation"])
            self.assertIn("no interpolation", lineage["transformation"])

    def test_cbsa_aggregation_uses_explicit_crosswalk_and_lineage_dag(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root); seed_feature_warehouse(paths)
            result = build_feature_table(paths, geography="cbsa", frequency="annual")
            panel = FeaturePanel(paths, "cbsa_year")
            rows = panel.query(columns=("geography_id", "period_start", "population", "population_growth_yoy"), limit=100)
            row = next(item for item in rows if str(item["period_start"]) == "2021-01-01")
            self.assertEqual((row["geography_id"], row["population"]), ("12345", 330))
            self.assertAlmostEqual(row["population_growth_yoy"], .1)
            import duckdb
            with duckdb.connect(":memory:") as db:
                value = db.execute("SELECT lineage_id FROM read_parquet(?) WHERE geography_type='cbsa' AND feature_name='population' AND period_start='2021-01-01'", [str(result.lineage_path)]).fetchone()[0]
            lineage = panel.lineage(value)
            self.assertEqual(len(lineage["input_feature_lineage_ids"]), 2)
            self.assertEqual(len(lineage["input_observation_ids"]), 2, "crosswalk observations are evidence")
            trace = panel.trace_lineage(value)
            self.assertEqual(len(trace["nodes"]), 3)
            self.assertEqual(len(trace["input_observation_ids"]), 4)
            self.assertNotIn("fair_market_rent_2br", panel.latest()["features"])
            self.assertNotIn("median_household_income", panel.latest()["features"])
            self.assertTrue(panel.latest()["limitations"])

    def test_ambiguous_source_keys_fail_before_publication(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            for dataset, value in (("acs_a", 100), ("acs_b", 101)):
                row = observation(source_id="census_acs", dataset=dataset, version="v1", series="B01003_001E",
                                  geography_id="01001", metric="population", value=value, year=2023, unit="persons")
                ingest_observations(paths, source_id="census_acs", dataset_id=dataset, source_version="v1", domain="demographics", rows=[row])
            with self.assertRaisesRegex(ValueError, "ambiguous source observations"):
                build_feature_table(paths, geography="county", frequency="annual")
            self.assertFalse(list((paths.root / "features" / "county_year").glob("version=*")))


if __name__ == "__main__":
    unittest.main()
