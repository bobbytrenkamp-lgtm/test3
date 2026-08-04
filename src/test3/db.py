from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), email TEXT NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','analyst','reviewer','viewer')), password_hash TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(organization_id,email));
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, csrf_token TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deals(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), name TEXT NOT NULL, address TEXT, property_type TEXT, status TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), original_name TEXT NOT NULL, stored_name TEXT NOT NULL, detected_mime TEXT NOT NULL, category TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, uploader_id TEXT NOT NULL REFERENCES users(id), uploaded_at TEXT NOT NULL, processing_status TEXT NOT NULL, malware_scan_status TEXT NOT NULL DEFAULT 'not_available', UNIQUE(deal_id,sha256));
CREATE TABLE IF NOT EXISTS document_versions(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), version INTEGER NOT NULL, extractor_version TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(document_id,version));
CREATE TABLE IF NOT EXISTS extracted_values(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), document_id TEXT NOT NULL REFERENCES documents(id), document_version INTEGER NOT NULL, document_category TEXT NOT NULL, field_name TEXT NOT NULL, raw_value TEXT NOT NULL, normalized_value TEXT, unit TEXT, currency TEXT, page_number INTEGER, bbox_json TEXT, source_excerpt TEXT NOT NULL, source_text_hash TEXT NOT NULL, extraction_method TEXT NOT NULL, extractor_version TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), validation_status TEXT NOT NULL, review_status TEXT NOT NULL, reviewer_id TEXT REFERENCES users(id), reviewed_at TEXT, comments TEXT, superseded_value_id TEXT REFERENCES extracted_values(id), final_approved_value_id TEXT REFERENCES extracted_values(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), rule_code TEXT NOT NULL, severity TEXT NOT NULL, explanation TEXT NOT NULL, compared_values_json TEXT NOT NULL, source_documents_json TEXT NOT NULL, page_references_json TEXT NOT NULL, suggested_next_step TEXT NOT NULL, resolution_status TEXT NOT NULL, resolution_notes TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT, actor_id TEXT REFERENCES users(id), action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT, details_json TEXT NOT NULL, previous_hash TEXT, event_hash TEXT NOT NULL, created_at TEXT NOT NULL);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
            if columns and "token_hash" not in columns:
                # Sessions are deliberately ephemeral; invalidate legacy plaintext-token sessions.
                connection.execute("DROP TABLE sessions")
                connection.execute("CREATE TABLE sessions(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, csrf_token TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL, created_at TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def audit(self, organization_id: str, actor_id: str | None, action: str, entity_type: str, entity_id: str | None, details: dict, deal_id: str | None = None) -> str:
        import hashlib
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT event_hash FROM audit_events WHERE organization_id=? ORDER BY rowid DESC LIMIT 1", (organization_id,)).fetchone()
            event_id, created = str(uuid.uuid4()), now()
            payload = json.dumps({"id": event_id, "organization_id": organization_id, "deal_id": deal_id, "actor_id": actor_id, "action": action, "entity_type": entity_type, "entity_id": entity_id, "details": details, "previous": previous[0] if previous else None, "created_at": created}, sort_keys=True)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            connection.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?,?,?)", (event_id, organization_id, deal_id, actor_id, action, entity_type, entity_id, json.dumps(details), previous[0] if previous else None, digest, created))
            return event_id

    def verify_audit_chain(self, organization_id: str) -> tuple[bool, str | None]:
        import hashlib
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
        previous = None
        for row in rows:
            payload = json.dumps({"id": row["id"], "organization_id": row["organization_id"], "deal_id": row["deal_id"], "actor_id": row["actor_id"], "action": row["action"], "entity_type": row["entity_type"], "entity_id": row["entity_id"], "details": json.loads(row["details_json"]), "previous": previous, "created_at": row["created_at"]}, sort_keys=True)
            if row["previous_hash"] != previous or row["event_hash"] != hashlib.sha256(payload.encode()).hexdigest():
                return False, row["id"]
            previous = row["event_hash"]
        return True, None
