from __future__ import annotations

import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from test3.cre_data import available_as_of, import_cre_csv, parse_cre_csv, reconcile_observations, verify_observations
from test3.cre_data.review import ATTESTATION_SCHEMA, approve_cre_review, prepare_cre_review
from test3.warehouse.duckdb_engine import WarehouseEngine
from test3.warehouse.storage import WarehousePaths


FIELDS = ("market", "geography_type", "geography_id", "cbsa", "period", "frequency", "property_type", "property_subtype",
          "metric", "value", "unit", "source_name", "source_identifier", "source_period", "release_date", "retrieved_at",
          "methodology", "vintage", "licensing_notes", "redistribution_permitted", "verification_status", "source_class",
          "sample_count", "notes")


def cre_csv(rows):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def row(**changes):
    value = {"market": "Fictional Research Market", "geography_type": "market", "geography_id": "fictional-market",
             "cbsa": "99999", "period": "2024-Q1", "frequency": "quarterly", "property_type": "multifamily",
             "property_subtype": "market_rate", "metric": "vacancy_rate", "value": ".05", "unit": "decimal_fraction",
             "source_name": "Fictional Open Research", "source_identifier": "fixture://cre/market-report",
             "source_period": "2024-Q1", "release_date": "2024-04-15", "retrieved_at": "2026-08-09T12:00:00Z",
             "methodology": "market_vacancy", "vintage": "original", "licensing_notes": "Fictional fixture; redistribution permitted.",
             "redistribution_permitted": "yes", "verification_status": "analyst_verified", "source_class": "academic_open",
             "sample_count": "25", "notes": "Fictional deterministic test evidence."}
    value.update(changes)
    return value


