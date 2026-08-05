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
from .extraction import normalize_value, process
from .field_registry import FIELD_BY_NAME
from .reconciliation import as_dicts, reconcile
from .security import sha256_bytes, validate_upload
from .test1_snapshot import Test1SnapshotError, load_snapshot


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Service:
    def __init__(self, data_dir: Path, max_upload_bytes: int = 50 * 1024 * 1024, test1_data_dir: Path | None = None):
        self.data_dir = data_dir.resolve()
        self.upload_dir = self.data_dir / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "test3.db")
        self.max_upload_bytes = max_upload_bytes
        self.test1_data_dir = test1_data_dir.resolve() if test1_data_dir else None
        self._recover_purge_staging()

    @staticmethod
    def _strict_json(path: Path) -> dict:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate staging metadata key")
                result[key] = value
            return result
        if path.stat().st_size > 16_384:
            raise ValueError("staging metadata exceeds safety limit")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
        if not isinstance(value, dict):
            raise ValueError("staging metadata must be an object")
        return value

    def _recover_purge_staging(self) -> None:
        staging_root = (self.data_dir / ".purge-staging").resolve()
        if not staging_root.is_dir():
            return
        for metadata_path in sorted(staging_root.glob("*.json")):
            try:
                metadata = self._strict_json(metadata_path)
                required = {"purge_id", "organization_id", "deal_id", "document_id", "stored_name", "sha256", "size_bytes"}
                if set(metadata) != required or metadata_path.stem != metadata["purge_id"]:
                    raise ValueError("staging metadata contract mismatch")
                staged = (staging_root / f"{metadata['purge_id']}.bin").resolve()
                original = (self.upload_dir / metadata["organization_id"] / metadata["deal_id"] / metadata["stored_name"]).resolve()
                if staging_root not in staged.parents or self.upload_dir.resolve() not in original.parents:
                    raise ValueError("unsafe staged or original path")
                with self.db.connect() as connection:
                    document = connection.execute("SELECT * FROM documents WHERE id=? AND organization_id=? AND deal_id=?", (metadata["document_id"], metadata["organization_id"], metadata["deal_id"])).fetchone()
                    purge = connection.execute("SELECT id FROM document_purges WHERE id=? AND document_id=?", (metadata["purge_id"], metadata["document_id"])).fetchone()
                if not document or document["stored_name"] != metadata["stored_name"] or document["sha256"] != metadata["sha256"] or document["size_bytes"] != metadata["size_bytes"]:
                    raise ValueError("staging metadata does not match the document tombstone")
                committed = purge is not None and document["original_purged_at"] is not None
                if staged.is_file():
                    if staged.stat().st_size != metadata["size_bytes"] or _sha256_file(staged) != metadata["sha256"]:
                        raise ValueError("staged original failed size or SHA-256 verification")
                    if committed:
                        staged.unlink()
                        action = "document.purge_cleanup_completed"
                    elif original.exists():
                        if original.stat().st_size != metadata["size_bytes"] or _sha256_file(original) != metadata["sha256"]:
                            raise ValueError("original path conflicts with uncommitted staged bytes")
                        staged.unlink()
                        action = "document.purge_duplicate_staging_removed"
                    else:
                        original.parent.mkdir(parents=True, exist_ok=True)
                        staged.replace(original)
                        action = "document.purge_uncommitted_restored"
                elif committed or original.is_file():
                    action = "document.purge_metadata_cleaned"
                else:
                    raise ValueError("both staged and original bytes are missing for an uncommitted purge")
                metadata_path.unlink()
                self.db.audit(metadata["organization_id"], None, action, "document", metadata["document_id"], {"purge_id": metadata["purge_id"], "automatic_recovery": True}, metadata["deal_id"])
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                # Leave uncertain artifacts untouched. The integrity endpoint reports them.
                continue

    def has_users(self) -> bool:
        with self.db.connect() as connection:
            return connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def initialize_admin(self, organization_name: str, email: str, display_name: str, password: str) -> dict:
        organization_name, email, display_name = organization_name.strip(), email.strip().lower(), display_name.strip()
        if not organization_name or not display_name or "@" not in email or len(email) > 254:
            raise ValueError("Organization name, display name and a valid local administrator email are required")
        if len(password) < 16:
            raise ValueError("Institutional administrator passwords must be at least 16 characters")
        org_id, user_id, created = str(uuid.uuid4()), str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise ValueError("A local user already exists; initialization is a first-run operation")
            connection.execute("INSERT INTO organizations VALUES(?,?,?)", (org_id, organization_name[:200], created))
            connection.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (user_id, org_id, email, display_name[:200], "admin", hash_password(password), created))
        self.db.audit(org_id, user_id, "organization.initialized", "organization", org_id, {"local_only": True})
        return {"id": user_id, "organization_id": org_id, "email": email, "display_name": display_name, "role": "admin"}

    def reset_local_password(self, email: str, password: str) -> dict:
        if len(password) < 16:
            raise ValueError("Institutional administrator passwords must be at least 16 characters")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            users = connection.execute("SELECT * FROM users WHERE lower(email)=? LIMIT 2", (email.strip().lower(),)).fetchall()
            if len(users) != 1:
                raise ValueError("The local email must identify exactly one user")
            user = users[0]
            connection.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user["id"]))
            connection.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        self.db.audit(user["organization_id"], user["id"], "user.local_password_reset", "user", user["id"], {"sessions_revoked": True})
        return {"id": user["id"], "email": user["email"], "sessions_revoked": True}

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

    def bootstrap(self, user: dict) -> dict:
        with self.db.connect() as connection:
            deals = [dict(row) for row in connection.execute("SELECT * FROM deals WHERE organization_id=? ORDER BY updated_at DESC", (user["organization_id"],))]
            for deal in deals:
                deal["document_count"] = connection.execute("SELECT COUNT(*) FROM documents WHERE deal_id=?", (deal["id"],)).fetchone()[0]
                deal["finding_count"] = connection.execute("SELECT COUNT(*) FROM findings WHERE deal_id=? AND resolution_status='open'", (deal["id"],)).fetchone()[0]
        public_user = {key: user[key] for key in ("id", "organization_id", "email", "display_name", "role") if key in user}
        if "csrf_token" in user:
            public_user["csrf_token"] = user["csrf_token"]
        return {
            "user": public_user, "deals": deals, "zeroCost": True, "localOnly": True,
            "manualAssumptionFields": [
                {"name": field.name, "label": field.label, "unit": field.unit, "currency": field.currency}
                for field in FIELD_BY_NAME.values()
            ],
        }

    def deal(self, deal_id: str, organization_id: str) -> dict:
        with self.db.connect() as connection:
            deal = connection.execute("SELECT * FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone()
            if not deal:
                raise LookupError("Deal not found")
            documents = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE deal_id=? AND organization_id=? ORDER BY uploaded_at DESC", (deal_id, organization_id))]
            values = [dict(row) for row in connection.execute("SELECT * FROM extracted_values WHERE deal_id=? AND organization_id=? ORDER BY created_at", (deal_id, organization_id))]
            assumptions = [dict(row) for row in connection.execute("SELECT * FROM manual_assumptions WHERE deal_id=? AND organization_id=? ORDER BY created_at", (deal_id, organization_id))]
            decisions = [dict(row) for row in connection.execute("SELECT * FROM review_decisions WHERE deal_id=? AND organization_id=? ORDER BY rowid", (deal_id, organization_id))]
            findings = [dict(row) for row in connection.execute("SELECT * FROM findings WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC", (deal_id, organization_id))]
            audit = [dict(row) for row in connection.execute("SELECT * FROM audit_events WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC LIMIT 100", (deal_id, organization_id))]
        latest_decision = {(item["entity_type"], item["entity_id"]): item for item in decisions}
        for value in values:
            value["bbox"] = json.loads(value.pop("bbox_json")) if value.get("bbox_json") else None
            value["source_kind"] = "document"
            value["entity_type"] = "extracted_value"
            value["extracted_normalized_value"] = value["normalized_value"]
            decision = latest_decision.get(("extracted_value", value["id"]))
            if decision:
                value["normalized_value"] = decision["proposed_normalized_value"]
                value["latest_decision_id"] = decision["id"]
        for assumption in assumptions:
            decision = latest_decision.get(("manual_assumption", assumption["id"]))
            values.append({
                **assumption,
                "entity_type": "manual_assumption", "source_kind": "user_entered",
                "document_id": None, "document_version": None,
                "document_category": "user_entered_assumption",
                "raw_value": assumption["proposed_value"],
                "normalized_value": decision["proposed_normalized_value"] if decision else assumption["proposed_value"],
                "page_number": None, "bbox": None,
                "source_excerpt": assumption["rationale"],
                "source_text_hash": hashlib.sha256(assumption["rationale"].encode()).hexdigest(),
                "extraction_method": "user_entered", "extractor_version": "1.0",
                "confidence": 1.0, "validation_status": "user_entered",
                "comments": decision["comments"] if decision else None,
                "latest_decision_id": decision["id"] if decision else None,
            })
        for finding in findings:
            for key in ("compared_values_json", "source_documents_json", "page_references_json"):
                finding[key.removesuffix("_json")] = json.loads(finding.pop(key))
        return {"deal": dict(deal), "documents": documents, "values": values, "findings": findings, "audit": audit, "review_decisions": decisions}

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

    def purge_original_document(self, organization_id: str, user_id: str, document_id: str, reason: str) -> dict:
        reason = str(reason or "").strip()
        if len(reason) < 12:
            raise ValueError("A specific purge reason of at least 12 characters is required")
        with self.db.connect() as connection:
            document = connection.execute("SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)).fetchone()
        if not document:
            raise LookupError("Document not found")
        if document["original_purged_at"]:
            raise ValueError("The original document bytes were already purged")
        path = (self.upload_dir / organization_id / document["deal_id"] / document["stored_name"]).resolve()
        if self.upload_dir.resolve() not in path.parents or not path.is_file():
            raise ValueError("The original document is missing or has an unsafe storage path")
        content = path.read_bytes()
        if len(content) != document["size_bytes"] or hashlib.sha256(content).hexdigest() != document["sha256"]:
            raise ValueError("The stored original failed its recorded size or SHA-256 integrity check")
        purge_id, created = str(uuid.uuid4()), now()
        staging_root = (self.data_dir / ".purge-staging").resolve()
        staging_root.mkdir(parents=True, exist_ok=True)
        staged = staging_root / f"{purge_id}.bin"
        metadata_path = staging_root / f"{purge_id}.json"
        metadata = {"purge_id": purge_id, "organization_id": organization_id, "deal_id": document["deal_id"], "document_id": document_id, "stored_name": document["stored_name"], "sha256": document["sha256"], "size_bytes": document["size_bytes"]}
        with metadata_path.open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        path.replace(staged)
        try:
            with self.db.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = connection.execute("SELECT original_purged_at FROM documents WHERE id=? AND organization_id=?", (document_id, organization_id)).fetchone()
                if not current or current["original_purged_at"]:
                    raise ValueError("The document purge state changed; no purge was completed")
                connection.execute("UPDATE documents SET original_purged_at=?,original_purged_by=?,original_purge_reason=?,processing_status='purged' WHERE id=?", (created, user_id, reason[:4000], document_id))
                connection.execute("INSERT INTO document_purges VALUES(?,?,?,?,?,?,?,?,?)", (purge_id, organization_id, document["deal_id"], document_id, user_id, document["sha256"], document["size_bytes"], reason[:4000], created))
        except Exception:
            if staged.exists() and not path.exists():
                staged.replace(path)
            metadata_path.unlink(missing_ok=True)
            raise
        cleanup_pending = False
        try:
            staged.unlink()
            metadata_path.unlink()
        except OSError:
            cleanup_pending = True
        self.db.audit(organization_id, user_id, "document.original_purged", "document", document_id, {"purge_id": purge_id, "sha256": document["sha256"], "size": document["size_bytes"], "reason": reason[:4000]}, document["deal_id"])
        return {"id": document_id, "original_purged_at": created, "purge_id": purge_id, "metadata_retained": True, "cleanup_pending": cleanup_pending}

    def operational_integrity(self, organization_id: str) -> dict:
        database = self.db.health()
        audit_valid, audit_break = self.db.verify_audit_chain(organization_id)
        review_valid, review_break = self.db.verify_review_chain(organization_id)
        with self.db.connect() as connection:
            documents = connection.execute("SELECT deal_id,stored_name,sha256,size_bytes,original_purged_at FROM documents WHERE organization_id=?", (organization_id,)).fetchall()
            artifacts = connection.execute("SELECT id,content_json,content_sha256,approval_snapshot_json,approval_snapshot_sha256 FROM export_artifacts WHERE organization_id=?", (organization_id,)).fetchall()
        storage = {"activeOriginals": 0, "purgedTombstones": 0, "missingActiveOriginals": 0, "integrityMismatches": 0, "unexpectedPurgedOriginals": 0, "unsafePaths": 0}
        upload_root = self.upload_dir.resolve()
        for document in documents:
            path = (self.upload_dir / organization_id / document["deal_id"] / document["stored_name"]).resolve()
            if upload_root not in path.parents:
                storage["unsafePaths"] += 1
                continue
            if document["original_purged_at"]:
                storage["purgedTombstones"] += 1
                if path.exists():
                    storage["unexpectedPurgedOriginals"] += 1
                continue
            storage["activeOriginals"] += 1
            if not path.is_file():
                storage["missingActiveOriginals"] += 1
                continue
            if path.stat().st_size != document["size_bytes"] or _sha256_file(path) != document["sha256"]:
                storage["integrityMismatches"] += 1
        staging_root = self.data_dir / ".purge-staging"
        staging_files = sum(1 for item in staging_root.iterdir() if item.is_file()) if staging_root.is_dir() else 0
        chains = {"auditValid": audit_valid, "auditBreakId": audit_break, "reviewValid": review_valid, "reviewBreakId": review_break}
        storage_ok = not any(storage[key] for key in ("missingActiveOriginals", "integrityMismatches", "unexpectedPurgedOriginals", "unsafePaths")) and staging_files == 0
        artifact_mismatches = sum(
            hashlib.sha256(item["content_json"].encode()).hexdigest() != item["content_sha256"]
            or hashlib.sha256(item["approval_snapshot_json"].encode()).hexdigest() != item["approval_snapshot_sha256"]
            for item in artifacts
        )
        artifact_integrity = {"count": len(artifacts), "hashMismatches": artifact_mismatches}
        return {"ok": database["ok"] and audit_valid and review_valid and storage_ok and artifact_mismatches == 0, "checkedAt": now(), "database": database, "chains": chains, "storage": storage, "exports": artifact_integrity, "purgeStagingFiles": staging_files, "networkRequests": 0}

    def review_value(self, organization_id: str, user_id: str, value_id: str, status: str, normalized_value: str | None, comments: str = "") -> dict:
        normalized_value = None if normalized_value is None else str(normalized_value)
        comments = str(comments or "")
        if status not in ("approved", "rejected", "needs_review"):
            raise ValueError("Invalid review status")
        if status == "approved" and not str(normalized_value or "").strip():
            raise ValueError("An approved normalized value is required")
        if status == "rejected" and not comments.strip():
            raise ValueError("Rejection comments are required")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            value = connection.execute("SELECT * FROM extracted_values WHERE id=? AND organization_id=?", (value_id, organization_id)).fetchone()
            if not value:
                raise LookupError("Extracted value not found")
            if status == "approved":
                normalized_value = self._validated_registered_value(value["field_name"], normalized_value)
            reviewed = now()
            decision_id = self._append_review_decision(connection, organization_id, value["deal_id"], user_id, "extracted_value", value_id, status, normalized_value, comments, reviewed)
            superseded = self._set_controlling_value(connection, organization_id, value["deal_id"], value["field_name"], "extracted_value", value_id) if status == "approved" else []
            final_id = value_id if status == "approved" else None
            connection.execute("UPDATE extracted_values SET review_status=?, reviewer_id=?, reviewed_at=?, comments=?, final_approved_value_id=? WHERE id=?", (status, user_id, reviewed, comments[:2000], final_id, value_id))
        self.db.audit(organization_id, user_id, f"value.{status}", "extracted_value", value_id, {"decision_id": decision_id, "proposed_normalized_value": normalized_value, "comments": comments, "superseded": superseded}, value["deal_id"])
        return {"id": value_id, "review_status": status, "reviewed_at": reviewed, "decision_id": decision_id, "superseded": superseded}

    def create_assumption(self, organization_id: str, user_id: str, deal_id: str, payload: dict) -> dict:
        field_name = str(payload.get("field_name", "")).strip()
        proposed_value = str(payload.get("proposed_value", "")).strip()
        rationale = str(payload.get("rationale", "")).strip()
        if field_name not in FIELD_BY_NAME:
            raise ValueError("Manual assumptions require a registered field name")
        if not proposed_value:
            raise ValueError("A proposed value is required")
        if not rationale:
            raise ValueError("A source or rationale is required")
        assumption_id, created = str(uuid.uuid4()), now()
        field = FIELD_BY_NAME[field_name]
        with self.db.connect() as connection:
            if not connection.execute("SELECT id FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone():
                raise LookupError("Deal not found")
            connection.execute("INSERT INTO manual_assumptions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (assumption_id, organization_id, deal_id, field_name, proposed_value[:1000], field.unit, field.currency, rationale[:4000], "needs_review", None, None, user_id, created))
        self.db.audit(organization_id, user_id, "assumption.created", "manual_assumption", assumption_id, {"field_name": field_name, "proposed_value": proposed_value, "rationale": rationale}, deal_id)
        return {"id": assumption_id, "field_name": field_name, "review_status": "needs_review"}

    def review_assumption(self, organization_id: str, user_id: str, assumption_id: str, status: str, normalized_value: str | None, comments: str = "") -> dict:
        normalized_value = None if normalized_value is None else str(normalized_value)
        comments = str(comments or "")
        if status not in ("approved", "rejected", "needs_review"):
            raise ValueError("Invalid review status")
        if status == "approved" and not str(normalized_value or "").strip():
            raise ValueError("An approved normalized value is required")
        if status == "rejected" and not comments.strip():
            raise ValueError("Rejection comments are required")
        reviewed = now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            assumption = connection.execute("SELECT * FROM manual_assumptions WHERE id=? AND organization_id=?", (assumption_id, organization_id)).fetchone()
            if not assumption:
                raise LookupError("Manual assumption not found")
            if status == "approved":
                normalized_value = self._validated_registered_value(assumption["field_name"], normalized_value)
            decision_id = self._append_review_decision(connection, organization_id, assumption["deal_id"], user_id, "manual_assumption", assumption_id, status, normalized_value, comments, reviewed)
            superseded = self._set_controlling_value(connection, organization_id, assumption["deal_id"], assumption["field_name"], "manual_assumption", assumption_id) if status == "approved" else []
            connection.execute("UPDATE manual_assumptions SET review_status=?, reviewer_id=?, reviewed_at=? WHERE id=?", (status, user_id, reviewed, assumption_id))
        self.db.audit(organization_id, user_id, f"assumption.{status}", "manual_assumption", assumption_id, {"decision_id": decision_id, "proposed_normalized_value": normalized_value, "comments": comments, "superseded": superseded}, assumption["deal_id"])
        return {"id": assumption_id, "review_status": status, "reviewed_at": reviewed, "decision_id": decision_id, "superseded": superseded}

    @staticmethod
    def _append_review_decision(connection, organization_id: str, deal_id: str, actor_id: str, entity_type: str, entity_id: str, decision: str, proposed_value: str | None, comments: str, created: str) -> str:
        previous = connection.execute("SELECT decision_hash FROM review_decisions WHERE organization_id=? ORDER BY rowid DESC LIMIT 1", (organization_id,)).fetchone()
        previous_hash = previous[0] if previous else None
        decision_id = str(uuid.uuid4())
        payload = json.dumps({"id": decision_id, "organization_id": organization_id, "deal_id": deal_id, "actor_id": actor_id, "entity_type": entity_type, "entity_id": entity_id, "decision": decision, "proposed_normalized_value": proposed_value, "comments": comments[:2000], "previous": previous_hash, "created_at": created}, sort_keys=True)
        decision_hash = hashlib.sha256(payload.encode()).hexdigest()
        connection.execute("INSERT INTO review_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (decision_id, organization_id, deal_id, actor_id, entity_type, entity_id, decision, proposed_value, comments[:2000], previous_hash, decision_hash, created))
        return decision_id

    @staticmethod
    def _validated_registered_value(field_name: str, proposed_value: str | None) -> str:
        field = FIELD_BY_NAME.get(field_name)
        if not field:
            return str(proposed_value).strip()
        normalized = normalize_value(str(proposed_value), field.value_type, field.unit)
        if normalized is None:
            raise ValueError(f"Approved {field_name} does not satisfy its registered {field.value_type} type")
        return normalized

    @staticmethod
    def _set_controlling_value(connection, organization_id: str, deal_id: str, field_name: str, entity_type: str, entity_id: str) -> list[str]:
        extracted = [row[0] for row in connection.execute("SELECT id FROM extracted_values WHERE organization_id=? AND deal_id=? AND field_name=? AND review_status='approved' AND id!=?", (organization_id, deal_id, field_name, entity_id if entity_type == "extracted_value" else ""))]
        manual = [row[0] for row in connection.execute("SELECT id FROM manual_assumptions WHERE organization_id=? AND deal_id=? AND field_name=? AND review_status='approved' AND id!=?", (organization_id, deal_id, field_name, entity_id if entity_type == "manual_assumption" else ""))]
        for old_id in extracted:
            connection.execute("UPDATE extracted_values SET review_status='superseded', final_approved_value_id=? WHERE id=?", (entity_id if entity_type == "extracted_value" else None, old_id))
        for old_id in manual:
            connection.execute("UPDATE manual_assumptions SET review_status='superseded' WHERE id=?", (old_id,))
        return [*extracted, *manual]

    def run_reconciliation(self, organization_id: str, user_id: str, deal_id: str) -> list[dict]:
        snapshot = self.deal(deal_id, organization_id)
        documents_by_id = {item["id"]: item for item in snapshot["documents"]}
        active = [item for item in snapshot["values"] if item["review_status"] not in ("rejected", "superseded")]
        values = {}
        for row in active:
            values[row["field_name"]] = row["normalized_value"]
            document = documents_by_id.get(row.get("document_id"))
            values[f"{row['field_name']}__document"] = document["original_name"] if document else "User-entered assumption"
            values[f"{row['field_name']}__page"] = row.get("page_number")
        results = as_dicts(reconcile(values))
        input_hash = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
        run_id, created = str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE findings SET resolution_status='superseded', superseded_at=? WHERE deal_id=? AND organization_id=? AND resolution_status='open'", (created, deal_id, organization_id))
            connection.execute("INSERT INTO reconciliation_runs VALUES(?,?,?,?,?,?,?,?)", (run_id, organization_id, deal_id, user_id, "1.0", input_hash, len(results), created))
            for item in results:
                connection.execute("INSERT INTO findings(id,organization_id,deal_id,rule_code,severity,explanation,compared_values_json,source_documents_json,page_references_json,suggested_next_step,resolution_status,resolution_notes,created_at,reconciliation_run_id,superseded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), organization_id, deal_id, item["rule_code"], item["severity"], item["explanation"], json.dumps(item["compared_values"]), json.dumps(item["source_documents"]), json.dumps(item["page_references"]), item["suggested_next_step"], "open", None, created, run_id, None))
        self.db.audit(organization_id, user_id, "reconciliation.completed", "reconciliation_run", run_id, {"finding_count": len(results), "rule_engine": "1.0", "input_sha256": input_hash}, deal_id)
        return results

    def resolve_finding(self, organization_id: str, user_id: str, finding_id: str, notes: str) -> dict:
        if not notes.strip():
            raise ValueError("Resolution notes are required")
        with self.db.connect() as connection:
            finding = connection.execute("SELECT * FROM findings WHERE id=? AND organization_id=?", (finding_id, organization_id)).fetchone()
            if not finding:
                raise LookupError("Finding not found")
            if finding["resolution_status"] != "open":
                raise ValueError("Only an open finding can be resolved")
            connection.execute("UPDATE findings SET resolution_status='resolved', resolution_notes=? WHERE id=?", (notes[:4000], finding_id))
        self.db.audit(organization_id, user_id, "finding.resolved", "finding", finding_id, {"notes": notes}, finding["deal_id"])
        return {"id": finding_id, "resolution_status": "resolved"}

    def export(self, organization_id: str, user_id: str, deal_id: str, kind: str) -> dict:
        snapshot = self.deal(deal_id, organization_id)
        approved = [item for item in snapshot["values"] if item["review_status"] == "approved"]
        documents_by_id = {item["id"]: item for item in snapshot["documents"]}
        for item in approved:
            document = documents_by_id.get(item.get("document_id"))
            item["document_sha256"] = document["sha256"] if document else None
        if kind == "test2":
            result = test2_export(snapshot["deal"], approved, snapshot["findings"])
        elif kind == "memo":
            result = diligence_summary(snapshot["deal"], approved, snapshot["findings"])
        elif kind == "test1":
            approved_values = {item["field_name"]: item.get("normalized_value") for item in approved}
            inputs = {
                "address": snapshot["deal"]["address"],
                "county_fips": approved_values.get("county_fips"),
                "state": approved_values.get("state") or snapshot["deal"].get("state"),
                "municipality": approved_values.get("municipality"),
                "parcel_id": approved_values.get("parcel_id"),
            }
            try:
                local_snapshot = load_snapshot(self.test1_data_dir) if self.test1_data_dir else None
                result = test1_enrichment(inputs, local_snapshot)
            except Test1SnapshotError as error:
                result = {"status": "invalid_snapshot", "verified": False, "coverage": "missing", "inputs": inputs, "results": {}, "networkRequests": 0, "message": str(error)}
        else:
            raise ValueError("Unknown export kind")
        content_json = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
        result_hash = hashlib.sha256(content_json.encode()).hexdigest()
        approval_snapshot = [
            {
                "entityId": item["id"], "entityType": item["entity_type"], "field": item["field_name"],
                "normalizedValue": item.get("normalized_value"), "decisionId": item.get("latest_decision_id"),
                "documentId": item.get("document_id"), "documentVersion": item.get("document_version"),
                "sourceTextSha256": item.get("source_text_hash"), "documentSha256": item.get("document_sha256"),
                "reviewerId": item.get("reviewer_id"), "reviewedAt": item.get("reviewed_at"),
            }
            for item in sorted(approved, key=lambda row: (row["field_name"], row["id"]))
        ]
        snapshot_json = json.dumps(approval_snapshot, sort_keys=True, separators=(",", ":"), default=str)
        snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
        artifact_id, created = str(uuid.uuid4()), now()
        schema_version = str(result.get("schemaVersion") or result.get("status") or f"test3-{kind}/1.0")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT id FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone():
                raise LookupError("Deal not found")
            version = connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM export_artifacts WHERE deal_id=? AND kind=?", (deal_id, kind)).fetchone()[0]
            connection.execute("INSERT INTO export_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (artifact_id, organization_id, deal_id, kind, version, schema_version, content_json, result_hash, snapshot_json, snapshot_hash, user_id, created))
        artifact = {"id": artifact_id, "dealId": deal_id, "kind": kind, "version": version, "schemaVersion": schema_version, "contentSha256": result_hash, "approvalSnapshotSha256": snapshot_hash, "approvedCount": len(approval_snapshot), "actorId": user_id, "createdAt": created}
        self.db.audit(organization_id, user_id, f"export.{kind}", "export_artifact", artifact_id, artifact, deal_id)
        return {"artifact": artifact, "content": result}

    def export_history(self, organization_id: str, deal_id: str) -> list[dict]:
        with self.db.connect() as connection:
            if not connection.execute("SELECT id FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone():
                raise LookupError("Deal not found")
            rows = connection.execute("SELECT id,deal_id,kind,version,schema_version,content_sha256,approval_snapshot_sha256,actor_id,created_at FROM export_artifacts WHERE organization_id=? AND deal_id=? ORDER BY created_at DESC, rowid DESC", (organization_id, deal_id)).fetchall()
        return [{"id": row["id"], "dealId": row["deal_id"], "kind": row["kind"], "version": row["version"], "schemaVersion": row["schema_version"], "contentSha256": row["content_sha256"], "approvalSnapshotSha256": row["approval_snapshot_sha256"], "actorId": row["actor_id"], "createdAt": row["created_at"]} for row in rows]

    def export_artifact(self, organization_id: str, artifact_id: str) -> dict:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM export_artifacts WHERE id=? AND organization_id=?", (artifact_id, organization_id)).fetchone()
        if not row:
            raise LookupError("Export artifact not found")
        content_json, snapshot_json = row["content_json"], row["approval_snapshot_json"]
        if hashlib.sha256(content_json.encode()).hexdigest() != row["content_sha256"] or hashlib.sha256(snapshot_json.encode()).hexdigest() != row["approval_snapshot_sha256"]:
            raise ValueError("Export artifact integrity verification failed")
        artifact = {"id": row["id"], "dealId": row["deal_id"], "kind": row["kind"], "version": row["version"], "schemaVersion": row["schema_version"], "contentSha256": row["content_sha256"], "approvalSnapshotSha256": row["approval_snapshot_sha256"], "actorId": row["actor_id"], "createdAt": row["created_at"]}
        return {"artifact": artifact, "approvalSnapshot": json.loads(snapshot_json), "content": json.loads(content_json)}
