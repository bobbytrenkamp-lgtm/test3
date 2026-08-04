from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adapters import diligence_summary, test1_enrichment, test2_export
from .auth import hash_password
from .classification import classify
from .db import Database, now
from .extraction import process
from .reconciliation import as_dicts, reconcile
from .security import sha256_bytes, validate_upload


class Service:
    def __init__(self, data_dir: Path, max_upload_bytes: int = 50 * 1024 * 1024):
        self.data_dir = data_dir.resolve()
        self.upload_dir = self.data_dir / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "test3.db")
        self.max_upload_bytes = max_upload_bytes

    def seed(self) -> dict:
        with self.db.connect() as connection:
            existing = connection.execute("SELECT id FROM organizations LIMIT 1").fetchone()
            if existing:
                user = connection.execute("SELECT * FROM users LIMIT 1").fetchone()
                return {key: user[key] for key in ("id", "organization_id", "email", "display_name", "role")}
            org_id, user_id, deal_id, created = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), now()
            connection.execute("INSERT INTO organizations VALUES(?,?,?)", (org_id, "Fictional CRE Partners", created))
            connection.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (user_id, org_id, "analyst@example.test", "Casey Analyst", "admin", hash_password("fictional-demo"), created))
            connection.execute("INSERT INTO deals VALUES(?,?,?,?,?,?,?,?,?)", (deal_id, org_id, "Harbor Point Offices (Fictional)", "100 Example Avenue, Baltimore, MD", "office", "needs_review", user_id, created, created))
        self.db.audit(org_id, user_id, "deal.created", "deal", deal_id, {"fictional": True}, deal_id)
        return {"id": user_id, "organization_id": org_id, "email": "analyst@example.test", "display_name": "Casey Analyst", "role": "admin"}

    def bootstrap(self, user: dict | None = None) -> dict:
        user = user or self.seed()
        with self.db.connect() as connection:
            deals = [dict(row) for row in connection.execute("SELECT * FROM deals WHERE organization_id=? ORDER BY updated_at DESC", (user["organization_id"],))]
            for deal in deals:
                deal["document_count"] = connection.execute("SELECT COUNT(*) FROM documents WHERE deal_id=?", (deal["id"],)).fetchone()[0]
                deal["finding_count"] = connection.execute("SELECT COUNT(*) FROM findings WHERE deal_id=? AND resolution_status!='resolved'", (deal["id"],)).fetchone()[0]
        return {"user": user, "deals": deals, "zeroCost": True, "localOnly": True}

    def deal(self, deal_id: str, organization_id: str) -> dict:
        with self.db.connect() as connection:
            deal = connection.execute("SELECT * FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone()
            if not deal:
                raise LookupError("Deal not found")
            documents = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE deal_id=? AND organization_id=? ORDER BY uploaded_at DESC", (deal_id, organization_id))]
            values = [dict(row) for row in connection.execute("SELECT * FROM extracted_values WHERE deal_id=? AND organization_id=? ORDER BY created_at", (deal_id, organization_id))]
            findings = [dict(row) for row in connection.execute("SELECT * FROM findings WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC", (deal_id, organization_id))]
            audit = [dict(row) for row in connection.execute("SELECT * FROM audit_events WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC LIMIT 100", (deal_id, organization_id))]
        for value in values:
            value["bbox"] = json.loads(value.pop("bbox_json")) if value.get("bbox_json") else None
        for finding in findings:
            for key in ("compared_values_json", "source_documents_json", "page_references_json"):
                finding[key.removesuffix("_json")] = json.loads(finding.pop(key))
        return {"deal": dict(deal), "documents": documents, "values": values, "findings": findings, "audit": audit}

    def create_deal(self, organization_id: str, user_id: str, payload: dict) -> dict:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Deal name is required")
        deal_id, created = str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            connection.execute("INSERT INTO deals VALUES(?,?,?,?,?,?,?,?,?)", (deal_id, organization_id, name[:200], str(payload.get("address", ""))[:500], str(payload.get("property_type", "unknown"))[:50], "not_processed", user_id, created, created))
        self.db.audit(organization_id, user_id, "deal.created", "deal", deal_id, {"name": name}, deal_id)
        return {"id": deal_id, "name": name}

    def upload(self, organization_id: str, user_id: str, deal_id: str, filename: str, content: bytes) -> dict:
        safe_name, mime = validate_upload(filename, content, self.max_upload_bytes)
        digest = sha256_bytes(content)
        with self.db.connect() as connection:
            if not connection.execute("SELECT id FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone():
                raise LookupError("Deal not found")
            duplicate = connection.execute("SELECT * FROM documents WHERE deal_id=? AND sha256=?", (deal_id, digest)).fetchone()
            if duplicate:
                raise ValueError(f"Duplicate upload: document {duplicate['id']} already has this SHA-256 hash")
        document_id = str(uuid.uuid4())
        stored_name = f"{document_id}{Path(safe_name).suffix.lower()}"
        destination = (self.upload_dir / organization_id / deal_id / stored_name).resolve()
        expected_root = (self.upload_dir / organization_id / deal_id).resolve()
        if expected_root not in destination.parents:
            raise ValueError("Unsafe storage path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        initial_category, classification_confidence = classify(safe_name)
        try:
            status, candidates, error = process(safe_name, mime, content, initial_category)
        except Exception as processing_error:
            status, candidates, error = "failed", [], f"Processor failed safely: {type(processing_error).__name__}"
        category, confidence = classify(safe_name, "\n".join(candidate.excerpt for candidate in candidates))
        category = category if confidence >= classification_confidence else initial_category
        created = now()
        with self.db.connect() as connection:
            connection.execute("INSERT INTO documents(id,organization_id,deal_id,original_name,stored_name,detected_mime,category,sha256,size_bytes,uploader_id,uploaded_at,processing_status,malware_scan_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (document_id, organization_id, deal_id, safe_name, stored_name, mime, category, digest, len(content), user_id, created, status, "not_available"))
            connection.execute("INSERT INTO document_versions VALUES(?,?,?,?,?)", (str(uuid.uuid4()), document_id, 1, "test3-deterministic/2.0", created))
            for candidate in candidates:
                value_id = str(uuid.uuid4())
                source_hash = hashlib.sha256(candidate.excerpt.encode()).hexdigest()
                connection.execute("INSERT INTO extracted_values(id,organization_id,deal_id,document_id,document_version,document_category,field_name,raw_value,normalized_value,unit,currency,page_number,bbox_json,source_excerpt,source_text_hash,extraction_method,extractor_version,confidence,validation_status,review_status,reviewer_id,reviewed_at,comments,superseded_value_id,final_approved_value_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (value_id, organization_id, deal_id, document_id, 1, category, candidate.field, candidate.raw, candidate.normalized, candidate.unit, candidate.currency, candidate.page, json.dumps(candidate.bbox) if candidate.bbox else None, candidate.excerpt, source_hash, candidate.method, "2.0", candidate.confidence, "valid" if candidate.normalized is not None else "needs_review", "needs_review", None, None, error, None, None, created))
        self.db.audit(organization_id, user_id, "document.uploaded", "document", document_id, {"sha256": digest, "size": len(content), "mime": mime, "category": category, "processing": status, "warning": error}, deal_id)
        return {"id": document_id, "category": category, "status": status, "sha256": digest, "candidates": len(candidates), "warning": error}

    def review_value(self, organization_id: str, user_id: str, value_id: str, status: str, normalized_value: str | None, comments: str = "") -> dict:
        if status not in ("approved", "rejected", "needs_review"):
            raise ValueError("Invalid review status")
        with self.db.connect() as connection:
            value = connection.execute("SELECT * FROM extracted_values WHERE id=? AND organization_id=?", (value_id, organization_id)).fetchone()
            if not value:
                raise LookupError("Extracted value not found")
            reviewed = now()
            final_id = value_id if status == "approved" else None
            connection.execute("UPDATE extracted_values SET normalized_value=?, review_status=?, reviewer_id=?, reviewed_at=?, comments=?, final_approved_value_id=? WHERE id=?", (normalized_value, status, user_id, reviewed, comments[:2000], final_id, value_id))
        self.db.audit(organization_id, user_id, f"value.{status}", "extracted_value", value_id, {"normalized_value": normalized_value, "comments": comments}, value["deal_id"])
        return {"id": value_id, "review_status": status, "reviewed_at": reviewed}

    def run_reconciliation(self, organization_id: str, user_id: str, deal_id: str) -> list[dict]:
        with self.db.connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT e.*, d.original_name FROM extracted_values e JOIN documents d ON d.id=e.document_id WHERE e.deal_id=? AND e.organization_id=? AND e.review_status!='rejected'", (deal_id, organization_id))]
            values = {}
            for row in rows:
                values[row["field_name"]] = row["normalized_value"]
                values[f"{row['field_name']}__document"] = row["original_name"]
                values[f"{row['field_name']}__page"] = row["page_number"]
            results = as_dicts(reconcile(values))
            connection.execute("DELETE FROM findings WHERE deal_id=? AND organization_id=? AND resolution_status='open'", (deal_id, organization_id))
            created = now()
            for item in results:
                connection.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), organization_id, deal_id, item["rule_code"], item["severity"], item["explanation"], json.dumps(item["compared_values"]), json.dumps(item["source_documents"]), json.dumps(item["page_references"]), item["suggested_next_step"], "open", None, created))
        self.db.audit(organization_id, user_id, "reconciliation.completed", "deal", deal_id, {"finding_count": len(results), "rule_engine": "1.0"}, deal_id)
        return results

    def resolve_finding(self, organization_id: str, user_id: str, finding_id: str, notes: str) -> dict:
        if not notes.strip():
            raise ValueError("Resolution notes are required")
        with self.db.connect() as connection:
            finding = connection.execute("SELECT * FROM findings WHERE id=? AND organization_id=?", (finding_id, organization_id)).fetchone()
            if not finding:
                raise LookupError("Finding not found")
            connection.execute("UPDATE findings SET resolution_status='resolved', resolution_notes=? WHERE id=?", (notes[:4000], finding_id))
        self.db.audit(organization_id, user_id, "finding.resolved", "finding", finding_id, {"notes": notes}, finding["deal_id"])
        return {"id": finding_id, "resolution_status": "resolved"}

    def export(self, organization_id: str, user_id: str, deal_id: str, kind: str) -> dict:
        snapshot = self.deal(deal_id, organization_id)
        approved = [item for item in snapshot["values"] if item["review_status"] == "approved"]
        documents_by_id = {item["id"]: item for item in snapshot["documents"]}
        for item in approved:
            item["document_sha256"] = documents_by_id[item["document_id"]]["sha256"]
        if kind == "test2":
            result = test2_export(snapshot["deal"], approved, snapshot["findings"])
        elif kind == "memo":
            result = diligence_summary(snapshot["deal"], approved, snapshot["findings"])
        elif kind == "test1":
            result = test1_enrichment({"address": snapshot["deal"]["address"]})
        else:
            raise ValueError("Unknown export kind")
        self.db.audit(organization_id, user_id, f"export.{kind}", "deal", deal_id, {"approved_count": len(approved)}, deal_id)
        return result