class CREDataTests(unittest.TestCase):
    def test_path_identifiers_are_bounded_before_version_publication(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            with self.assertRaisesRegex(ValueError, "64 normalized characters"):
                import_cre_csv(paths, cre_csv([row()]), dataset_id="fictional_cre_history",
                               source_version="v" * 65)
            self.assertFalse(paths.contained(Path("verification/cre/dataset=fictional_cre_history")).exists())

    def test_property_specific_metrics_units_and_impossible_values_fail(self):
        valid, errors, metadata = parse_cre_csv(cre_csv([row()]))
        self.assertEqual((len(valid), len(errors), metadata["valid_rows"]), (1, 0, 1))
        _, errors, _ = parse_cre_csv(cre_csv([row(unit="USD_per_sf_year")]))
        self.assertIn("unit", errors[0]["error"])
        _, errors, _ = parse_cre_csv(cre_csv([row(value="1.2")]))
        self.assertIn("outside", errors[0]["error"])
        _, errors, _ = parse_cre_csv(cre_csv([row(property_type="office", metric="occupancy_rate", methodology="physical_occupancy")]))
        self.assertIn("not governed", errors[0]["error"])

    def test_verification_preserves_conflicts_revisions_gaps_and_anomalies(self):
        rows = [
            row(),
            row(source_name="Independent Fictional Source", source_identifier="fixture://cre/independent", value=".13", source_class="brokerage_public_report"),
            row(vintage="revision-1", value=".06"),
            row(period="2024-Q3", source_period="2024-Q3", release_date="2024-10-15", value=".22"),
        ]
        parsed, errors, _ = parse_cre_csv(cre_csv(rows)); self.assertFalse(errors)
        checked = verify_observations(parsed, evaluated_at="2026-08-09", analyst_review_confirmed=True)
        codes = {item["code"] for item in checked["findings"]}
        self.assertTrue({"source_conflict", "revised_observation", "missing_periods", "sudden_jump"} <= codes)
        self.assertEqual(len(checked["observations"]), 4, "conflicting and revised evidence must be preserved")
        self.assertTrue(all(0 <= item["confidence"] <= 1 for item in checked["observations"]))

    def test_longitudinal_checks_span_distinct_quarterly_evidence_documents(self):
        rows = [
            row(source_identifier="fixture://report/2024q1"),
            row(period="2024-Q3", source_period="2024-Q3", release_date="2024-10-15",
                source_identifier="fixture://report/2024q3", value=".20"),
        ]
        parsed, errors, _ = parse_cre_csv(cre_csv(rows)); self.assertFalse(errors)
        checked = verify_observations(parsed, evaluated_at="2026-08-09", analyst_review_confirmed=True)
        codes = {item["code"] for item in checked["findings"]}
        self.assertIn("missing_periods", codes)
        self.assertIn("sudden_jump", codes)

    def test_revision_identity_does_not_depend_on_evidence_document_url(self):
        parsed, errors, _ = parse_cre_csv(cre_csv([
            row(source_identifier="fixture://original", vintage="original"),
            row(source_identifier="fixture://revision", vintage="revision-1", value=".06"),
        ])); self.assertFalse(errors)
        checked = verify_observations(parsed, evaluated_at="2026-08-09", analyst_review_confirmed=True)
        self.assertIn("revised_observation", {item["code"] for item in checked["findings"]})
        self.assertNotIn("source_conflict", {item["code"] for item in checked["findings"]})

    def test_duplicates_and_future_information_fail_closed(self):
        parsed, _, _ = parse_cre_csv(cre_csv([row(), row()]))
        checked = verify_observations(parsed, evaluated_at="2026-08-09")
        self.assertEqual(checked["summary"]["model_eligible"], 0)
        self.assertIn("duplicate_observation", {item["code"] for item in checked["findings"]})
        unique, _, _ = parse_cre_csv(cre_csv([row()]))
        historical = available_as_of(verify_observations(unique)["observations"], "2024-03-31")
        self.assertFalse(historical["included"])
        self.assertEqual(historical["excluded"][0]["code"], "future_data_leakage")
        self.assertFalse(historical["look_ahead"])

    def test_file_cannot_self_approve_without_operator_review_flag(self):
        parsed, _, _ = parse_cre_csv(cre_csv([row()]))
        unchecked = verify_observations(parsed)
        self.assertEqual(unchecked["summary"]["model_eligible"], 0)
        self.assertIn("unconfirmed_verification", {item["code"] for item in unchecked["findings"]})
        checked = verify_observations(parsed, analyst_review_confirmed=True)
        self.assertEqual(checked["summary"]["model_eligible"], 1)

    def test_occupancy_and_vacancy_must_be_exact_complements(self):
        parsed, errors, _ = parse_cre_csv(cre_csv([
            row(metric="occupancy_rate", methodology="physical_occupancy", value=".94",
                source_identifier="fixture://cre/occupancy"),
            row(metric="vacancy_rate", methodology="physical_vacancy", value=".08",
                source_identifier="fixture://cre/vacancy"),
        ]))
        self.assertFalse(errors)
        checked = verify_observations(parsed, analyst_review_confirmed=True)
        self.assertIn("occupancy_vacancy_mismatch", {item["code"] for item in checked["findings"]})
        self.assertEqual(checked["summary"]["model_eligible"], 0)

    def test_resolved_complementary_rates_remain_eligible(self):
        parsed, errors, _ = parse_cre_csv(cre_csv([
            row(metric="occupancy_rate", methodology="physical_occupancy", value=".94",
                source_identifier="fixture://cre/occupancy"),
            row(metric="vacancy_rate", methodology="physical_vacancy", value=".06",
                source_identifier="fixture://cre/vacancy"),
        ]))
        self.assertFalse(errors)
        checked = verify_observations(parsed, analyst_review_confirmed=True)
        self.assertNotIn("occupancy_vacancy_mismatch", {item["code"] for item in checked["findings"]})
        self.assertEqual(checked["summary"]["model_eligible"], 2)

    def test_operating_statement_identity_and_margin_are_central_verification_gates(self):
        parsed, errors, _ = parse_cre_csv(cre_csv([
            row(metric="same_store_revenue", methodology="same_store_operating_revenue", value="10000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/revenue"),
            row(metric="same_store_operating_expense", methodology="same_store_operating_expense", value="4000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/expense"),
            row(metric="same_store_noi", methodology="same_store_net_operating_income", value="5900",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/noi"),
            row(metric="noi_margin", methodology="same_store_noi_margin", value=".61",
                unit="decimal_fraction", source_identifier="fixture://cre/margin"),
        ]))
        self.assertFalse(errors)
        checked = verify_observations(parsed, analyst_review_confirmed=True)
        codes = {item["code"] for item in checked["findings"]}
        self.assertTrue({"operating_identity_mismatch", "noi_margin_mismatch"} <= codes)
        self.assertEqual(checked["summary"]["model_eligible"], 0)

    def test_reconciled_operating_statement_rows_remain_eligible(self):
        parsed, errors, _ = parse_cre_csv(cre_csv([
            row(metric="same_store_revenue", methodology="same_store_operating_revenue", value="10000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/revenue"),
            row(metric="same_store_operating_expense", methodology="same_store_operating_expense", value="4000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/expense"),
            row(metric="same_store_noi", methodology="same_store_net_operating_income", value="6000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/noi"),
            row(metric="noi_margin", methodology="same_store_noi_margin", value=".6",
                unit="decimal_fraction", source_identifier="fixture://cre/margin"),
        ]))
        self.assertFalse(errors)
        checked = verify_observations(parsed, analyst_review_confirmed=True)
        codes = {item["code"] for item in checked["findings"]}
        self.assertFalse({"operating_unit_mismatch", "operating_identity_mismatch", "noi_margin_mismatch"} & codes)
        self.assertEqual(checked["summary"]["model_eligible"], 4)

    def test_review_packet_surfaces_and_approval_blocks_operating_inconsistency(self):
        content = cre_csv([
            row(metric="same_store_revenue", methodology="same_store_operating_revenue", value="10000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/revenue"),
            row(metric="same_store_operating_expense", methodology="same_store_operating_expense", value="4000",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/expense"),
            row(metric="same_store_noi", methodology="same_store_net_operating_income", value="5900",
                unit="USD_thousands_quarter", source_identifier="fixture://cre/noi"),
        ])
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            review = folder / "review.csv"; review.write_bytes(content)
            packet_path = folder / "packet.json"
            prepare_cre_review(review, packet_path)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["quality_summary"]["blocking_finding_codes"], ["operating_identity_mismatch"])
            self.assertEqual(packet["quality_findings"][0]["code"], "operating_identity_mismatch")
            self.assertEqual(packet["quality_findings"][0]["affected_observations"][0]["market"],
                             "Fictional Research Market")
            self.assertFalse(packet["quality_findings_truncated"])
            attestation = folder / "attestation.json"
            attestation.write_text(json.dumps({
                "schema_version": ATTESTATION_SCHEMA,
                "analyst_identity": "Fictional Analyst",
                "signed_at": "2026-08-13T12:00:00-04:00",
                "rationale": "Reviewed fictional evidence for a conservative rejection test.",
                "input_sha256": hashlib.sha256(content).hexdigest(),
                "approved_markets": ["fictional-market"],
                "approved_metrics": ["same_store_revenue", "same_store_operating_expense", "same_store_noi"],
                "period_from": "2024-Q1", "period_to": "2024-Q1",
                "acknowledgements": {name: True for name in (
                    "source_evidence_reviewed", "methodology_compatible",
                    "market_definitions_reviewed", "rights_confirmed")},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "operating_identity_mismatch"):
                approve_cre_review(review, attestation, folder / "approved.csv")

    def test_reconciliation_uses_explicit_priority_and_never_averages(self):
        parsed, _, _ = parse_cre_csv(cre_csv([row(), row(source_name="Preferred", source_identifier="fixture://preferred", value=".07")]))
        checked = verify_observations(parsed, analyst_review_confirmed=True)["observations"]
        result = reconcile_observations(checked, source_priority=("Preferred", "Fictional Open Research"))
        self.assertEqual((result[0]["source_name"], result[0]["value"], result[0]["averaged"]), ("Preferred", "0.07", False))
        self.assertEqual(len(result[0]["alternative_observation_ids"]), 1)

    def test_import_persists_raw_parquet_manifest_and_verification(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            result = import_cre_csv(paths, cre_csv([row()]), dataset_id="fictional_cre_history", source_version="2024q1-v1",
                                    evaluated_at="2026-08-09", analyst_review_confirmed=True)
            self.assertEqual((result.observations, result.model_eligible, result.invalid_rows), (1, 1, 0))
            self.assertTrue(result.parquet_path.is_file()); self.assertTrue(result.verification_path.is_file())
            report = json.loads(result.verification_path.read_text(encoding="utf-8"))
            self.assertEqual(report["warehouse_manifest_hash"], result.manifest_hash)
            warehouse_rows = WarehouseEngine(paths).query_observations(metrics=("vacancy_rate",),
                                                                        columns=("observation_id", "property_type", "metric"))
            self.assertEqual((len(warehouse_rows), warehouse_rows[0]["property_type"]), (1, "multifamily"))
            with self.assertRaises((FileExistsError, ValueError)):
                import_cre_csv(paths, cre_csv([row()]), dataset_id="fictional_cre_history", source_version="2024q1-v1")


if __name__ == "__main__":
    unittest.main()
