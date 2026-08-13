from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from test3.cre_data.sources.catalog import CRE_TARGET_SOURCES
from test3.cre_data.sources.sec_maa import parse_maa_accessibility_snapshot
from test3.cre_data.sources.sec_maa import SNAPSHOT_SCHEMA, write_review_csv
from test3.cre_data.review import ATTESTATION_SCHEMA, approve_cre_review, prepare_cre_review
from test3.cre_data.schema import parse_cre_file
from test3.cre_data.verification import verify_observations


FIXTURE = Path(__file__).parent / "fixtures" / "fictional_maa_snapshot.txt"


class Milestone6Tests(unittest.TestCase):
    def test_maa_snapshot_extracts_source_reported_outcomes_without_approval(self):
        result = parse_maa_accessibility_snapshot(
            FIXTURE.read_text(encoding="utf-8"),
            filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
            filing_date="2025-07-30",
            retrieved_at="2026-08-09T12:00:00+00:00",
        )
        self.assertEqual(result.period, "2025-Q2")
        self.assertEqual((result.effective_rent_rows, result.rent_growth_rows, result.revenue_growth_rows,
                          result.expense_growth_rows, result.noi_growth_rows, result.revenue_rows,
                          result.expense_rows, result.noi_rows, result.noi_margin_rows, result.inventory_rows,
                          result.occupancy_rows, result.vacancy_rows), (1,) * 12)
        values = {row["metric"]: row["value"] for row in result.observations}
        self.assertEqual(values, {
            "effective_rent": "1500", "rent_growth_yoy": "0.034",
            "revenue_growth_yoy": "0.053", "operating_expense_growth_yoy": "0.053",
            "noi_growth_yoy": "0.053",
            "same_store_revenue": "10000", "same_store_operating_expense": "4000",
            "same_store_noi": "6000", "noi_margin": "0.6",
            "inventory": "1200", "occupancy_rate": "0.955", "vacancy_rate": "0.045",
        })
        checked = verify_observations(list(result.observations), analyst_review_confirmed=False)
        self.assertEqual(checked["summary"]["model_eligible"], 0)
        self.assertEqual(checked["summary"]["unverified"], 12)

    def test_sec_maa_source_is_real_target_but_local_only(self):
        source = CRE_TARGET_SOURCES["sec_maa_same_store"]
        self.assertEqual(source.target_classification, "institutional_target")
        self.assertFalse(source.requires_payment)
        self.assertTrue(source.automation_permitted)
        self.assertEqual(source.redistribution_permitted, "no")
        self.assertTrue({"same_store_revenue", "same_store_operating_expense", "same_store_noi", "noi_margin"}
                        <= set(source.metrics_available))

    def test_maa_parser_accepts_governed_2026_heading_drift(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace(
            "QUARTER OVER QUARTER COMPARISONS", "QUARTERLY COMPARISONS"
        ).replace("SEQUENTIAL QUARTER COMPARISONS", "SEQUENTIAL QUARTERLY COMPARISONS")
        result = parse_maa_accessibility_snapshot(
            snapshot,
            filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
            filing_date="2025-07-30",
        )
        self.assertEqual(result.rent_growth_rows, 1)

    def test_maa_parser_accepts_legacy_occupancy_heading_and_uses_current_quarter(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace(
            "MULTIFAMILY SAME STORE PORTFOLIO NOI CONTRIBUTION PERCENTAGE",
            "NOI CONTRIBUTION PERCENTAGE BY MARKET",
        )
        result = parse_maa_accessibility_snapshot(
            snapshot,
            filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
            filing_date="2025-07-30",
        )
        values = {row["metric"]: row["value"] for row in result.observations}
        self.assertEqual(values["occupancy_rate"], "0.955")
        self.assertEqual(values["vacancy_rate"], "0.045")

    def test_maa_parser_fails_when_reported_growth_disagrees_with_rent_levels(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace("1,450 3.4 %", "1,450 9.9 %")
        with self.assertRaisesRegex(ValueError, "rent-growth cross-check failed"):
            parse_maa_accessibility_snapshot(
                snapshot,
                filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                filing_date="2025-07-30",
            )

    def test_maa_parser_fails_when_operating_growth_disagrees_with_levels(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace("4,000 $ 3,800 5.3 %", "4,000 $ 3,800 9.9 %")
        with self.assertRaisesRegex(ValueError, "operating-expense-growth cross-check failed"):
            parse_maa_accessibility_snapshot(
                snapshot,
                filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                filing_date="2025-07-30",
            )

    def test_maa_parser_requires_disclosed_monetary_units(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace(
            "Dollars in thousands, except Average Effective Rent per Unit", "Amounts omitted"
        )
        with self.assertRaisesRegex(ValueError, "monetary unit label"):
            parse_maa_accessibility_snapshot(
                snapshot,
                filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                filing_date="2025-07-30",
            )

    def test_maa_parser_enforces_revenue_expense_noi_identity(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace("$ 6,000 $ 5,700 5.3 %", "$ 6,001 $ 5,700 5.3 %")
        with self.assertRaisesRegex(ValueError, "revenue-expense-NOI identity failed"):
            parse_maa_accessibility_snapshot(
                snapshot,
                filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                filing_date="2025-07-30",
            )

    def test_maa_parser_fails_when_independent_tables_disagree_on_units(self):
        snapshot = FIXTURE.read_text(encoding="utf-8").replace(
            "Fictionville, NC 1,200 60.0 %", "Fictionville, NC 1,199 60.0 %"
        )
        with self.assertRaisesRegex(ValueError, "apartment-unit cross-check failed"):
            parse_maa_accessibility_snapshot(
                snapshot,
                filing_url="https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                filing_date="2025-07-30",
            )

    def test_analyst_approval_is_hash_bound_scoped_and_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            snapshot = FIXTURE.read_bytes(); snapshot_path = folder / "filing.snapshot.txt"
            snapshot_path.write_bytes(snapshot)
            (folder / "filing.json").write_text(json.dumps({
                "schema_version": SNAPSHOT_SCHEMA,
                "snapshot_file": snapshot_path.name,
                "sha256": hashlib.sha256(snapshot).hexdigest(),
                "filing_url": "https://www.sec.gov/Archives/edgar/data/912595/fictional/maa-ex99_2.htm",
                "filing_date": "2025-07-30",
                "retrieved_at": "2026-08-09T12:00:00+00:00",
            }), encoding="utf-8")
            review = folder / "review.csv"; write_review_csv(folder, review)
            packet_path = folder / "review-packet.json"
            packet = prepare_cre_review(review, packet_path)
            self.assertFalse(packet["authoritative"])
            self.assertEqual((packet["observations"], packet["markets"]), (12, 1))
            self.assertEqual(packet["evidence_documents"], 1)
            packet_payload = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet_payload["attestation_template"]["approved_markets"], [])
            self.assertTrue(all(value is False for value in packet_payload["attestation_template"]["acknowledgements"].values()))
            with self.assertRaises(FileExistsError):
                prepare_cre_review(review, packet_path)
            attestation = folder / "attestation.json"
            attestation.write_text(json.dumps({
                "schema_version": ATTESTATION_SCHEMA,
                "analyst_identity": "Fictional Analyst",
                "signed_at": "2026-08-12T12:00:00-04:00",
                "rationale": "Reviewed the fictional source row and methodology for testing.",
                "input_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
                "approved_markets": ["maa-fictionville-nc"],
                "approved_metrics": ["rent_growth_yoy"],
                "period_from": "2025-Q2", "period_to": "2025-Q2",
                "acknowledgements": {name: True for name in (
                    "source_evidence_reviewed", "methodology_compatible",
                    "market_definitions_reviewed", "rights_confirmed")},
            }), encoding="utf-8")
            output = folder / "approved.csv"
            approved = approve_cre_review(review, attestation, output)
            self.assertEqual((approved["observations"], approved["markets"], approved["periods"]), (1, 1, 1))
            rows, errors, _ = parse_cre_file(output.read_bytes(), suffix=".csv")
            self.assertFalse(errors); self.assertEqual(rows[0]["verification_status"], "analyst_verified")
            with self.assertRaises(FileExistsError):
                approve_cre_review(review, attestation, output)
            bad = json.loads(attestation.read_text(encoding="utf-8")); bad["input_sha256"] = "0" * 64
            bad_path = folder / "bad.json"; bad_path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different review file"):
                approve_cre_review(review, bad_path, folder / "bad-output.csv")
            unknown = json.loads(attestation.read_text(encoding="utf-8")); unknown["approved_metrics"] = ["rent_growth_yoy", "transaction_cap_rate"]
            unknown_path = folder / "unknown.json"; unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown or empty metrics"):
                approve_cre_review(review, unknown_path, folder / "unknown-output.csv")
            naive = json.loads(attestation.read_text(encoding="utf-8")); naive["signed_at"] = "2026-08-12T12:00:00"
            naive_path = folder / "naive.json"; naive_path.write_text(json.dumps(naive), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "timezone"):
                approve_cre_review(review, naive_path, folder / "naive-output.csv")
