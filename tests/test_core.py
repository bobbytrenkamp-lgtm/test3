from __future__ import annotations

import hashlib
import html
import io
import json
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
from test3.extraction import Candidate, extract_selectable_pdf_text, extract_text_candidates, parse_csv, parse_xlsx, process
from test3.normalization import date, number
from test3.ollama import validate_local_endpoint
from test3.permissions import require
from test3.reconciliation import reconcile
from test3.security import detect_mime, safe_filename, sanitize_text, sha256_bytes, validate_upload
from test3.service import Service


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
        self.assertEqual(result["property"]["name"], "Fictional Plaza")
        self.assertIsNone(result["acquisitionAssumptions"]["purchasePrice"])
        self.assertEqual(result["sourceDocumentHashes"], ["abc"])

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
        self.assertEqual(report["counts"]["documents"], 1)
        self.assertGreaterEqual(report["fileCount"], 2)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            create_backup(Path(self.temp.name), destination)


if __name__ == "__main__":
    unittest.main()
