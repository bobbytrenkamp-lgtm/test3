from __future__ import annotations

import hashlib
import html
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path
from openpyxl import Workbook
from PIL import Image

from test3.adapters import diligence_summary, test1_enrichment, test2_export
from test3.auth import hash_password, verify_password
from test3.backup import create_backup, verify_backup
from test3.classification import classify
from test3.db import Database
from test3.extraction import Candidate, extract_selectable_pdf_text, extract_text_candidates, normalize_value, parse_csv, parse_xlsx, process
from test3.field_registry import FIELD_BY_NAME, FIELD_REGISTRY, applicable_fields
from test3.normalization import date, number
from test3.ollama import validate_local_endpoint
from test3.permissions import require
from test3.reconciliation import reconcile
from test3.security import detect_mime, safe_filename, sanitize_text, sha256_bytes, validate_upload
from test3.service import Service
from test3.test1_snapshot import Test1SnapshotError, load_snapshot


def synthetic_xlsx() -> bytes:
    out = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Tenant", "Rent"])
    sheet.append(["Example LLC", 1250])
    workbook.save(out)
    workbook.close()
    return out.getvalue()


def synthetic_pdf(stream: bytes = b"BT /F1 12 Tf 72 720 Td (Property Name: Example Plaza) Tj 0 -18 Td (Asking Price: $10,000,000) Tj ET") -> bytes:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output); output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def synthetic_test1_data(root: Path) -> None:
    datasets = {
        "platform_metadata.json": {"_schema":"platform_metadata_v1", "_generated_at":"2026-08-01T00:00:00Z", "methodology_version":"1.0", "coverage":{"counties_researched":1}, "disclaimers":["Fictional data; verify primary sources."]},
        "map_data.json": {"generated_at":"2026-08-01T00:00:00Z", "source_last_updated":"2026-07-31", "counties":{"51107":{"name":"Example County", "state":"Virginia", "level":3, "types":["data_center"], "title":"Fictional rule", "description":"Fictional policy description", "effective_date":"2026-01-01", "status":"active", "last_reviewed":"2026-07-31", "confidence":"high", "pipeline_verified":False, "sources":[{"label":"Example County official source", "url":"https://example.gov/policy"}]}}},
        "political_risk.json": {"meta":{"last_updated":"2026-07-31"}, "scores":[{"fips":"51107", "risk_score":4, "score_label":"Elevated", "evidence_summary":"Fictional evidence", "confidence":"medium", "signal_count":1, "last_updated":"2026-07-31", "signals":[{"label":"Official hearing", "source_url":"https://example.gov/hearing"}]}]},
        "water_stress.json": {"_last_updated":"2024-01", "_disclaimer":"Approximate fictional water data", "_sources":["Public source note"], "water_stress":{"51107":3}},
        "tax_incentives.json": {"_last_updated":"2026-07-31", "tax_incentives":[{"state":"VA", "program_name":"Fictional incentive", "incentive_type":"Grant", "min_investment_m":100, "notes":"Verify", "fips_list":["51107"]}]},
        "facilities_index.json": [{"facility_id":"fictional-1", "name":"Example Facility", "operator":"Example Operator", "county_fips":"51107", "operational_status":"operational", "capacity_mw_known":25.5, "confidence_score":0.8}],
        "state_regulations.json": {"_last_updated":"2026-07-31", "states":{"51":{"name":"Virginia", "abbr":"VA", "level":1, "status":"active", "summary":"Fictional state context", "types":["data_center"], "sources":[{"label":"Virginia official source", "url":"https://example.virginia.gov/rule"}]}}},
    }
    for filename, value in datasets.items():
        (root / filename).write_text(json.dumps(value), encoding="utf-8")


