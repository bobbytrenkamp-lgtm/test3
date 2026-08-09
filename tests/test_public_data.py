from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import duckdb
from openpyxl import Workbook

from test3.warehouse.lineage import observation_lineage
from test3.warehouse.reporting import coverage_report
from test3.warehouse.sources.base import PublicDataRequest, RawSnapshot
from test3.warehouse.sources.bea import BEARegional
from test3.warehouse.sources.bls import BLSLAUS
from test3.warehouse.sources.building_permits import CensusBuildingPermits
from test3.warehouse.sources.census import CensusACS
from test3.warehouse.sources.census_crosswalk import CensusCBSACrosswalk
from test3.warehouse.sources.fred import FredPublic
from test3.warehouse.sources.hud import HUDFairMarketRents
from test3.warehouse.sources.http import GovernedHttpClient
from test3.warehouse.ingestion import ingest_observations
from test3.warehouse.manifests import active_manifests
from test3.warehouse.refresh import refresh_source
from test3.warehouse.storage import WarehousePaths
from test3.warehouse.crosswalks import CountyCrosswalk, lookup_county_cbsa, validate_crosswalk
from test3.warehouse.derived import derive_annual_growth
from datetime import date


FIXTURES = Path(__file__).parent / "fixtures" / "public_data"


def snapshot(source_id, dataset_id, path, request):
    body = path.read_bytes()
    metadata = path.parent / "metadata-fixture.json"
    return RawSnapshot(source_id, dataset_id, "fixture-v1", path, metadata, datetime.now(timezone.utc).isoformat(),
                       "https://official.example/fixture", "https://official.example/fixture", 200, "text/plain",
                       len(body), hashlib.sha256(body).hexdigest(), request.serializable())


