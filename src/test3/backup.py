from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .db import SCHEMA_VERSION


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(data_dir: Path, destination: Path) -> Path:
    data_dir, destination = data_dir.resolve(), destination.resolve()
    database = data_dir / "test3.db"
    if not database.is_file():
        raise ValueError("test3.db does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("Refusing to overwrite an existing backup")
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "test3.db"
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        files = [(snapshot, "test3.db")]
        upload_root = data_dir / "uploads"
        if upload_root.exists():
            files.extend((path, path.relative_to(data_dir).as_posix()) for path in upload_root.rglob("*") if path.is_file())
        market_root = data_dir / "market-data"
        if market_root.exists():
            files.extend((path, path.relative_to(data_dir).as_posix()) for path in market_root.rglob("*") if path.is_file())
        manifest = {"format": "test3-backup/6.0", "schemaVersion": SCHEMA_VERSION, "createdAt": datetime.now(timezone.utc).isoformat(), "files": {name: {"sha256": _hash(path), "bytes": path.stat().st_size} for path, name in files}}
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, name in files:
                archive.write(path, name)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return destination


def verify_backup(archive_path: Path, max_expanded_bytes: int = 2 * 1024 * 1024 * 1024) -> dict:
    with tempfile.TemporaryDirectory() as temporary, zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if sum(info.file_size for info in infos) > max_expanded_bytes:
            raise ValueError("Backup exceeds expanded-size safety limit")
        if any(Path(info.filename).is_absolute() or ".." in Path(info.filename).parts for info in infos):
            raise ValueError("Backup contains an unsafe path")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") not in ("test3-backup/1.0", "test3-backup/2.0", "test3-backup/3.0", "test3-backup/4.0", "test3-backup/5.0", "test3-backup/6.0"):
            raise ValueError("Unsupported backup format")
        root = Path(temporary)
        archive.extractall(root)
        for name, expected in manifest["files"].items():
            path = (root / name).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                raise ValueError(f"Missing or unsafe backup member: {name}")
            if path.stat().st_size != expected["bytes"] or _hash(path) != expected["sha256"]:
                raise ValueError(f"Backup integrity failed: {name}")
        with closing(sqlite3.connect(root / "test3.db")) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError(f"SQLite integrity check failed: {result}")
            available = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            count_tables = ("organizations", "users", "deals", "documents", "audit_events")
            if manifest["format"] == "test3-backup/2.0":
                count_tables += ("manual_assumptions", "review_decisions")
                if not set(count_tables).issubset(available):
                    raise ValueError("Backup database does not match its 2.0 manifest format")
            if manifest["format"] == "test3-backup/3.0":
                count_tables += ("manual_assumptions", "review_decisions", "reconciliation_runs", "document_purges")
                if manifest.get("schemaVersion") != 1 or not set(count_tables).issubset(available):
                    raise ValueError("Backup database does not match its 3.0 schema/table contract")
            if manifest["format"] == "test3-backup/4.0":
                count_tables += ("manual_assumptions", "review_decisions", "reconciliation_runs", "document_purges", "export_artifacts")
                if manifest.get("schemaVersion") != 2 or not set(count_tables).issubset(available):
                    raise ValueError("Backup database does not match its 4.0 schema/table contract")
            if manifest["format"] == "test3-backup/5.0":
                count_tables += ("manual_assumptions", "review_decisions", "reconciliation_runs", "document_purges", "export_artifacts", "semantic_entities")
                if manifest.get("schemaVersion") != 3 or not set(count_tables).issubset(available):
                    raise ValueError("Backup database does not match its 5.0 schema/table contract")
            if manifest["format"] == "test3-backup/6.0":
                count_tables += ("manual_assumptions", "review_decisions", "reconciliation_runs", "document_purges", "export_artifacts", "semantic_entities", "data_source_snapshots", "market_observations", "model_artifacts", "assumption_runs", "assumption_evidence", "assumption_decision_context", "opportunity_runs")
                if manifest.get("schemaVersion") != SCHEMA_VERSION or not set(count_tables).issubset(available):
                    raise ValueError("Backup database does not match its 6.0 schema/table contract")
            counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in count_tables if table in available}
            organization_ids = [row[0] for row in connection.execute("SELECT id FROM organizations")]
        operational = []
        if manifest["format"] in ("test3-backup/3.0", "test3-backup/4.0", "test3-backup/5.0", "test3-backup/6.0"):
            from .service import Service
            restored = Service(root)
            operational = [restored.operational_integrity(organization_id) for organization_id in organization_ids]
            if not all(report["ok"] for report in operational):
                raise ValueError("Restored application failed operational integrity checks")
    return {"valid": True, "format": manifest["format"], "schemaVersion": manifest.get("schemaVersion"), "counts": counts, "fileCount": len(manifest["files"]), "restoredOperationalIntegrity": all(report["ok"] for report in operational) if operational else None}