class SecurityTests(unittest.TestCase):
    def test_role_permissions(self):
        require("viewer", "read")
        require("reviewer", "value.review")
        with self.assertRaises(PermissionError): require("viewer", "document.upload")
        with self.assertRaises(PermissionError): require("analyst", "value.review")

    def test_local_password_hashing(self):
        encoded = hash_password("fictional-demo", salt=b"0123456789abcdef")
        self.assertTrue(verify_password("fictional-demo", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))
        self.assertNotIn("fictional-demo", encoded)

    def test_sha256_known_value(self):
        self.assertEqual(sha256_bytes(b"fictional"), "a524644266885e16a3bb16166ae38bdbfb36af08fc51036f4dbb91423c7cbcc1")

    def test_mime_ignores_misleading_extension(self):
        self.assertEqual(detect_mime("malware.jpg", b"%PDF-1.4\n"), "application/pdf")

    def test_supported_signatures(self):
        self.assertEqual(detect_mime("a.png", b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(detect_mime("a.jpg", b"\xff\xd8\xffrest"), "image/jpeg")
        self.assertEqual(detect_mime("a.xlsx", synthetic_xlsx()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_macro_enabled_archive_is_rejected(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
            archive.writestr("xl/vbaProject.bin", b"fictional macro")
        self.assertEqual(detect_mime("renamed.xlsx", out.getvalue()), "application/vnd.ms-excel.sheet.macroEnabled.12")
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            validate_upload("renamed.xlsx", out.getvalue(), 100_000)

    def test_file_limits_and_unsupported(self):
        with self.assertRaises(ValueError): validate_upload("a.pdf", b"", 100)
        with self.assertRaises(ValueError): validate_upload("a.exe", b"MZ...", 100)
        with self.assertRaises(ValueError): validate_upload("a.csv", b"1234", 2)

    def test_path_traversal_is_removed(self):
        self.assertEqual(safe_filename("../../secret.csv"), "secret.csv")
        self.assertEqual(safe_filename("..\\..\\evil<script>.pdf"), "evil_script_.pdf")

    def test_html_sanitization(self):
        payload = '<img src=x onerror="steal()">'
        self.assertEqual(sanitize_text(payload), html.escape(payload, quote=True))


class NormalizationTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(number("$1,234.50"), Decimal("1234.50"))
        self.assertEqual(number("(2,500)"), Decimal("-2500"))
        self.assertIsNone(number("N/A"))

    def test_dates(self):
        self.assertEqual(date("2026-04-30"), ("2026-04-30", False))
        self.assertEqual(date("03/04/2026", "mdy"), ("2026-03-04", True))
        self.assertEqual(date("03/04/2026", "dmy"), ("2026-04-03", True))
        self.assertEqual(date("Apr 30, 2026"), ("2026-04-30", False))
        self.assertEqual(date("46022"), ("2025-12-31", False))


class ExtractionTests(unittest.TestCase):
    def test_field_registry_is_unique_governed_and_category_scoped(self):
        self.assertEqual(len(FIELD_BY_NAME), len(FIELD_REGISTRY))
        self.assertGreaterEqual(len(FIELD_REGISTRY), 30)
        self.assertTrue(all(field.label and field.value_type and field.patterns and field.categories for field in FIELD_REGISTRY))
        debt_names = {field.name for field in applicable_fields("debt_quote")}
        self.assertIn("loan_amount", debt_names)
        self.assertNotIn("tenant_name", debt_names)

    def test_registry_normalizes_rates_dates_and_metadata(self):
        candidates = extract_text_candidates(
            "Discount Rate: 7.5%\nMarket Value: $12,500,000",
            category="appraisal",
        )
        rate = next(item for item in candidates if item.field == "discount_rate")
        value = next(item for item in candidates if item.field == "appraised_value")
        self.assertEqual(rate.normalized, "0.075")
        self.assertEqual(rate.unit, "decimal_fraction")
        self.assertEqual(value.normalized, "12500000")
        self.assertEqual(value.currency, "USD")

    def test_registry_does_not_apply_debt_fields_to_lease(self):
        candidates = extract_text_candidates(
            "Tenant Name: Example LLC\nLoan Amount: $10,000,000",
            category="commercial_lease",
        )
        self.assertIn("tenant_name", {item.field for item in candidates})
        self.assertNotIn("loan_amount", {item.field for item in candidates})

    def test_ambiguous_rate_without_percent_stays_for_review(self):
        rate = next(item for item in extract_text_candidates("Discount Rate: 7.5", category="appraisal") if item.field == "discount_rate")
        self.assertIsNone(rate.normalized)
        self.assertLessEqual(rate.confidence, 0.45)

    def test_basis_points_normalization_round_trips_in_review_units(self):
        spread = next(item for item in extract_text_candidates("Credit Spread: 350 bps", category="debt_quote") if item.field == "loan_spread")
        self.assertEqual(spread.normalized, "0.035")
        field = FIELD_BY_NAME["loan_spread"]
        self.assertEqual(normalize_value(spread.normalized, field.value_type, field.unit), "0.035")

    def test_classification(self):
        self.assertEqual(classify("Fictional Rent Roll.csv")[0], "rent_roll")
        self.assertEqual(classify("mystery.bin")[0], "unknown")

    def test_source_page_and_confidence(self):
        candidates = extract_text_candidates("Property Name: Example Plaza\nAsking Price: $10,000,000", page=3)
        price = next(item for item in candidates if item.field == "asking_price")
        self.assertEqual(price.page, 3)
        self.assertEqual(price.normalized, "10000000")
        self.assertGreater(price.confidence, 0.8)
        self.assertIn("Asking Price", price.excerpt)

    def test_csv_bounding_box(self):
        rows, candidates = parse_csv(b"Tenant,Rent\nExample LLC,1250\n")
        self.assertEqual(rows[1][0], "Example LLC")
        rent = next(item for item in candidates if item.field.endswith("rent"))
        self.assertEqual(rent.normalized, "1250")
        self.assertEqual(rent.bbox, (1, 1, 2, 2))

    def test_xlsx_values_without_formula_execution(self):
        rows, candidates = parse_xlsx(synthetic_xlsx())
        self.assertEqual(rows[1][0], "Example LLC")
        self.assertTrue(any(item.normalized == "1250" for item in candidates))

    def test_xlsx_formula_is_never_evaluated(self):
        content = synthetic_xlsx()
        workbook = Workbook(); sheet = workbook.active; sheet.append(["Total"]); sheet.append(["=1+1"]); out = io.BytesIO(); workbook.save(out); workbook.close()
        _, candidates = parse_xlsx(out.getvalue())
        self.assertEqual(candidates[0].raw, "=1+1")
        self.assertIsNone(candidates[0].normalized)
        self.assertEqual(candidates[0].method, "xlsx_formula_not_evaluated_v2")

    def test_pdfium_pdf_source_bbox(self):
        status, candidates, warning = process("fictional-om.pdf", "application/pdf", synthetic_pdf())
        self.assertEqual(status, "extracted")
        self.assertIsNone(warning)
        name = next(item for item in candidates if item.field == "property_name")
        self.assertEqual(name.page, 1)
        self.assertIsNotNone(name.bbox)

    def test_image_decode_verification(self):
        out = io.BytesIO(); Image.new("RGB", (10, 8), "white").save(out, format="PNG")
        status, _, warning = process("scan.png", "image/png", out.getvalue())
        self.assertIn(status, ("needs_review", "extracted"))
        self.assertNotEqual(status, "failed")
        self.assertEqual(process("bad.png", "image/png", b"\x89PNG\r\n\x1a\ncorrupt")[0], "failed")

    def test_simple_pdf_and_ocr_failure_state(self):
        pdf = b"%PDF-1.4\nBT (Property Name: Example Plaza) Tj ET"
        self.assertIn("Example Plaza", extract_selectable_pdf_text(pdf))
        self.assertEqual(process("corrupt.pdf", "application/pdf", b"%PDF-1.4 image-only")[0], "failed")
        self.assertEqual(process("scan.pdf", "application/pdf", synthetic_pdf(b""))[0], "needs_review")
        image = io.BytesIO(); Image.new("L", (2, 2), 255).save(image, format="PNG")
        self.assertIn(process("scan.png", "image/png", image.getvalue())[0], ("needs_review", "extracted"))

    def test_corrupt_xlsx_fails_honestly(self):
        status, candidates, warning = process("bad.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"not-a-zip")
        self.assertEqual(status, "failed")
        self.assertEqual(candidates, [])
        self.assertIn("could not be parsed", warning)

    def test_xlsx_archive_bomb_is_rejected(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("xl/worksheets/sheet1.xml", " " * 1_000_000)
        with self.assertRaisesRegex(ValueError, "compression ratio"):
            parse_xlsx(out.getvalue())


class ReconciliationTests(unittest.TestCase):
    def test_cap_rate_is_independently_checked(self):
        findings = reconcile({"asking_price": "10000000", "broker_stated_noi": "500000", "broker_stated_cap_rate": "6"})
        self.assertEqual(findings[0].rule_code, "CAP_RATE_MATH")
        self.assertIn("5.00%", findings[0].explanation)

    def test_ten_or_more_checks_can_fire(self):
        values = {
            "rent_roll_occupied_area":"80","rent_roll_total_area":"100","occupancy":"90","rentable_square_feet":"120",
            "rent_roll_annualized_rent":"100","operating_rental_revenue":"200","calculated_noi":"50","operating_statement_noi":"60",
            "historical_noi":"100","pro_forma_noi":"130","lease_expiration":"2026","rent_roll_expiration":"2027",
            "lease_current_rent":"10","rent_roll_current_rent":"12","lease_area":"100","rent_roll_lease_area":"110",
            "om_unit_count":"10","rent_roll_unit_count":"11","asking_price":"1000","loi_price":"900","psa_price":"800",
            "capex_line_item_total":"100","capex_stated_total":"120","calculated_ltv":"0.7","stated_ltv":"0.8",
            "calculated_ltc":"0.6","stated_ltc":"0.7","calculated_all_in_rate":"0.06","stated_interest_rate":"0.07",
            "operating_periods":["Jan"]*11,"row_identifiers":["A","A"],"expected_row_count":"10","actual_row_count":"9","ocr_values":["l,OOO"]}
        self.assertGreaterEqual(len(reconcile(values)), 10)

    def test_tenant_variation_is_suggestion_not_merge(self):
        findings = reconcile({"tenant_names":["Example Holdings LLC","Example Holding LLC"]})
        self.assertEqual(findings[0].rule_code, "TENANT_NAME_VARIATION")


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.deal = {"id":"deal-1","name":"Fictional Plaza","property_type":"office"}
        self.approved = [{"field_name":"property_name","normalized_value":"Fictional Plaza","review_status":"approved","document_id":"doc-1","document_sha256":"abc","page_number":1,"source_text_hash":"source","reviewed_at":"2026-01-01T00:00:00Z"},{"field_name":"asking_price","normalized_value":"10000000","review_status":"rejected","document_id":"doc-1"}]

    def test_export_excludes_unapproved(self):
        result = test2_export(self.deal, self.approved, [])
        self.assertFalse(result["mappingDiagnostics"]["importReady"])
        self.assertIsNone(result["test2PortableModel"])
        self.assertIn("missing approved discount_rate", result["mappingDiagnostics"]["blockers"])
        self.assertNotIn("asking_price", [source["field"] for source in result["supportingSources"]])
        self.assertEqual(result["sourceDocumentHashes"], ["abc"])

    def test_export_builds_real_test2_portable_model_from_approved_values(self):
        approved = self.approved + [
            {"field_name":"forecast_start_date","normalized_value":"2026-01-01","review_status":"approved","document_id":"doc-2"},
            {"field_name":"forecast_months","normalized_value":"120","review_status":"approved","document_id":"doc-2"},
            {"field_name":"discount_rate","normalized_value":"0.075","review_status":"approved","document_id":"doc-2"},
            {"field_name":"rentable_square_feet","normalized_value":"125000","review_status":"approved","document_id":"doc-2"},
        ]
        result = test2_export(self.deal, approved, [])
        portable = result["test2PortableModel"]
        self.assertTrue(result["mappingDiagnostics"]["importReady"])
        self.assertEqual(portable["format"], "cre-platform-model")
        self.assertEqual(portable["formatVersion"], 1)
        self.assertEqual(portable["model"]["forecast"], {"startDate":"2026-01-01", "months":120})
        self.assertEqual(portable["model"]["valuation"], {"discountRate":"0.075"})
        self.assertEqual(portable["model"]["property"]["rentableArea"], "125000")
        self.assertNotIn("acquisitionPrice", portable["model"]["valuation"])

    def test_export_rejects_percent_style_discount_rate(self):
        approved = self.approved + [
            {"field_name":"forecast_start_date","normalized_value":"2026-01-01","review_status":"approved","document_id":"doc-2"},
            {"field_name":"forecast_months","normalized_value":"120","review_status":"approved","document_id":"doc-2"},
            {"field_name":"discount_rate","normalized_value":"7.5","review_status":"approved","document_id":"doc-2"},
        ]
        result = test2_export(self.deal, approved, [])
        self.assertFalse(result["mappingDiagnostics"]["importReady"])
        self.assertIn("approved discount_rate must be a decimal fraction from 0 through 1", result["mappingDiagnostics"]["blockers"])

    def test_test1_fallback(self):
        result = test1_enrichment({"county_fips":"00000"})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["results"], {})

    def test_memo_does_not_invent(self):
        memo = diligence_summary(self.deal, self.approved, [])
        self.assertTrue(memo["draft"])
        self.assertEqual(len(memo["approvedFacts"]), 1)

    def test_local_model_rejects_external_hosts(self):
        self.assertEqual(validate_local_endpoint("http://127.0.0.1:11434"), "http://127.0.0.1:11434")
        with self.assertRaises(ValueError): validate_local_endpoint("https://models.example.com")


class Test1SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        synthetic_test1_data(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_static_directory_shapes_load_with_integrity(self):
        snapshot = load_snapshot(self.root)
        self.assertEqual(snapshot["schemaVersion"], "test1-local-data-directory/1.0")
        self.assertEqual(snapshot["sourceLastUpdated"], "2026-07-31")
        self.assertEqual(len(snapshot["integrity"]["map_data.json"]["sha256"]), 64)

    def test_enrichment_is_cited_conservative_and_network_free(self):
        result = test1_enrichment({"county_fips":"51107", "address":"100 Fictional Street"}, load_snapshot(self.root))
        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["verified"])
        self.assertEqual(result["networkRequests"], 0)
        self.assertEqual(result["results"]["policy"]["citations"][0]["url"], "https://example.gov/policy")
        self.assertEqual(result["results"]["waterStress"]["label"], "High")
        self.assertEqual(result["results"]["facilities"]["knownCapacityMw"], "25.5")
        self.assertIn(result["snapshot"]["freshness"]["status"], {"current", "stale"})
        self.assertEqual(result["snapshot"]["datasetDates"]["waterStress"], "2024-01")

    def test_enrichment_requires_approved_quality_fips_input(self):
        result = test1_enrichment({"county_fips":None}, load_snapshot(self.root))
        self.assertEqual(result["status"], "input_required")
        self.assertEqual(result["coverage"], "missing")
        self.assertEqual(result["results"], {})

    def test_state_only_context_is_not_claimed_as_county_match(self):
        result = test1_enrichment({"county_fips":"51001"}, load_snapshot(self.root))
        self.assertEqual(result["status"], "state_only")
        self.assertEqual(result["coverage"], "state_only")
        self.assertIsNone(result["results"]["policy"])

    def test_invalid_test1_schema_fails_explicitly(self):
        (self.root / "platform_metadata.json").write_text(json.dumps({"_schema":"unknown"}), encoding="utf-8")
        with self.assertRaisesRegex(Test1SnapshotError, "metadata schema"):
            load_snapshot(self.root)

    def test_duplicate_json_keys_are_rejected(self):
        (self.root / "platform_metadata.json").write_text('{"_schema":"platform_metadata_v1","_schema":"other"}', encoding="utf-8")
        with self.assertRaisesRegex(Test1SnapshotError, "duplicate key"):
            load_snapshot(self.root)

    def test_service_uses_only_reviewed_county_fips_and_local_directory(self):
        app_data = self.root / "app"
        service = Service(app_data, test1_data_dir=self.root)
        user = service.seed()
        deal_id = service.bootstrap()["deals"][0]["id"]
        before = service.export(user["organization_id"], user["id"], deal_id, "test1")
        self.assertEqual(before["status"], "input_required")
        assumption = service.create_assumption(user["organization_id"], user["id"], deal_id, {"field_name":"county_fips", "proposed_value":"51107", "rationale":"Fictional official parcel record"})
        pending = service.export(user["organization_id"], user["id"], deal_id, "test1")
        self.assertEqual(pending["status"], "input_required")
        service.review_assumption(user["organization_id"], user["id"], assumption["id"], "approved", "51107", "Checked fictional source")
        matched = service.export(user["organization_id"], user["id"], deal_id, "test1")
        self.assertEqual(matched["status"], "matched")
        self.assertEqual(matched["results"]["countyFips"], "51107")

    def test_invalid_county_fips_cannot_be_approved(self):
        service = Service(self.root / "fips-app", test1_data_dir=self.root)
        user = service.seed()
        deal_id = service.bootstrap()["deals"][0]["id"]
        assumption = service.create_assumption(user["organization_id"], user["id"], deal_id, {"field_name":"county_fips", "proposed_value":"ABCDE", "rationale":"Invalid fictional value"})
        with self.assertRaisesRegex(ValueError, "registered fips type"):
            service.review_assumption(user["organization_id"], user["id"], assumption["id"], "approved", "ABCDE", "No")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.temp.name), max_upload_bytes=100_000)
        self.user = self.service.seed()
        self.deal_id = self.service.bootstrap()["deals"][0]["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_end_to_end_review_and_export(self):
        upload = self.service.upload(self.user["organization_id"], self.user["id"], self.deal_id, "fictional-offering-memorandum.csv", b"Property Name,Asking Price\nFictional Plaza,10000000\n")
        self.assertEqual(upload["status"], "extracted")
        snapshot = self.service.deal(self.deal_id, self.user["organization_id"])
        value = snapshot["values"][0]
        self.service.review_value(self.user["organization_id"], self.user["id"], value["id"], "approved", value["normalized_value"], "checked")
        export = self.service.export(self.user["organization_id"], self.user["id"], self.deal_id, "test2")
        self.assertEqual(export["mappingDiagnostics"]["approvedFieldCount"], 1)
        self.assertEqual(export["sourceDocumentHashes"], [hashlib.sha256(b"Property Name,Asking Price\nFictional Plaza,10000000\n").hexdigest()])

    def test_duplicate_detection(self):
        content = b"Tenant,Rent\nExample,100\n"
        self.service.upload(self.user["organization_id"], self.user["id"], self.deal_id, "rent-roll.csv", content)
        with self.assertRaisesRegex(ValueError, "Duplicate upload"):
            self.service.upload(self.user["organization_id"], self.user["id"], self.deal_id, "copy.csv", content)

    def test_organization_isolation(self):
        with self.assertRaises(LookupError): self.service.deal(self.deal_id, "other-org")

    def test_review_decisions_are_append_only_and_source_value_is_immutable(self):
        self.service.upload(self.user["organization_id"], self.user["id"], self.deal_id, "fictional.csv", b"Property Name\nOriginal Plaza\n")
        candidate = self.service.deal(self.deal_id, self.user["organization_id"])["values"][0]
        result = self.service.review_value(self.user["organization_id"], self.user["id"], candidate["id"], "approved", "Reviewed Plaza", "Source checked")
        reviewed = next(item for item in self.service.deal(self.deal_id, self.user["organization_id"])["values"] if item["id"] == candidate["id"])
        self.assertEqual(reviewed["normalized_value"], "Reviewed Plaza")
        self.assertEqual(reviewed["extracted_normalized_value"], "Original Plaza")
        self.assertEqual(reviewed["latest_decision_id"], result["decision_id"])
        with self.service.db.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE review_decisions SET comments='changed' WHERE id=?", (result["decision_id"],))
        self.assertEqual(self.service.db.verify_review_chain(self.user["organization_id"]), (True, None))

    def test_manual_assumption_review_supersedes_prior_controlling_value(self):
        first = self.service.create_assumption(self.user["organization_id"], self.user["id"], self.deal_id, {"field_name":"discount_rate", "proposed_value":"0.08", "rationale":"Fictional committee case"})
        self.service.review_assumption(self.user["organization_id"], self.user["id"], first["id"], "approved", "0.08", "Approved base case")
        second = self.service.create_assumption(self.user["organization_id"], self.user["id"], self.deal_id, {"field_name":"discount_rate", "proposed_value":"0.09", "rationale":"Fictional downside case"})
        decision = self.service.review_assumption(self.user["organization_id"], self.user["id"], second["id"], "approved", "0.09", "Approved replacement")
        self.assertEqual(decision["superseded"], [first["id"]])
        values = {item["id"]: item for item in self.service.deal(self.deal_id, self.user["organization_id"])["values"]}
        self.assertEqual(values[first["id"]]["review_status"], "superseded")
        self.assertEqual(values[second["id"]]["review_status"], "approved")
        exported = self.service.export(self.user["organization_id"], self.user["id"], self.deal_id, "test2")
        source = next(item for item in exported["supportingSources"] if item["field"] == "discount_rate")
        self.assertEqual(source["sourceType"], "user_entered")
        self.assertIsNone(source["documentId"])
        self.assertEqual(source["rationale"], "Fictional downside case")

    def test_manual_assumption_requires_registered_field_and_rationale(self):
        with self.assertRaisesRegex(ValueError, "registered field"):
            self.service.create_assumption(self.user["organization_id"], self.user["id"], self.deal_id, {"field_name":"invented", "proposed_value":"1", "rationale":"No"})
        with self.assertRaisesRegex(ValueError, "rationale"):
            self.service.create_assumption(self.user["organization_id"], self.user["id"], self.deal_id, {"field_name":"discount_rate", "proposed_value":"0.08", "rationale":""})

    def test_registered_manual_assumption_cannot_be_approved_with_invalid_type(self):
        assumption = self.service.create_assumption(self.user["organization_id"], self.user["id"], self.deal_id, {"field_name":"discount_rate", "proposed_value":"7.5", "rationale":"Ambiguous fictional input"})
        with self.assertRaisesRegex(ValueError, "registered rate type"):
            self.service.review_assumption(self.user["organization_id"], self.user["id"], assumption["id"], "approved", "7.5", "Cannot approve")
        value = next(item for item in self.service.deal(self.deal_id, self.user["organization_id"])["values"] if item["id"] == assumption["id"])
        self.assertEqual(value["review_status"], "needs_review")

    def test_review_chain_tampering_is_detected_if_database_controls_are_bypassed(self):
        assumption = self.service.create_assumption(self.user["organization_id"], self.user["id"], self.deal_id, {"field_name":"discount_rate", "proposed_value":"0.08", "rationale":"Fictional case"})
        decision = self.service.review_assumption(self.user["organization_id"], self.user["id"], assumption["id"], "approved", "0.08", "Approved")
        with self.service.db.connect() as connection:
            connection.execute("DROP TRIGGER review_decisions_no_update")
            connection.execute("UPDATE review_decisions SET comments='tampered' WHERE id=?", (decision["decision_id"],))
        self.assertEqual(self.service.db.verify_review_chain(self.user["organization_id"]), (False, decision["decision_id"]))

    def test_audit_chain(self):
        self.service.create_deal(self.user["organization_id"], self.user["id"], {"name":"Second Fictional Deal"})
        with self.service.db.connect() as connection:
            events = connection.execute("SELECT * FROM audit_events WHERE organization_id=? ORDER BY created_at", (self.user["organization_id"],)).fetchall()
        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[1]["previous_hash"], events[0]["event_hash"])
        self.assertEqual(self.service.db.verify_audit_chain(self.user["organization_id"]), (True, None))

    def test_audit_tampering_is_detected(self):
        with self.service.db.connect() as connection:
            event = connection.execute("SELECT id FROM audit_events LIMIT 1").fetchone()
            connection.execute("UPDATE audit_events SET details_json=? WHERE id=?", ('{"tampered":true}', event["id"]))
        valid, broken_id = self.service.db.verify_audit_chain(self.user["organization_id"])
        self.assertFalse(valid)
        self.assertEqual(broken_id, event["id"])

    def test_backup_and_temporary_restore_drill(self):
        content = b"Tenant,Rent\nExample,100\n"
        self.service.upload(self.user["organization_id"], self.user["id"], self.deal_id, "rent-roll.csv", content)
        destination = Path(self.temp.name) / "backup.zip"
        create_backup(Path(self.temp.name), destination)
        report = verify_backup(destination)
        self.assertTrue(report["valid"])
        self.assertEqual(report["format"], "test3-backup/2.0")
        self.assertEqual(report["counts"]["documents"], 1)
        self.assertGreaterEqual(report["fileCount"], 2)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            create_backup(Path(self.temp.name), destination)


if __name__ == "__main__":
    unittest.main()