class PublicDataTests(unittest.TestCase):
    def test_http_client_rejects_arbitrary_urls(self):
        client = GovernedHttpClient(("api.census.gov",))
        with self.assertRaisesRegex(ValueError, "allowed official"):
            client.get("http://api.census.gov/data")
        with self.assertRaisesRegex(ValueError, "allowed official"):
            client.get("https://example.com/data")

    def test_census_normalizes_governed_metrics(self):
        request = PublicDataRequest("acs5_profile", 2025, 2025, "county")
        rows = list(CensusACS().normalize(snapshot("census_acs", "acs5_profile", FIXTURES / "census_acs.json", request)))
        self.assertEqual(len(rows), 10)
        self.assertEqual({row["geography_id"] for row in rows}, {"37001"})
        self.assertIn("population", {row["metric"] for row in rows})

    def test_bls_fred_and_permits_keep_original_frequency_and_geography(self):
        request = PublicDataRequest("laus_county", 2025, 2025, "county")
        bls = list(BLSLAUS().normalize(snapshot("bls_laus_ces", "laus_county", FIXTURES / "bls_laus.tsv", request)))
        self.assertEqual(len(bls), 3); self.assertEqual(bls[0]["county_fips"], "37001")
        fred_request = PublicDataRequest("macro_dgs10", parameters={"series": "DGS10"})
        fred = list(FredPublic().normalize(snapshot("fred_public", "macro_dgs10", FIXTURES / "fred.csv", fred_request)))
        self.assertEqual(len(fred), 1); self.assertEqual(fred[0]["period_type"], "daily")
        bps_request = PublicDataRequest("annual_county", 2025, 2025, "county")
        permits = list(CensusBuildingPermits().normalize(snapshot("census_bps", "annual_county", FIXTURES / "building_permits.csv", bps_request)))
        self.assertEqual(len(permits), 5); self.assertEqual(permits[-1]["metric"], "residential_permits_total")

    def test_bls_public_api_scales_published_thousands_deterministically(self):
        request = PublicDataRequest("national_lns12000000", parameters={"series": "LNS12000000"})
        snap = snapshot("bls_laus_ces", "national_lns12000000", FIXTURES / "bls_api.json", request)
        snap = RawSnapshot(**{**snap.__dict__, "final_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/LNS12000000"})
        rows = list(BLSLAUS().normalize(snap))
        self.assertEqual(rows[0]["value"], "161234000"); self.assertEqual(rows[0]["unit"], "persons")

    def test_bls_qcew_keeps_only_disclosed_all_ownership_county_totals(self):
        request = PublicDataRequest("qcew_county_annual_2024", 2024, 2024, "county", {"qcew_year": "2024"})
        rows = list(BLSLAUS().normalize(snapshot("bls_laus_ces", "qcew_county_annual_2024", FIXTURES / "bls_qcew.csv", request)))
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["geography_id"] for row in rows}, {"37001"})
        self.assertIn("average_weekly_wage", {row["metric"] for row in rows})

    def test_bls_annual_workbook_and_verified_local_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            workbook_path = Path(root) / "laucnty25.xlsx"
            workbook = Workbook(); sheet = workbook.active
            sheet.append(["Labor Force Data by County, 2025 Annual Averages"])
            sheet.append(["LAUS Code", "State FIPS Code", "County FIPS Code", "County Name/State Abbreviation",
                          "Year", "Labor Force", "Employed", "Unemployed", "Unemployment Rate (%)"])
            sheet.append(["LAUCN370010000000003", "37", "001", "Fiction County, NC", 2025, "100,000", "95,000", "5,000", 5.0])
            workbook.save(workbook_path)
            request = PublicDataRequest("annual", 2025, 2025, "county", {
                "annual_county": "true", "local_file": str(workbook_path),
                "source_url": "https://www.bls.gov/lau/laucnty25.xlsx",
            })
            paths = WarehousePaths.from_data_root(root)
            snap = BLSLAUS().fetch(request, paths)
            repeated = BLSLAUS().fetch(request, paths)
            rows = list(BLSLAUS().normalize(snap))
            self.assertEqual(len(rows), 4)
            self.assertEqual(snap.source_version, repeated.source_version)
            self.assertEqual({row["metric"] for row in rows}, {"labor_force", "employment", "unemployment", "unemployment_rate"})
            self.assertNotIn(str(Path(root).resolve()), snap.request_parameters["parameters"]["local_file"])

    def test_official_cbsa_crosswalk_workbook_is_versioned_canonical_data(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "list1_2023.xlsx"
            workbook = Workbook(); sheet = workbook.active
            sheet.append(["title"])
            sheet.append(["CBSA Code", "CBSA Title", "County/County Equivalent", "State Name", "FIPS State Code", "FIPS County Code"])
            sheet.append(["39580", "Raleigh-Cary, NC", "Wake County", "North Carolina", "37", "183"])
            workbook.save(path)
            request = PublicDataRequest("county_cbsa_2023", parameters={"vintage": "2023"})
            rows = list(CensusCBSACrosswalk().normalize(snapshot("census_cbsa_crosswalk", "county_cbsa_2023", path, request)))
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["county_fips"], "37183")
            self.assertEqual(rows[0]["cbsa"], "39580"); self.assertEqual(rows[0]["metric"], "county_cbsa_membership")
            paths = WarehousePaths.from_data_root(root)
            ingest_observations(paths, source_id="census_cbsa_crosswalk", dataset_id="county_cbsa_2023",
                                source_version="fixture-v1", domain="geography", rows=rows)
            self.assertEqual(lookup_county_cbsa(paths, "37183", date(2024, 1, 1))["cbsa"], "39580")
            self.assertIsNone(lookup_county_cbsa(paths, "37183", date(2020, 1, 1)))

    def test_hud_history_preserves_counties_and_county_subdivisions(self):
        request = PublicDataRequest("fair_market_rents_history", 2026, 2026)
        rows = list(HUDFairMarketRents().normalize(snapshot("hud_public", "fair_market_rents_history", FIXTURES / "hud_fmr.csv", request)))
        self.assertEqual(len(rows), 10)
        self.assertEqual({row["geography_type"] for row in rows}, {"county", "county_subdivision"})
        self.assertEqual({row["property_subtype"] for row in rows}, {"studio", "one_bedroom", "two_bedroom", "three_bedroom", "four_bedroom"})
        self.assertEqual(next(row for row in rows if row["geography_type"] == "county_subdivision")["county_fips"], "09110")

    def test_crosswalk_vintages_and_derived_growth_lineage(self):
        crosswalk = CountyCrosswalk("37001", "Fiction", "37", "North Carolina", "12345", "Fiction Metro", date(2023, 1, 1), None, "2023")
        self.assertEqual(validate_crosswalk(crosswalk).cbsa, "12345")
        with self.assertRaises(ValueError):
            validate_crosswalk(CountyCrosswalk("37001", "Fiction", "36", "Wrong", None, None, date(2023, 1, 1), None, "x"))
        base = {"metric":"population", "period_type":"annual", "geography_type":"county", "geography_id":"37001", "observation_id":"a", "value":"100", "observation_date":"2024-01-01"}
        growth = list(derive_annual_growth([base, {**base, "observation_id":"b", "value":"110", "observation_date":"2025-01-01"}], metric="population", output_metric="population_growth_yoy"))
        self.assertEqual(len(growth), 1); self.assertIn("a,b", growth[0]["methodology"])

    def test_bea_zip_normalization_preserves_scaling(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "CAINC1.zip"
            with zipfile.ZipFile(archive, "w") as target:
                target.write(FIXTURES / "bea.csv", "CAINC1__ALL_AREAS_1969_2025.csv")
            request = PublicDataRequest("regional_cainc1", 2025, 2025, parameters={"table": "CAINC1"})
            rows = list(BEARegional().normalize(snapshot("bea_regional", "regional_cainc1", archive, request)))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["unit"], "thousands_USD_current")

    def test_each_fixture_flows_to_parquet_manifest_coverage_and_lineage(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            request = PublicDataRequest("acs5_profile", 2025, 2025, "county")
            snap = snapshot("census_acs", "acs5_profile", FIXTURES / "census_acs.json", request)
            rows = list(CensusACS().normalize(snap))
            result = ingest_observations(paths, source_id="census_acs", dataset_id="acs5_profile", source_version="fixture-v1", domain="demographics", rows=rows)
            report = coverage_report(paths)
            self.assertTrue(any(item["metric"] == "population" for item in report))
            with duckdb.connect(":memory:") as db:
                observation_id = db.execute(f"select observation_id from read_parquet('{result.parquet_path.as_posix()}') limit 1").fetchone()[0]
            lineage = observation_lineage(paths, observation_id)
            self.assertEqual(lineage["source"], "census_acs")

    def test_all_tier_one_parsers_publish_queryable_parquet(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            cases = [
                (BLSLAUS(), "bls_laus_ces", "laus_county", "labor", FIXTURES / "bls_laus.tsv", PublicDataRequest("laus_county", 2025, 2025, "county")),
                (FredPublic(), "fred_public", "macro_dgs10", "capital_markets", FIXTURES / "fred.csv", PublicDataRequest("macro_dgs10", parameters={"series":"DGS10"})),
                (CensusBuildingPermits(), "census_bps", "annual_county", "construction", FIXTURES / "building_permits.csv", PublicDataRequest("annual_county", 2025, 2025, "county")),
            ]
            for adapter, source_id, dataset_id, domain, path, request in cases:
                snap = snapshot(source_id, dataset_id, path, request)
                result = ingest_observations(paths, source_id=source_id, dataset_id=dataset_id, source_version="fixture-v1", domain=domain, rows=adapter.normalize(snap))
                self.assertGreater(result.row_count, 0)
            archive = Path(root) / "bea-fixture.zip"
            with zipfile.ZipFile(archive, "w") as target: target.write(FIXTURES / "bea.csv", "CAINC1__ALL_AREAS_1969_2025.csv")
            request = PublicDataRequest("regional_cainc1", 2025, 2025, parameters={"table":"CAINC1"})
            snap = snapshot("bea_regional", "regional_cainc1", archive, request)
            result = ingest_observations(paths, source_id="bea_regional", dataset_id="regional_cainc1", source_version="fixture-v1", domain="income", rows=BEARegional().normalize(snap))
            self.assertEqual(result.row_count, 3)
            self.assertGreaterEqual(len(coverage_report(paths)), 6)

    def test_schema_change_and_empty_response_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            bad = Path(root) / "bad.json"; bad.write_text('[["NAME"],["x"]]', encoding="utf-8")
            request = PublicDataRequest("acs5_profile", 2025, 2025, "county")
            with self.assertRaisesRegex(ValueError, "schema changed"):
                list(CensusACS().normalize(snapshot("census_acs", "acs5_profile", bad, request)))

    def test_refresh_is_unchanged_and_failure_keeps_prior_active_snapshot(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            request = PublicDataRequest("auto", 2025, 2025, "county")
            snap = snapshot("census_acs", "acs5_county_2025_b01003_001e", FIXTURES / "census_acs.json", PublicDataRequest("acs5_county_2025_b01003_001e", 2025, 2025, "county"))
            with patch.object(CensusACS, "fetch", return_value=snap):
                first = refresh_source(paths, "census", request)
                second = refresh_source(paths, "census", request)
            self.assertEqual(first["status"], "succeeded"); self.assertEqual(second["status"], "unchanged")
            broken = RawSnapshot(**{**snap.__dict__, "source_version": "fixture-v2"})
            with patch.object(CensusACS, "fetch", return_value=broken), patch.object(CensusACS, "normalize", side_effect=ValueError("schema changed")):
                with self.assertRaisesRegex(ValueError, "schema changed"):
                    refresh_source(paths, "census", request)
            self.assertEqual(len(active_manifests(paths)), 1)


if __name__ == "__main__": unittest.main()
