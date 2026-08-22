from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .adapters import diligence_summary, test1_enrichment, test2_export
from .auth import hash_password
from .classification import classify
from .db import Database, now
from .extraction import normalize_value, process
from .field_registry import FIELD_BY_NAME
from .reconciliation import as_dicts, reconcile
from .security import sha256_bytes, validate_upload
from .semantic import derive_entities
from .test1_snapshot import Test1SnapshotError, load_snapshot
from .assumptions.observations import parse_market_panel, rows_to_observations, canonical_hash
from .assumptions.artifacts import load_artifact
from .assumptions.test1_economic import load_test1_economic
from .assumptions.recommend import recommend
from .assumptions.catalog import BY_NAME, public_catalog
from .creos_handoff import build_assumption_run_handoff
from .assumptions.profiling import profile_observations
from .assumptions.analysis import benchmark_matrix, correlation_matrix, lead_lag_matrix, stress_scenarios, time_series_diagnostics
from .assumptions.public_sources import public_series_catalog
from .assumptions.factors import derived_change_factors, market_factor_scorecards
from .assumptions.governance import cadence_findings, research_manifest, revision_conflicts, source_scorecards
from .assumptions.validation import market_regimes, walk_forward_baselines
from .research.comparables import analyze_location, parse_csv_records
from .opportunity import (CANDIDATE_EVIDENCE_SCHEMA_VERSION, CANDIDATE_STATUSES, ORIGIN_TYPES,
                          PROPERTY_TYPES, OpportunityScreeningTier, analyze_property_opportunity, canonical_json,
                          normalize_evidence_payload, normalized_address_hash, parse_location_evidence,
                          parse_sale_comps, registered_screening_policy, screen_opportunity, screening_input_from_snapshot,
                          sha256_json)

OPPORTUNITY_ACKNOWLEDGEMENTS = (
    "evidence_reviewed", "source_rights_reviewed", "limitations_acknowledged", "test2_advisory_only",
)
SCREENING_PRIORITY_RANK = {"HIGH_PRIORITY_REVIEW": 1, "WORTH_REVIEWING": 2, "LOW_PRIORITY": 3,
                           "INSUFFICIENT_EVIDENCE": 4, None: 5}
SCREENING_CURRENCY_STATUSES = frozenset({"CURRENT", "OUTDATED_EVIDENCE", "NOT_SCREENED"})
SCREENING_PRIORITY_SQL = """CASE WHEN r.screening_tier='HIGH_PRIORITY_REVIEW' THEN 1
    WHEN r.screening_tier='WORTH_REVIEWING' THEN 2 WHEN r.screening_tier='LOW_PRIORITY' THEN 3
    WHEN r.screening_tier='INSUFFICIENT_EVIDENCE' THEN 4 ELSE 5 END"""
SCREENING_CURRENCY_SQL = """CASE WHEN r.id IS NULL THEN 'NOT_SCREENED'
    WHEN sv.version=lv.version THEN 'CURRENT' ELSE 'OUTDATED_EVIDENCE' END"""


class ConflictError(ValueError):
    """A requested immutable resource already exists or lifecycle state conflicts."""


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
        self.market_data_dir = self.data_dir / "market-data"
        self.market_data_dir.mkdir(parents=True, exist_ok=True)
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
            "assumptionCatalog": public_catalog(),
            "publicSeriesCatalog": public_series_catalog(),
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
            entities = [dict(row) for row in connection.execute("SELECT * FROM semantic_entities WHERE deal_id=? AND organization_id=? ORDER BY document_id,source_row", (deal_id, organization_id))]
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
        status_by_value = {item["id"]: item["review_status"] for item in values}
        for entity in entities:
            entity["data"] = json.loads(entity.pop("data_json"))
            source_ids = json.loads(entity.pop("source_value_ids_json"))
            entity["source_value_ids"] = source_ids
            statuses = [status_by_value.get(source_id, "missing") for source_id in source_ids]
            entity["review_status"] = "approved" if statuses and all(status == "approved" for status in statuses) else ("rejected" if any(status == "rejected" for status in statuses) else "needs_review")
        with self.db.connect() as connection:
            runs = [dict(row) for row in connection.execute("SELECT * FROM assumption_runs WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC", (deal_id, organization_id))]
            opportunity_runs = [dict(row) for row in connection.execute("SELECT * FROM opportunity_runs WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC", (deal_id, organization_id))]
            opportunity_decisions = [dict(row) for row in connection.execute("SELECT * FROM opportunity_decisions WHERE deal_id=? AND organization_id=? ORDER BY rowid", (deal_id, organization_id))]
            opportunity_handoffs = [dict(row) for row in connection.execute("SELECT * FROM opportunity_handoffs WHERE deal_id=? AND organization_id=? ORDER BY version DESC", (deal_id, organization_id))]
            snapshots = [dict(row) for row in connection.execute("SELECT * FROM data_source_snapshots WHERE (deal_id=? OR deal_id IS NULL) AND organization_id=? ORDER BY created_at DESC", (deal_id, organization_id))]
            observations = [dict(row) for row in connection.execute("SELECT o.* FROM market_observations o JOIN data_source_snapshots s ON s.id=o.snapshot_id WHERE o.organization_id=? AND (s.deal_id=? OR s.deal_id IS NULL) ORDER BY o.observation_date", (organization_id, deal_id))]
            decision_contexts = [dict(row) for row in connection.execute("SELECT * FROM assumption_decision_context WHERE deal_id=? AND organization_id=? ORDER BY created_at DESC", (deal_id, organization_id))]
        for run in runs:
            for key in ("evidence_snapshot_ids_json", "input_features_json", "confidence_components_json", "limitations_json"):
                run[key.removesuffix("_json")] = json.loads(run.pop(key))
        for run in opportunity_runs:
            run["content"] = json.loads(run.pop("content_json"))
        for decision in opportunity_decisions:
            decision["acknowledgements"] = json.loads(decision.pop("acknowledgements_json"))
            decision["modifications"] = json.loads(decision.pop("modifications_json"))
        for handoff in opportunity_handoffs:
            handoff["content"] = json.loads(handoff.pop("content_json"))
        decisions_by_run = {}
        for decision in opportunity_decisions:
            decisions_by_run.setdefault(decision["opportunity_run_id"], []).append(decision)
        for run in opportunity_runs:
            history = decisions_by_run.get(run["id"], [])
            run["decisions"] = history
            run["review_state"] = history[-1]["decision"] if history else "awaiting_review"
        return {"deal": dict(deal), "documents": documents, "values": values, "entities": entities, "findings": findings, "audit": audit, "review_decisions": decisions, "assumption_runs": runs, "opportunity_runs": opportunity_runs, "opportunity_decisions": opportunity_decisions, "opportunity_handoffs": opportunity_handoffs, "data_source_snapshots": snapshots, "market_observations": observations, "data_profile": profile_observations(observations), "benchmark_matrix": benchmark_matrix(observations), "correlation_matrix": correlation_matrix(observations), "time_series_diagnostics": time_series_diagnostics(observations), "stress_scenarios": stress_scenarios(observations), "lead_lag_matrix": lead_lag_matrix(observations), "derived_change_factors": derived_change_factors(observations), "market_factor_scorecards": market_factor_scorecards(observations), "revision_conflicts": revision_conflicts(observations), "cadence_findings": cadence_findings(observations), "source_scorecards": source_scorecards(observations, snapshots), "research_manifest": research_manifest(observations, snapshots), "walk_forward_baselines": walk_forward_baselines(observations), "market_regimes": market_regimes(observations), "assumption_decision_contexts": decision_contexts}

    def location_analysis(self, organization_id: str, user_id: str, deal_id: str, payload: dict) -> dict:
        with self.db.connect() as connection:
            deal = connection.execute("SELECT * FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone()
        if not deal:
            raise LookupError("Deal not found")
        subject = dict(payload.get("subject") or {})
        subject.setdefault("address", deal["address"])
        subject.setdefault("property_type", deal["property_type"])
        comps_text, pois_text = str(payload.get("comps_csv") or ""), str(payload.get("pois_csv") or "")
        if not comps_text or not pois_text:
            raise ValueError("Both comparable-rent and point-of-interest CSV files are required")
        comps, pois = parse_csv_records(comps_text, "comps"), parse_csv_records(pois_text, "pois")
        result = analyze_location(subject, comps, pois, max_comp_distance_miles=float(payload.get("max_comp_distance_miles", 15)), limit=int(payload.get("limit", 10)))
        result["provenance"] = {
            "compsFileSha256": hashlib.sha256(comps_text.encode()).hexdigest(), "compsRows": len(comps),
            "poisFileSha256": hashlib.sha256(pois_text.encode()).hexdigest(), "poisRows": len(pois),
            "analysisVersion": "location-comparables/1.0", "generatedAt": now(),
        }
        self.db.audit(organization_id, user_id, "research.location_analysis", "deal", deal_id,
                      {"comps_file_sha256": result["provenance"]["compsFileSha256"], "pois_file_sha256": result["provenance"]["poisFileSha256"],
                       "comp_count": len(result["rentComparables"]), "poi_count": len(pois), "analysis_version": "location-comparables/1.0"}, deal_id)
        return result

    @staticmethod
    def _bounded_text(payload: dict, field: str, maximum: int, *, required: bool = False) -> str | None:
        value = str(payload.get(field) or "").strip()
        if required and not value:
            raise ValueError(f"{field} is required")
        if len(value) > maximum:
            raise ValueError(f"{field} exceeds {maximum} characters")
        return value or None

    def create_opportunity_candidate(self, organization_id: str, user_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Opportunity candidate must be a JSON object")
        allowed = {"deal_id", "property_type", "display_name", "address", "market", "submarket", "status", "origin_type"}
        if set(payload) - allowed:
            raise ValueError("Unsupported opportunity candidate fields: " + ", ".join(sorted(set(payload) - allowed)))
        property_type = str(payload.get("property_type") or "").strip().lower()
        if property_type not in PROPERTY_TYPES:
            raise ValueError("property_type is not a governed property type")
        status = str(payload.get("status") or "candidate").strip()
        origin_type = str(payload.get("origin_type") or "manual").strip()
        if status not in CANDIDATE_STATUSES or origin_type not in ORIGIN_TYPES:
            raise ValueError("Invalid opportunity status or origin_type")
        if status != "candidate":
            raise ValueError("New opportunities must begin with candidate status")
        display_name = self._bounded_text(payload, "display_name", 300)
        address = self._bounded_text(payload, "address", 500)
        market = self._bounded_text(payload, "market", 200)
        submarket = self._bounded_text(payload, "submarket", 200)
        if not display_name and not address:
            raise ValueError("display_name or address is required")
        deal_id = self._bounded_text(payload, "deal_id", 100)
        if origin_type == "existing_deal" and not deal_id:
            raise ValueError("existing_deal origin requires deal_id")
        address_hash = normalized_address_hash(address)
        candidate_id, created = str(uuid.uuid4()), now()
        warnings = []
        with self.db.connect() as connection:
            if deal_id and not connection.execute("SELECT 1 FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone():
                raise LookupError("Deal not found")
            if address_hash:
                exact_duplicate = connection.execute("SELECT 1 FROM opportunity_candidates WHERE organization_id=? AND normalized_address_sha256=?", (organization_id, address_hash)).fetchone()
                legacy_duplicate = False
                if not exact_duplicate:
                    legacy_duplicate = any(normalized_address_hash(row[0]) == address_hash for row in connection.execute(
                        "SELECT address FROM opportunity_candidates WHERE organization_id=? AND address IS NOT NULL", (organization_id,)))
                if exact_duplicate or legacy_duplicate:
                    warnings.append("POSSIBLE_DUPLICATE_CANDIDATE")
            connection.execute(
                "INSERT INTO opportunity_candidates(id,organization_id,deal_id,created_by,property_type,display_name,address,normalized_address_sha256,market,submarket,status,origin_type,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (candidate_id, organization_id, deal_id, user_id, property_type, display_name, address,
                 address_hash, market, submarket, status, origin_type, created),
            )
        self.db.audit(organization_id, user_id, "opportunity.candidate_created", "opportunity_candidate",
                      candidate_id, {"property_type": property_type, "origin_type": origin_type,
                                     "status": status, "warnings": warnings}, deal_id)
        return {"id": candidate_id, "organization_id": organization_id, "deal_id": deal_id,
                "property_type": property_type, "display_name": display_name, "address": address,
                "market": market, "submarket": submarket, "status": status,
                "origin_type": origin_type, "created_by": user_id, "created_at": created,
                "warnings": warnings, "deal_created": False}

    @staticmethod
    def _screening_summary(row) -> dict | None:
        if not row or not row["run_id"]:
            return None
        result = json.loads(row["result_json"])
        metrics = result.get("derivedMetrics") or {}
        freshness = result.get("evidenceFreshnessDetail") or {}
        validated = result.get("validatedOpportunityScore") or {}
        tier = row["screening_tier"]
        return {"id": row["run_id"], "candidate_version_id": row["candidate_version_id"],
                "candidate_version": row["latest_screened_version"], "screening_tier": tier,
                "screening_priority_rank": SCREENING_PRIORITY_RANK[tier],
                "analysis_as_of": row["screened_analysis_as_of"], "evaluated_at": row["evaluated_at"],
                "evidence_completeness": result.get("evidenceCompleteness"),
                "evidence_freshness_days": result.get("evidenceFreshnessDays"),
                "oldest_evidence_age_days": freshness.get("oldestEvidenceAgeDays"),
                "signal_evidence_max_age_days": freshness.get("signalEvidenceMaxAgeDays"),
                "rent_gap_pct": metrics.get("rentGapPct"),
                "basis_discount_pct": metrics.get("basisDiscountPct"),
                "evidence_supported_noi_delta": metrics.get("noiUpside"),
                "noi_upside_ratio": metrics.get("noiUpsideRatio"),
                "cap_rate_spread_bps": metrics.get("capRateSpreadBps"),
                "vacancy_delta": metrics.get("vacancyDelta"),
                "warning_count": len(result.get("warnings") or []),
                "reason_count": len(result.get("reasons") or []),
                "validated_score_status": validated.get("status", "NO_VALIDATED_OPPORTUNITY_SCORE"),
                "result_sha256": row["result_sha256"]}

    @staticmethod
    def _decimal_query(query: dict, field: str) -> str | None:
        if field not in query or query[field] in (None, ""):
            return None
        try:
            value = Decimal(str(query[field]))
        except InvalidOperation as exc:
            raise ValueError(f"{field} must be a finite decimal") from exc
        if not value.is_finite() or value < 0:
            raise ValueError(f"{field} must be a finite non-negative decimal")
        return format(value, "f")

    def list_opportunity_candidates(self, organization_id: str, query: dict) -> dict:
        if not isinstance(query, dict):
            raise ValueError("Opportunity query must be an object")
        allowed = {"property_type", "status", "market", "screening_tier", "screening_currency_status",
                   "evidence_completeness_min", "evidence_completeness_max", "rent_gap_min",
                   "basis_discount_min", "freshness_max_days", "q", "sort", "direction", "limit", "offset"}
        if set(query) - allowed:
            raise ValueError("Unsupported opportunity query fields")
        try:
            limit, offset = int(query.get("limit", 50)), int(query.get("offset", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("limit and offset must be integers") from exc
        if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000:
            raise ValueError("limit must be 1-200 and offset must be 0-1,000,000")
        sort = str(query.get("sort") or "created_at")
        direction = str(query.get("direction") or ("asc" if sort == "screening_tier" else "desc")).lower()
        sorts = {"created_at": "c.created_at", "analysis_as_of": "lv.analysis_as_of",
                 "screening_tier": SCREENING_PRIORITY_SQL,
                 "evidence_completeness": "CAST(json_extract(r.result_json,'$.evidenceCompleteness') AS REAL)",
                 "evidence_freshness": "CAST(json_extract(r.result_json,'$.evidenceFreshnessDays') AS INTEGER)",
                 "rent_gap": "CAST(json_extract(r.result_json,'$.derivedMetrics.rentGapPct') AS REAL)",
                 "basis_discount": "CAST(json_extract(r.result_json,'$.derivedMetrics.basisDiscountPct') AS REAL)"}
        if sort not in sorts or direction not in {"asc", "desc"}:
            raise ValueError("Unsupported opportunity sort or direction")
        if query.get("property_type") and query["property_type"] not in PROPERTY_TYPES:
            raise ValueError("Unsupported property_type filter")
        if query.get("status") and query["status"] not in CANDIDATE_STATUSES:
            raise ValueError("Unsupported status filter")
        if query.get("screening_tier") and query["screening_tier"] not in {item.value for item in OpportunityScreeningTier}:
            raise ValueError("Unsupported screening_tier filter")
        if query.get("screening_currency_status") and query["screening_currency_status"] not in SCREENING_CURRENCY_STATUSES:
            raise ValueError("Unsupported screening_currency_status filter")
        if query.get("market") and len(str(query["market"])) > 200:
            raise ValueError("market filter exceeds 200 characters")
        search = str(query.get("q") or "").strip()
        if len(search) > 200:
            raise ValueError("q exceeds 200 characters")
        completeness_min = self._decimal_query(query, "evidence_completeness_min")
        completeness_max = self._decimal_query(query, "evidence_completeness_max")
        rent_gap_min = self._decimal_query(query, "rent_gap_min")
        basis_discount_min = self._decimal_query(query, "basis_discount_min")
        if completeness_min is not None and Decimal(completeness_min) > 1:
            raise ValueError("evidence_completeness_min cannot exceed 1")
        if completeness_max is not None and Decimal(completeness_max) > 1:
            raise ValueError("evidence_completeness_max cannot exceed 1")
        if completeness_min is not None and completeness_max is not None and Decimal(completeness_min) > Decimal(completeness_max):
            raise ValueError("evidence completeness minimum cannot exceed maximum")
        freshness_max = None
        if query.get("freshness_max_days") not in (None, ""):
            try:
                freshness_max = int(query["freshness_max_days"])
            except (TypeError, ValueError) as exc:
                raise ValueError("freshness_max_days must be a non-negative integer") from exc
            if freshness_max < 0 or freshness_max > 100_000:
                raise ValueError("freshness_max_days must be between 0 and 100,000")
        where, parameters = ["c.organization_id=?"], [organization_id]
        for field in ("property_type", "status", "market"):
            if query.get(field):
                where.append(f"c.{field}=?")
                parameters.append(str(query[field]))
        if query.get("screening_tier"):
            where.append("r.screening_tier=?")
            parameters.append(str(query["screening_tier"]))
        if query.get("screening_currency_status"):
            where.append(SCREENING_CURRENCY_SQL + "=?")
            parameters.append(str(query["screening_currency_status"]))
        if completeness_min is not None:
            where.append("decimal_gte(json_extract(r.result_json,'$.evidenceCompleteness'),?)=1")
            parameters.append(completeness_min)
        if completeness_max is not None:
            where.append("decimal_lte(json_extract(r.result_json,'$.evidenceCompleteness'),?)=1")
            parameters.append(completeness_max)
        if rent_gap_min is not None:
            where.append("decimal_gte(json_extract(r.result_json,'$.derivedMetrics.rentGapPct'),?)=1")
            parameters.append(rent_gap_min)
        if basis_discount_min is not None:
            where.append("decimal_gte(json_extract(r.result_json,'$.derivedMetrics.basisDiscountPct'),?)=1")
            parameters.append(basis_discount_min)
        if freshness_max is not None:
            where.append("CAST(json_extract(r.result_json,'$.evidenceFreshnessDays') AS INTEGER)<=?")
            parameters.append(freshness_max)
        if search:
            escaped = search.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where.append("(lower(COALESCE(c.display_name,'')) LIKE ? ESCAPE '\\' OR lower(COALESCE(c.address,'')) LIKE ? ESCAPE '\\' OR lower(COALESCE(c.market,'')) LIKE ? ESCAPE '\\' OR lower(COALESCE(c.submarket,'')) LIKE ? ESCAPE '\\')")
            parameters.extend([f"%{escaped}%"] * 4)
        joins = """ FROM opportunity_candidates c
            LEFT JOIN opportunity_candidate_versions lv ON lv.id=(SELECT lv2.id FROM opportunity_candidate_versions lv2 WHERE lv2.organization_id=c.organization_id AND lv2.candidate_id=c.id ORDER BY lv2.version DESC LIMIT 1)
            LEFT JOIN opportunity_screening_runs r ON r.id=(SELECT r2.id FROM opportunity_screening_runs r2 JOIN opportunity_candidate_versions sv2 ON sv2.id=r2.candidate_version_id WHERE r2.organization_id=c.organization_id AND r2.candidate_id=c.id ORDER BY sv2.version DESC,r2.evaluated_at DESC,r2.rowid DESC LIMIT 1)
            LEFT JOIN opportunity_candidate_versions sv ON sv.id=r.candidate_version_id """
        clause = " WHERE " + " AND ".join(where)
        fields = f"""SELECT c.*,r.id run_id,r.candidate_version_id,r.screening_tier,r.result_json,r.result_sha256,r.evaluated_at,
            lv.version latest_evidence_version,lv.analysis_as_of latest_evidence_analysis_as_of,
            json_extract(lv.content_json,'$.inputs.acquisition_basis') latest_acquisition_basis,
            json_extract(lv.content_json,'$.inputs.basis_unit') latest_basis_unit,
            sv.version latest_screened_version,sv.analysis_as_of screened_analysis_as_of,
            {SCREENING_CURRENCY_SQL} screening_currency_status"""
        with self.db.connect() as connection:
            total = connection.execute("SELECT COUNT(*)" + joins + clause, parameters).fetchone()[0]
            summary_row = connection.execute(f"""SELECT
                COUNT(*) total_candidates,
                SUM(CASE WHEN r.screening_tier='HIGH_PRIORITY_REVIEW' THEN 1 ELSE 0 END) high_priority_review,
                SUM(CASE WHEN r.screening_tier='WORTH_REVIEWING' THEN 1 ELSE 0 END) worth_reviewing,
                SUM(CASE WHEN r.id IS NULL OR r.screening_tier='INSUFFICIENT_EVIDENCE' THEN 1 ELSE 0 END) needs_evidence,
                SUM(CASE WHEN {SCREENING_CURRENCY_SQL}='OUTDATED_EVIDENCE' THEN 1 ELSE 0 END) stale_screening
                """ + joins + clause, parameters).fetchone()
            sort_expression = sorts[sort]
            rows = connection.execute(fields + joins + clause + f" ORDER BY CASE WHEN {sort_expression} IS NULL THEN 1 ELSE 0 END ASC,{sort_expression} {direction.upper()},c.id ASC LIMIT ? OFFSET ?",
                                      (*parameters, limit, offset)).fetchall()
        items = []
        for row in rows:
            candidate = {key: row[key] for key in ("id", "deal_id", "created_by", "property_type", "display_name",
                                                   "address", "market", "submarket", "status", "origin_type", "created_at")}
            screening = self._screening_summary(row)
            candidate.update({"latest_evidence_version": row["latest_evidence_version"],
                              "latest_evidence_analysis_as_of": row["latest_evidence_analysis_as_of"],
                              "acquisition_basis": row["latest_acquisition_basis"],
                              "basis_unit": row["latest_basis_unit"],
                              "latest_screened_version": row["latest_screened_version"],
                              "screening_currency_status": row["screening_currency_status"],
                              "screening_tier": screening["screening_tier"] if screening else None,
                              "screening_priority_rank": screening["screening_priority_rank"] if screening else 5,
                              "latest_screening": screening,
                              "current_screening": screening})
            if screening:
                candidate.update({key: screening[key] for key in (
                    "evidence_completeness", "evidence_freshness_days", "oldest_evidence_age_days",
                    "signal_evidence_max_age_days", "rent_gap_pct", "basis_discount_pct",
                    "evidence_supported_noi_delta", "noi_upside_ratio", "cap_rate_spread_bps",
                    "vacancy_delta", "warning_count", "reason_count", "validated_score_status")})
            else:
                candidate.update({key: None for key in (
                    "evidence_completeness", "evidence_freshness_days", "oldest_evidence_age_days",
                    "signal_evidence_max_age_days", "rent_gap_pct", "basis_discount_pct",
                    "evidence_supported_noi_delta", "noi_upside_ratio", "cap_rate_spread_bps", "vacancy_delta")})
                candidate.update({"warning_count": 0, "reason_count": 0,
                                  "validated_score_status": "NO_VALIDATED_OPPORTUNITY_SCORE"})
            items.append(candidate)
        summary = {key: int(summary_row[key] or 0) for key in (
            "total_candidates", "high_priority_review", "worth_reviewing", "needs_evidence", "stale_screening")}
        return {"items": items, "pagination": {"limit": limit, "offset": offset, "returned": len(items), "total": total},
                "summary": summary,
                "sort": {"field": sort, "direction": direction}}

    def opportunity_candidate_query_plan(self, organization_id: str) -> list[dict]:
        """Return SQLite's plan for the representative bounded Finder list query."""
        sql = f"""EXPLAIN QUERY PLAN SELECT c.id,lv.version,sv.version
            FROM opportunity_candidates c
            LEFT JOIN opportunity_candidate_versions lv ON lv.id=(SELECT lv2.id FROM opportunity_candidate_versions lv2 WHERE lv2.organization_id=c.organization_id AND lv2.candidate_id=c.id ORDER BY lv2.version DESC LIMIT 1)
            LEFT JOIN opportunity_screening_runs r ON r.id=(SELECT r2.id FROM opportunity_screening_runs r2 JOIN opportunity_candidate_versions sv2 ON sv2.id=r2.candidate_version_id WHERE r2.organization_id=c.organization_id AND r2.candidate_id=c.id ORDER BY sv2.version DESC,r2.evaluated_at DESC,r2.rowid DESC LIMIT 1)
            LEFT JOIN opportunity_candidate_versions sv ON sv.id=r.candidate_version_id
            WHERE c.organization_id=? AND c.status='candidate'
            ORDER BY {SCREENING_PRIORITY_SQL} ASC,c.id ASC LIMIT 25"""
        with self.db.connect() as connection:
            rows = connection.execute(sql, (organization_id,)).fetchall()
        return [{"id": row[0], "parent": row[1], "detail": row[3]} for row in rows]

    def opportunity_candidate(self, organization_id: str, candidate_id: str) -> dict:
        with self.db.connect() as connection:
            candidate = connection.execute("SELECT * FROM opportunity_candidates WHERE id=? AND organization_id=?", (candidate_id, organization_id)).fetchone()
            if not candidate:
                raise LookupError("Opportunity candidate not found")
            versions = connection.execute("SELECT * FROM opportunity_candidate_versions WHERE candidate_id=? AND organization_id=? ORDER BY version", (candidate_id, organization_id)).fetchall()
            runs = connection.execute("SELECT r.*,r.id run_id,v.version latest_screened_version,v.analysis_as_of screened_analysis_as_of FROM opportunity_screening_runs r JOIN opportunity_candidate_versions v ON v.id=r.candidate_version_id WHERE r.candidate_id=? AND r.organization_id=? ORDER BY v.version,r.evaluated_at,r.rowid", (candidate_id, organization_id)).fetchall()
            archive_event = connection.execute("SELECT created_at FROM audit_events WHERE organization_id=? AND entity_type='opportunity_candidate' AND entity_id=? AND action='opportunity.candidate_archived' ORDER BY rowid DESC LIMIT 1", (organization_id, candidate_id)).fetchone()
        candidate_value = {key: candidate[key] for key in candidate.keys() if key != "normalized_address_sha256"}
        candidate_value["archived_at"] = archive_event["created_at"] if archive_event else None
        version_values = [{**{key: row[key] for key in row.keys() if key != "content_json"}, "content": json.loads(row["content_json"])} for row in versions]
        run_values = [{**{key: row[key] for key in row.keys() if key not in {"result_json", "run_id", "latest_screened_version", "screened_analysis_as_of"}}, "result": json.loads(row["result_json"])} for row in runs]
        latest_version = version_values[-1] if version_values else None
        latest_run_row = runs[-1] if runs else None
        latest_run = run_values[-1] if run_values else None
        if latest_run_row is None:
            currency = "NOT_SCREENED"
        elif latest_version and latest_run_row["latest_screened_version"] == latest_version["version"]:
            currency = "CURRENT"
        else:
            currency = "OUTDATED_EVIDENCE"
        projection = self._screening_summary(latest_run_row) if latest_run_row else None
        return {"candidate": candidate_value, "versions": version_values, "screening_runs": run_values,
                "latest_screening": latest_run,
                "current_screening": latest_run, "screening_projection": projection,
                "latest_evidence_version": latest_version["version"] if latest_version else None,
                "latest_evidence_analysis_as_of": latest_version["analysis_as_of"] if latest_version else None,
                "latest_screened_version": latest_run_row["latest_screened_version"] if latest_run_row else None,
                "screening_currency_status": currency}

    def archive_opportunity_candidate(self, organization_id: str, user_id: str, candidate_id: str) -> dict:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            candidate = connection.execute("SELECT * FROM opportunity_candidates WHERE id=? AND organization_id=?", (candidate_id, organization_id)).fetchone()
            if not candidate:
                raise LookupError("Opportunity candidate not found")
            if candidate["status"] == "archived":
                raise ValueError("Opportunity candidate is already archived")
            if candidate["status"] != "candidate":
                raise ValueError(f"Cannot transition opportunity candidate from {candidate['status']} to archived")
            connection.execute("UPDATE opportunity_candidates SET status='archived' WHERE id=? AND organization_id=?", (candidate_id, organization_id))
        event_id = self.db.audit(organization_id, user_id, "opportunity.candidate_archived", "opportunity_candidate",
                                 candidate_id, {"previous_status": candidate["status"], "status": "archived",
                                                "evidence_retained": True, "screening_history_retained": True}, candidate["deal_id"])
        with self.db.connect() as connection:
            archived_at = connection.execute("SELECT created_at FROM audit_events WHERE id=?", (event_id,)).fetchone()[0]
        return {"id": candidate_id, "status": "archived", "archived_at": archived_at,
                "evidence_retained": True, "screening_history_retained": True}

    def create_opportunity_candidate_version(self, organization_id: str, user_id: str,
                                             candidate_id: str, payload: dict) -> dict:
        version_id, created = str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            candidate = connection.execute("SELECT * FROM opportunity_candidates WHERE id=? AND organization_id=?", (candidate_id, organization_id)).fetchone()
            if not candidate:
                raise LookupError("Opportunity candidate not found")
            if candidate["status"] != "candidate":
                raise ValueError("Evidence versions can be added only to active candidates")
            snapshot = normalize_evidence_payload(candidate_id, candidate["property_type"], payload)
            content_json, content_hash = canonical_json(snapshot), sha256_json(snapshot)
            if connection.execute("SELECT 1 FROM opportunity_candidate_versions WHERE organization_id=? AND candidate_id=? AND content_sha256=?", (organization_id, candidate_id, content_hash)).fetchone():
                raise ConflictError("This exact candidate evidence version already exists")
            version = connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM opportunity_candidate_versions WHERE organization_id=? AND candidate_id=?", (organization_id, candidate_id)).fetchone()[0]
            connection.execute("INSERT INTO opportunity_candidate_versions VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (version_id, organization_id, candidate_id, version,
                                CANDIDATE_EVIDENCE_SCHEMA_VERSION, snapshot["inputs"]["analysis_as_of"],
                                content_json, content_hash, user_id, created))
        self.db.audit(organization_id, user_id, "opportunity.candidate_version_created", "opportunity_candidate_version",
                      version_id, {"candidate_id": candidate_id, "version": version, "content_sha256": content_hash})
        return {"id": version_id, "candidate_id": candidate_id, "version": version,
                "schema_version": CANDIDATE_EVIDENCE_SCHEMA_VERSION, "analysis_as_of": snapshot["inputs"]["analysis_as_of"],
                "content": snapshot, "content_sha256": content_hash, "created_by": user_id, "created_at": created}

    def screen_opportunity_candidate(self, organization_id: str, user_id: str, candidate_id: str,
                                     payload: dict) -> dict:
        if not isinstance(payload, dict) or payload:
            raise ValueError("Screening accepts no client-computed inputs; create an evidence version first")
        with self.db.connect() as connection:
            candidate = connection.execute("SELECT status FROM opportunity_candidates WHERE id=? AND organization_id=?", (candidate_id, organization_id)).fetchone()
            if not candidate:
                raise LookupError("Opportunity candidate not found")
            if candidate["status"] != "candidate":
                raise ValueError("Screening can run only for active candidates")
            version = connection.execute("SELECT * FROM opportunity_candidate_versions WHERE candidate_id=? AND organization_id=? ORDER BY version DESC LIMIT 1", (candidate_id, organization_id)).fetchone()
        if not version:
            raise ValueError("A candidate evidence version is required before screening")
        snapshot = json.loads(version["content_json"])
        if sha256_json(snapshot) != version["content_sha256"]:
            raise ValueError("Candidate evidence integrity validation failed")
        result = screen_opportunity(screening_input_from_snapshot(snapshot))
        result_value = result.to_dict()
        result_json, result_hash = canonical_json(result_value), sha256_json(result_value)
        run_id, created = str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            connection.execute("INSERT INTO opportunity_screening_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (run_id, organization_id, candidate_id, version["id"], result.policy_id,
                                result.policy_version, result.policy_hash, result.input_snapshot_hash,
                                result.evidence_hash, result.screening_tier.value, result_json, result_hash,
                                user_id, result.evaluated_at.astimezone(timezone.utc).isoformat(), created))
        self.db.audit(organization_id, user_id, "opportunity.screened", "opportunity_screening_run", run_id,
                      {"candidate_id": candidate_id, "candidate_version_id": version["id"],
                       "screening_tier": result.screening_tier.value, "result_sha256": result_hash})
        return {"id": run_id, "candidate_id": candidate_id, "candidate_version_id": version["id"],
                "result": result_value, "result_sha256": result_hash, "created_by": user_id, "created_at": created}

    def opportunity_candidate_history(self, organization_id: str, candidate_id: str) -> dict:
        detail = self.opportunity_candidate(organization_id, candidate_id)
        with self.db.connect() as connection:
            lifecycle = connection.execute("SELECT id,actor_id,action,details_json,created_at FROM audit_events WHERE organization_id=? AND entity_type='opportunity_candidate' AND entity_id=? AND action='opportunity.candidate_archived' ORDER BY rowid", (organization_id, candidate_id)).fetchall()
        timeline = ([{"type": "candidate_created", "at": detail["candidate"]["created_at"],
                      "id": candidate_id, "actor_id": detail["candidate"]["created_by"]}]
                    + [{"type": "evidence_version_created", "at": item["created_at"], "id": item["id"],
                        "actor_id": item["created_by"], "version": item["version"], "content_sha256": item["content_sha256"]}
                       for item in detail["versions"]]
                    + [{"type": "screening_run_created", "at": item["created_at"], "id": item["id"],
                        "actor_id": item["created_by"], "candidate_version_id": item["candidate_version_id"],
                        "screening_tier": item["screening_tier"], "result_sha256": item["result_sha256"]}
                       for item in detail["screening_runs"]]
                    + [{"type": "candidate_archived", "at": item["created_at"], "id": item["id"],
                        "actor_id": item["actor_id"], "details": json.loads(item["details_json"])}
                       for item in lifecycle])
        return {"candidate_id": candidate_id, "timeline": sorted(timeline, key=lambda item: (item["at"], item["type"], item["id"]))}

    def property_opportunity_analysis(self, organization_id: str, user_id: str, deal_id: str,
                                      payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Property opportunity request must be a JSON object")
        with self.db.connect() as connection:
            deal = connection.execute("SELECT * FROM deals WHERE id=? AND organization_id=?",
                                      (deal_id, organization_id)).fetchone()
            approved_fips = connection.execute("SELECT rd.proposed_normalized_value FROM manual_assumptions ma JOIN review_decisions rd ON rd.entity_id=ma.id AND rd.entity_type='manual_assumption' WHERE ma.organization_id=? AND ma.deal_id=? AND ma.field_name='county_fips' AND ma.review_status='approved' ORDER BY rd.rowid DESC LIMIT 1", (organization_id, deal_id)).fetchone()
            if not approved_fips:
                approved_fips = connection.execute("SELECT rd.proposed_normalized_value FROM extracted_values ev JOIN review_decisions rd ON rd.entity_id=ev.id AND rd.entity_type='extracted_value' WHERE ev.organization_id=? AND ev.deal_id=? AND ev.field_name='county_fips' AND ev.review_status='approved' ORDER BY rd.rowid DESC LIMIT 1", (organization_id, deal_id)).fetchone()
        if not deal:
            raise LookupError("Deal not found")
        rent_text, sale_text = str(payload.get("rent_comps_csv") or ""), str(payload.get("sale_comps_csv") or "")
        if not rent_text or not sale_text:
            raise ValueError("Both rent-comparable and sale-comparable CSV files are required")
        subject = dict(payload.get("subject") or {})
        subject.setdefault("address", deal["address"])
        subject.setdefault("property_type", deal["property_type"])
        subject.pop("county_fips_analyst_approved", None)
        subject.pop("county_fips", None)
        if approved_fips:
            subject["county_fips"] = approved_fips[0]
        pois_text = str(payload.get("location_evidence_csv") or "")
        location_rows = parse_location_evidence(pois_text) if pois_text else None
        raw_source_metadata = payload.get("source_metadata") or {}
        if not isinstance(raw_source_metadata, dict):
            raise ValueError("source_metadata must be an object")
        source_metadata = {key: dict(value) if isinstance(value, dict) else value
                           for key, value in raw_source_metadata.items()}
        if pois_text:
            source_metadata.setdefault("location_evidence", {})["file_sha256"] = hashlib.sha256(pois_text.encode()).hexdigest()
        if self.test1_data_dir and approved_fips:
            try:
                test1_context = test1_enrichment(
                    {"address": subject.get("address"), "county_fips": approved_fips[0]},
                    load_snapshot(self.test1_data_dir),
                )
            except Test1SnapshotError as error:
                test1_context = {"status": "invalid_snapshot", "verified": False, "coverage": "missing",
                                 "networkRequests": 0, "results": {}, "message": str(error)}
        elif self.test1_data_dir:
            test1_context = {"status": "input_approval_required", "verified": False, "coverage": "missing",
                             "networkRequests": 0, "results": {},
                             "message": "A reviewer-approved county FIPS is required; Test3 does not infer geography."}
        else:
            test1_context = {"status": "not_configured", "verified": False, "coverage": "missing",
                             "networkRequests": 0, "results": {}}
        result = analyze_property_opportunity(
            subject, parse_csv_records(rent_text, "comps"), parse_sale_comps(sale_text),
            analysis_as_of=str(payload.get("analysis_as_of") or ""),
            source_metadata=source_metadata,
            location_evidence=location_rows,
            test1_context=test1_context,
            economic_inputs=payload.get("economic_inputs") if "economic_inputs" in payload else None,
            location_thresholds=dict(payload.get("location_thresholds") or {}) or None,
            location_maximum_age_days=int(payload.get("location_maximum_age_days", 3650)),
            max_distance_miles=float(payload.get("max_distance_miles", 15)),
            rent_maximum_age_days=int(payload.get("rent_maximum_age_days", 365)),
            sale_maximum_age_days=int(payload.get("sale_maximum_age_days", 730)),
            limit=int(payload.get("limit", 10)),
        )
        run_id, created = str(uuid.uuid4()), now()
        content_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
        with self.db.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM opportunity_runs WHERE organization_id=? AND deal_id=? AND content_sha256=?",
                (organization_id, deal_id, result["artifactHash"]),
            ).fetchone():
                raise ValueError("This exact property opportunity analysis already exists for the deal")
            connection.execute(
                "INSERT INTO opportunity_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, organization_id, deal_id, result["schemaVersion"], result["policyVersion"],
                 result["analysisAsOf"], result["analysisInputHash"], content_json, result["artifactHash"],
                 "research_candidate", user_id, created),
            )
        self.db.audit(organization_id, user_id, "research.property_opportunity_created", "opportunity_run",
                      run_id, {"artifact_hash": result["artifactHash"],
                               "input_hash": result["analysisInputHash"],
                               "rent_comparables": len(result["rentEvidence"]["comparables"]),
                               "sale_comparables": len(result["saleEvidence"]["comparables"]),
                               "status": "research_candidate"}, deal_id)
        return {**result, "runId": run_id, "createdAt": created}

    @staticmethod
    def _opportunity_artifact_hash(content: dict) -> str:
        payload = dict(content)
        payload.pop("artifactHash", None)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def review_property_opportunity(self, organization_id: str, user_id: str, run_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Opportunity review must be a JSON object")
        decision = str(payload.get("decision") or "").strip()
        if decision not in ("approved", "rejected", "changes_requested"):
            raise ValueError("Decision must be approved, rejected or changes_requested")
        rationale = str(payload.get("rationale") or "").strip()
        if len(rationale) < 12 or len(rationale) > 4000:
            raise ValueError("A specific review rationale of 12 to 4,000 characters is required")
        acknowledgements = payload.get("acknowledgements") or {}
        if not isinstance(acknowledgements, dict) or set(acknowledgements) - set(OPPORTUNITY_ACKNOWLEDGEMENTS):
            raise ValueError("Acknowledgements contain unsupported fields")
        normalized_acknowledgements = {key: acknowledgements.get(key) is True for key in OPPORTUNITY_ACKNOWLEDGEMENTS}
        modifications = payload.get("modifications") or []
        if not isinstance(modifications, list) or len(modifications) > 100:
            raise ValueError("Modifications must be a list of at most 100 change requests")
        normalized_modifications = []
        for item in modifications:
            if not isinstance(item, dict) or set(item) != {"path", "proposed_value", "rationale"}:
                raise ValueError("Each modification requires path, proposed_value and rationale")
            path, proposed, reason = (str(item[key]).strip() for key in ("path", "proposed_value", "rationale"))
            if not path.startswith("/") or len(path) > 300 or not proposed or len(proposed) > 2000 or len(reason) < 12 or len(reason) > 2000:
                raise ValueError("Modification fields are incomplete or exceed governed limits")
            normalized_modifications.append({"path": path, "proposed_value": proposed, "rationale": reason})
        if decision == "changes_requested" and not normalized_modifications:
            raise ValueError("Changes requested must identify at least one proposed modification")
        if decision != "changes_requested" and normalized_modifications:
            raise ValueError("Modifications are allowed only with changes_requested")
        if decision == "approved" and not all(normalized_acknowledgements.values()):
            raise ValueError("Every institutional acknowledgement is required for approval")
        created = now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM opportunity_runs WHERE id=? AND organization_id=?", (run_id, organization_id)).fetchone()
            if not run:
                raise LookupError("Property opportunity run not found")
            if decision == "approved" and run["created_by"] == user_id:
                raise ValueError("The creator cannot approve their own opportunity analysis")
            content = json.loads(run["content_json"])
            calculated = self._opportunity_artifact_hash(content)
            if calculated != run["content_sha256"] or content.get("artifactHash") != run["content_sha256"]:
                raise ValueError("Opportunity artifact integrity validation failed")
            components = content.get("quality", {}).get("components", {})
            blockers = [name for name in ("rentComparableMinimumMet", "saleComparableMinimumMet", "saleUnitsConsistent", "sourceRightsDocumented") if components.get(name) is not True]
            if decision == "approved" and blockers:
                raise ValueError("Opportunity approval blocked by: " + ", ".join(blockers))
            previous = connection.execute("SELECT decision_hash FROM opportunity_decisions WHERE organization_id=? ORDER BY rowid DESC LIMIT 1", (organization_id,)).fetchone()
            previous_hash = previous[0] if previous else None
            decision_id = str(uuid.uuid4())
            ack_json = json.dumps(normalized_acknowledgements, sort_keys=True, separators=(",", ":"))
            modification_json = json.dumps(normalized_modifications, sort_keys=True, separators=(",", ":"))
            decision_payload = {"id": decision_id, "organization_id": organization_id, "deal_id": run["deal_id"],
                                "opportunity_run_id": run_id, "actor_id": user_id, "decision": decision,
                                "rationale": rationale[:4000], "acknowledgements": normalized_acknowledgements,
                                "modifications": normalized_modifications, "artifact_sha256": run["content_sha256"],
                                "previous": previous_hash, "created_at": created}
            decision_hash = hashlib.sha256(json.dumps(decision_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            connection.execute("INSERT INTO opportunity_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (decision_id, organization_id, run["deal_id"], run_id, user_id, decision,
                                rationale[:4000], ack_json, modification_json, run["content_sha256"],
                                previous_hash, decision_hash, created))
        self.db.audit(organization_id, user_id, f"opportunity.{decision}", "opportunity_decision", decision_id,
                      {"opportunity_run_id": run_id, "artifact_sha256": run["content_sha256"],
                       "decision_hash": decision_hash, "acknowledgements": normalized_acknowledgements,
                       "modification_count": len(normalized_modifications)}, run["deal_id"])
        return {"id": decision_id, "opportunity_run_id": run_id, "decision": decision,
                "artifact_sha256": run["content_sha256"], "decision_hash": decision_hash,
                "created_at": created, "automatic_test2_apply": False}

    @staticmethod
    def _comparable_reference(item: dict, evidence_type: str) -> dict:
        fields = {key: item.get(key) for key in ("address", "observedDate", "sourceReference", "askingRent", "price", "priceUnit") if item.get(key) is not None}
        fields["evidenceType"] = evidence_type
        fields["referenceHash"] = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return fields

    def create_opportunity_test2_handoff(self, organization_id: str, user_id: str, run_id: str) -> dict:
        created = now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM opportunity_runs WHERE id=? AND organization_id=?", (run_id, organization_id)).fetchone()
            if not run:
                raise LookupError("Property opportunity run not found")
            decision = connection.execute("SELECT * FROM opportunity_decisions WHERE opportunity_run_id=? AND organization_id=? ORDER BY rowid DESC LIMIT 1", (run_id, organization_id)).fetchone()
            if not decision or decision["decision"] != "approved":
                raise ValueError("The latest independent opportunity decision must be approved before Test2 evidence handoff")
            if connection.execute("SELECT 1 FROM opportunity_handoffs WHERE opportunity_decision_id=? AND organization_id=?", (decision["id"], organization_id)).fetchone():
                raise ValueError("A Test2 evidence handoff already exists for this approval decision")
            content = json.loads(run["content_json"])
            if self._opportunity_artifact_hash(content) != run["content_sha256"] or content.get("artifactHash") != run["content_sha256"] or decision["artifact_sha256"] != run["content_sha256"]:
                raise ValueError("Approved opportunity evidence failed artifact binding")
            version = connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM opportunity_handoffs WHERE deal_id=?", (run["deal_id"],)).fetchone()[0]
            sources = [{"sourceType": key, "sourceName": value.get("sourceName"), "rightsStatus": value.get("rightsStatus"),
                        "licensingNotes": value.get("licensingNotes"), "fileSha256": value.get("fileSha256")}
                       for key, value in sorted(content.get("sources", {}).items())]
            rent_refs = [self._comparable_reference(item, "rent_comparable") for item in content.get("rentEvidence", {}).get("comparables", [])]
            sale_refs = [self._comparable_reference(item, "sale_comparable") for item in content.get("saleEvidence", {}).get("comparables", [])]
            test1_snapshot = content.get("test1Context", {}).get("snapshot") or {}
            market_hashes = [value for key, value in test1_snapshot.items() if key.lower().endswith("hash") and isinstance(value, str)]
            payload = {
                "schemaVersion": "test3-test2-property-opportunity-evidence/1.0.0",
                "status": "ADVISORY_APPROVED_EVIDENCE_NOT_APPLIED",
                "automaticApply": False,
                "controllingUnderwritingEngine": "test2",
                "dealId": run["deal_id"], "opportunityRunId": run_id,
                "opportunityArtifactSha256": run["content_sha256"], "analysisInputSha256": run["input_sha256"],
                "analysisAsOf": run["analysis_as_of"], "policyVersion": run["policy_version"],
                "approval": {"decisionId": decision["id"], "decisionHash": decision["decision_hash"],
                             "actorId": decision["actor_id"], "decision": decision["decision"],
                             "rationale": decision["rationale"], "createdAt": decision["created_at"]},
                "subject": content.get("subject"), "sourceEvidence": sources,
                "comparableEvidence": {"rent": rent_refs, "sale": sale_refs},
                "marketDefinitionHashes": sorted(set(market_hashes)),
                "economicEvidence": content.get("economicEvidence"),
                "screeningScenarios": content.get("screeningScenarios"),
                "opportunityScore": content.get("opportunityScore"),
                "quality": content.get("quality"), "limitations": content.get("limitations", []),
                "underwritingBoundary": "Evidence only. Test2 or an analyst must explicitly decide whether and how to apply it.",
                "createdAt": created,
            }
            content_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            content_hash = hashlib.sha256(content_json.encode()).hexdigest()
            handoff_id = str(uuid.uuid4())
            connection.execute("INSERT INTO opportunity_handoffs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (handoff_id, organization_id, run["deal_id"], run_id, decision["id"], version,
                                payload["schemaVersion"], content_json, content_hash, user_id, created))
        self.db.audit(organization_id, user_id, "export.opportunity_test2_evidence", "opportunity_handoff", handoff_id,
                      {"opportunity_run_id": run_id, "decision_id": decision["id"], "content_sha256": content_hash,
                       "version": version, "automatic_apply": False}, run["deal_id"])
        return {"artifact": {"id": handoff_id, "version": version, "content_sha256": content_hash,
                             "schema_version": payload["schemaVersion"], "created_at": created}, "content": payload}

    def opportunity_handoff(self, organization_id: str, handoff_id: str) -> dict:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM opportunity_handoffs WHERE id=? AND organization_id=?", (handoff_id, organization_id)).fetchone()
        if not row:
            raise LookupError("Opportunity handoff not found")
        if hashlib.sha256(row["content_json"].encode()).hexdigest() != row["content_sha256"]:
            raise ValueError("Opportunity handoff integrity validation failed")
        result = dict(row)
        result["content"] = json.loads(result.pop("content_json"))
        return result

    def import_market_panel(self, organization_id: str, user_id: str, deal_id: str | None, filename: str, content: bytes, metadata: dict) -> dict:
        parsed, rows, errors = parse_market_panel(content)
        if not rows:
            raise ValueError("Market panel contains no valid observations")
        required = ("source_name", "source_version", "as_of_date", "licensing_notes")
        if any(not str(metadata.get(key, "")).strip() for key in required):
            raise ValueError("Source name, version, as-of date and licensing notes are required")
        try:
            datetime.strptime(str(metadata["as_of_date"]), "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("Source as-of date must use YYYY-MM-DD") from error
        if metadata.get("freshness_state", "unknown") not in ("current", "stale", "unknown"):
            raise ValueError("Freshness state must be current, stale or unknown")
        snapshot_id, created = str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            if connection.execute("SELECT 1 FROM data_source_snapshots WHERE organization_id=? AND (deal_id=? OR (deal_id IS NULL AND ? IS NULL)) AND content_sha256=?", (organization_id, deal_id, deal_id, parsed["fileSha256"])).fetchone():
                raise ValueError("This exact market panel was already imported for the deal")
        stored_name = f"{snapshot_id}.csv"
        storage_scope = deal_id or "_global"
        destination = (self.market_data_dir / organization_id / storage_scope / stored_name).resolve()
        expected = (self.market_data_dir / organization_id / storage_scope).resolve()
        if expected not in destination.parents:
            raise ValueError("Unsafe market-data storage path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        observations = rows_to_observations(snapshot_id, organization_id, rows, created)
        coverage = sorted({row.get("market_id") for row in rows if row.get("market_id")})
        property_types = sorted({row.get("property_type") for row in rows})
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if deal_id and not connection.execute("SELECT 1 FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone():
                raise LookupError("Deal not found")
            connection.execute("INSERT INTO data_source_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (snapshot_id, organization_id, deal_id, "market_panel", str(metadata["source_name"])[:200], str(metadata["source_version"])[:100], str(metadata["as_of_date"]), created, json.dumps({filename: parsed["fileSha256"]}, sort_keys=True), parsed["schemaVersion"], json.dumps(coverage), "market", json.dumps(property_types), str(metadata["licensing_notes"])[:2000], str(metadata.get("freshness_state", "unknown")), "partial" if errors else "valid", user_id, parsed["fileSha256"], stored_name, created))
            for item in observations:
                connection.execute("INSERT INTO market_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), item["organization_id"], item["snapshot_id"], item["metric"], item["value"], item["unit"], item["currency"], item["observation_date"], item["effective_date"], item["geography_type"], item["geography_id"], item["county_fips"], item["cbsa"], item["submarket"], item["property_type"], item["property_subtype"], item["source_label"], item["source_reference"], item["sample_count"], item["quality_level"], item["methodology_notes"], item["original_field_name"], item["transformation_version"], item["original_row_hash"], item["source_row"], item["validation_errors_json"], item["created_at"]))
        self.db.audit(organization_id, user_id, "market_panel.imported", "data_source_snapshot", snapshot_id, {"file_sha256": parsed["fileSha256"], "valid_rows": len(rows), "invalid_rows": len(errors), "observations": len(observations)}, deal_id)
        return {"snapshotId": snapshot_id, "validRows": len(rows), "invalidRows": len(errors), "observationCount": len(observations), "errors": errors, "fileSha256": parsed["fileSha256"]}

    def run_assumption_intelligence(self, organization_id: str, user_id: str, deal_id: str, assumption_type: str, context: dict) -> dict:
        if assumption_type not in BY_NAME:
            raise ValueError("Unsupported assumption type")
        with self.db.connect() as connection:
            deal = connection.execute("SELECT * FROM deals WHERE id=? AND organization_id=?", (deal_id, organization_id)).fetchone()
            if not deal:
                raise LookupError("Deal not found")
            observations = [dict(row) for row in connection.execute("SELECT o.* FROM market_observations o JOIN data_source_snapshots s ON s.id=o.snapshot_id WHERE o.organization_id=? AND (s.deal_id=? OR s.deal_id IS NULL) ORDER BY o.observation_date", (organization_id, deal_id))]
            artifacts = connection.execute("""SELECT * FROM model_artifacts
                WHERE organization_id=? AND target_assumption=? AND data_status='real' AND validation_state='validated'
                ORDER BY created_at DESC LIMIT 20""", (organization_id, assumption_type)).fetchall()
        model_artifact = None
        for candidate in artifacts:
            parsed = dict(candidate)
            parsed["property_types"] = json.loads(parsed.pop("property_types_json"))
            parsed["model_metrics"] = json.loads(parsed.pop("model_metrics_json"))
            if deal["property_type"] in parsed["property_types"]:
                model_artifact = parsed
                break
        recommendation = recommend(assumption_type, dict(deal), observations, dict(context or {}), model_artifact=model_artifact)
        run_id, created = str(uuid.uuid4()), now()
        recommendation["id"] = run_id
        run_hash = canonical_hash({**recommendation, "createdBy": user_id, "createdAt": created})
        snapshot_ids = sorted({row["snapshot_id"] for row in observations if row["id"] in recommendation.get("supportingEvidence", [])})
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO assumption_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, organization_id, deal_id, assumption_type, recommendation.get("modelArtifactId"), json.dumps(snapshot_ids), json.dumps(recommendation.get("inputFeatures", {}), sort_keys=True), recommendation.get("inputSha256", canonical_hash({})), created, recommendation.get("low"), recommendation.get("base"), recommendation.get("high"), recommendation.get("modelEstimate"), recommendation.get("benchmarkEstimate"), recommendation.get("confidence", "unavailable"), json.dumps(recommendation.get("confidenceComponents", {}), sort_keys=True), recommendation.get("dataCompleteness", 0), recommendation.get("freshnessScore", 0), recommendation.get("geographicMatchScore", 0), recommendation.get("propertyMatchScore", 0), int(recommendation.get("outOfDomain", False)), recommendation.get("method", "unavailable"), recommendation.get("fallbackLevel", "unavailable"), json.dumps(recommendation.get("limitations", [])), recommendation.get("rationale", "Candidate only; analyst approval required."), json.dumps(recommendation.get("dataWindow")) if recommendation.get("dataWindow") else None, recommendation.get("sampleCount", 0), run_hash, user_id, created))
            for observation_id in recommendation.get("supportingEvidence", []):
                connection.execute("INSERT INTO assumption_evidence VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), organization_id, run_id, observation_id, "included", "Selected by the documented fallback hierarchy.", created))
        self.db.audit(organization_id, user_id, "assumption_run.created", "assumption_run", run_id, {"assumption_type": assumption_type, "run_hash": run_hash, "candidate_only": True}, deal_id)
        return recommendation

    def run_market_rent_growth(self, organization_id: str, user_id: str, deal_id: str, context: dict) -> dict:
        return self.run_assumption_intelligence(organization_id, user_id, deal_id, "market_rent_growth", context)

    def install_model_artifact(self, organization_id: str, user_id: str, artifact_path: Path) -> dict:
        artifact = load_artifact(artifact_path, Path(__file__).resolve().parents[2])
        artifact_id, created = str(uuid.uuid4()), now()
        with self.db.connect() as connection:
            existing = connection.execute("SELECT id FROM model_artifacts WHERE organization_id=? AND artifact_content_hash=?", (organization_id, artifact["artifact_content_hash"])).fetchone()
            if existing:
                return {"id": existing["id"], "duplicate": True, "dataStatus": artifact["data_status"]}
            connection.execute("INSERT INTO model_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (artifact_id, organization_id, artifact["model_name"], artifact["model_version"], artifact["target_assumption"], artifact["training_data_snapshot_hash"], artifact["feature_schema_version"], artifact["training_window"], artifact["validation_window"], json.dumps(artifact["property_types"]), json.dumps(artifact["geographic_coverage"]), int(artifact["sample_size"]), json.dumps(artifact["coefficients"], sort_keys=True), json.dumps(artifact["standard_errors"], sort_keys=True), json.dumps(artifact["model_metrics"], sort_keys=True), json.dumps(artifact["residual_diagnostics"], sort_keys=True), json.dumps(artifact["limitations"]), artifact["source_code_path"], artifact["source_code_sha256"], artifact["repository_commit_sha"], artifact["r_version"], artifact.get("package_lock_sha256"), artifact["artifact_content_hash"], artifact["model_card_path"], artifact["validation_results_path"], artifact["input_schema_path"], artifact["data_status"], artifact.get("validation_state", "rejected"), created))
        self.db.audit(organization_id, user_id, "model_artifact.installed", "model_artifact", artifact_id, {"content_sha256": artifact["artifact_content_hash"], "data_status": artifact["data_status"], "validation_state": artifact.get("validation_state", "rejected")})
        return {"id": artifact_id, "duplicate": False, "dataStatus": artifact["data_status"], "validationState": artifact.get("validation_state", "rejected")}

    def import_test1_economic(self, organization_id: str, user_id: str, deal_id: str) -> dict:
        if not self.test1_data_dir:
            raise ValueError("A local Test1 data directory is not configured")
        with self.db.connect() as connection:
            approved = connection.execute("SELECT rd.proposed_normalized_value FROM manual_assumptions ma JOIN review_decisions rd ON rd.entity_id=ma.id AND rd.entity_type='manual_assumption' WHERE ma.organization_id=? AND ma.deal_id=? AND ma.field_name='county_fips' AND ma.review_status='approved' ORDER BY rd.rowid DESC LIMIT 1", (organization_id, deal_id)).fetchone()
            if not approved:
                approved = connection.execute("SELECT rd.proposed_normalized_value FROM extracted_values ev JOIN review_decisions rd ON rd.entity_id=ev.id AND rd.entity_type='extracted_value' WHERE ev.organization_id=? AND ev.deal_id=? AND ev.field_name='county_fips' AND ev.review_status='approved' ORDER BY rd.rowid DESC LIMIT 1", (organization_id, deal_id)).fetchone()
        if not approved:
            raise ValueError("An approved county FIPS is required before Test1 economic import")
        economy_dir = self.test1_data_dir / "economy" if (self.test1_data_dir / "economy").is_dir() else self.test1_data_dir
        snapshot, rows = load_test1_economic(economy_dir, approved[0])
        snapshot_id, created = str(uuid.uuid4()), now()
        content_hash = canonical_hash({"snapshot": snapshot, "rows": rows})
        with self.db.connect() as connection:
            connection.execute("INSERT INTO data_source_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (snapshot_id, organization_id, deal_id, "test1_economic", "Test1 local economic snapshot", snapshot["sourceVersion"], snapshot.get("asOfDate"), created, json.dumps(snapshot["fileHashes"], sort_keys=True), "test1-economic-normalization/1.0", json.dumps(snapshot["coverage"], sort_keys=True), "county_and_national", "[]", "Upstream public data snapshot; verify source terms recorded by Test1.", snapshot["freshnessState"] if snapshot["freshnessState"] in ("current", "stale", "unknown") else "unknown", "valid", user_id, content_hash, None, created))
            for index, row in enumerate(rows, 1):
                digest = canonical_hash(row)
                connection.execute("INSERT INTO market_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), organization_id, snapshot_id, row["metric"], row["value"], "decimal_fraction" if row["metric"] in ("inflation", "unemployment_rate", "treasury_rate") else "count_or_level", None, row["observation_date"], None, row["geography_type"], row["geography_id"], row["county_fips"], None, None, None, None, row["source_label"], row["source_reference"], None, "moderate", "Normalized from documented Test1 local economic JSON without imputation.", row["original_field_name"], "test1-economic/1.0", digest, index, "[]", created))
        self.db.audit(organization_id, user_id, "test1_economic.imported", "data_source_snapshot", snapshot_id, {"content_sha256": content_hash, "observation_count": len(rows), "county_fips": approved[0]}, deal_id)
        return {"snapshotId": snapshot_id, "observationCount": len(rows), "contentSha256": content_hash, "networkRequests": 0}

    def decide_assumption_run(self, organization_id: str, user_id: str, run_id: str, selection: str, custom_value: str | None, rationale: str, controlling_source: str) -> dict:
        if selection not in ("low", "base", "high", "custom", "rejected") or not rationale.strip() or not controlling_source.strip():
            raise ValueError("A valid selection, rationale and controlling source are required")
        with self.db.connect() as connection:
            run = connection.execute("SELECT * FROM assumption_runs WHERE id=? AND organization_id=?", (run_id, organization_id)).fetchone()
        if not run:
            raise LookupError("Assumption run not found")
        value = custom_value if selection == "custom" else run[f"{selection}_recommendation"] if selection in ("low", "base", "high") else run["base_recommendation"] or "0"
        assumption = self.create_assumption(organization_id, user_id, run["deal_id"], {"field_name": run["assumption_type"], "proposed_value": value, "rationale": rationale})
        review = self.review_assumption(organization_id, user_id, assumption["id"], "rejected" if selection == "rejected" else "approved", None if selection == "rejected" else value, rationale)
        created = now()
        context_value = {"runId": run_id, "selection": selection, "value": value, "rationale": rationale, "controllingSource": controlling_source, "reviewDecisionId": review["decision_id"]}
        with self.db.connect() as connection:
            connection.execute("INSERT INTO assumption_decision_context VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), organization_id, run["deal_id"], run_id, assumption["id"], review["decision_id"], selection, controlling_source[:500], canonical_hash(context_value), created))
        self.db.audit(organization_id, user_id, "assumption_run.decided", "assumption_run", run_id, context_value, run["deal_id"])
        return {"runId": run_id, "selection": selection, "manualAssumptionId": assumption["id"], "reviewDecisionId": review["decision_id"], "status": review["review_status"]}

    def create_assumption_run_handoff(self, organization_id: str, user_id: str, run_id: str) -> dict:
        """Phase 6: builds and returns a creos-handoff-v1 payload for one
        assumption run -- CREOS Underwrite's counterpart to Phase 5's
        SiteIntel "Send to Underwrite" export. See creos_handoff.py's
        module docstring for the translation-layer decisions. Read-only:
        an assumption run is an immutable candidate (see the
        assumption_runs_no_update/no_delete triggers in db.py), and
        building a handoff from it doesn't change that -- this handoff
        can be regenerated identically at any time, and does not require
        the run to have been decided inside this app first (the receiving
        side's own governance rule forces status:'proposed' regardless of
        what, if anything, this app already decided for its own deal)."""
        with self.db.connect() as connection:
            run = connection.execute("SELECT * FROM assumption_runs WHERE id=? AND organization_id=?", (run_id, organization_id)).fetchone()
            if not run:
                raise LookupError("Assumption run not found")
            deal = connection.execute("SELECT * FROM deals WHERE id=? AND organization_id=?", (run["deal_id"], organization_id)).fetchone()
            if not deal:
                raise LookupError("Deal not found")
        catalog_spec = BY_NAME.get(run["assumption_type"])
        if not catalog_spec:
            raise ValueError(f"Unknown assumption type: {run['assumption_type']}")
        run_dict = dict(run)
        run_dict["limitations"] = json.loads(run["limitations_json"] or "[]")
        payload = build_assumption_run_handoff(run=run_dict, deal=dict(deal), catalog_spec=catalog_spec)
        self.db.audit(organization_id, user_id, "assumption_run.handoff_generated", "assumption_run", run_id, {"handoff_id": payload["handoffId"], "assumption_type": run["assumption_type"]}, run["deal_id"])
        return payload

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
            inserted_cells = []
            for candidate in candidates:
                value_id = str(uuid.uuid4())
                source_hash = hashlib.sha256(candidate.excerpt.encode()).hexdigest()
                connection.execute("INSERT INTO extracted_values(id,organization_id,deal_id,document_id,document_version,document_category,field_name,raw_value,normalized_value,unit,currency,page_number,bbox_json,source_excerpt,source_text_hash,extraction_method,extractor_version,confidence,validation_status,review_status,reviewer_id,reviewed_at,comments,superseded_value_id,final_approved_value_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (value_id, organization_id, deal_id, document_id, 1, category, candidate.field, candidate.raw, candidate.normalized, candidate.unit, candidate.currency, candidate.page, json.dumps(candidate.bbox) if candidate.bbox else None, candidate.excerpt, source_hash, candidate.method, "2.0", candidate.confidence, "valid" if candidate.normalized is not None else "needs_review", "needs_review", None, None, error, None, None, created))
                inserted_cells.append({"id": value_id, "field_name": candidate.field, "raw_value": candidate.raw, "normalized_value": candidate.normalized, "page_number": candidate.page})
            entities = derive_entities(category, inserted_cells)
            for entity in entities:
                connection.execute("INSERT INTO semantic_entities(id,organization_id,deal_id,document_id,document_version,document_category,entity_type,source_page,source_row,data_json,data_sha256,source_value_ids_json,extractor_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), organization_id, deal_id, document_id, 1, category, entity["entity_type"], entity["source_page"], entity["source_row"], entity["data_json"], entity["data_sha256"], json.dumps(entity["source_value_ids"]), "semantic-table/1.1", created))
        self.db.audit(organization_id, user_id, "document.uploaded", "document", document_id, {"sha256": digest, "size": len(content), "mime": mime, "category": category, "processing": status, "warning": error}, deal_id)
        return {"id": document_id, "category": category, "status": status, "sha256": digest, "candidates": len(candidates), "semanticEntities": len(entities), "warning": error}

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
            semantic_entities = connection.execute("SELECT id,deal_id,document_id,data_json,data_sha256,source_value_ids_json FROM semantic_entities WHERE organization_id=?", (organization_id,)).fetchall()
            market_snapshots = connection.execute("SELECT id,deal_id,original_stored_name,content_sha256 FROM data_source_snapshots WHERE organization_id=? AND source_type='market_panel'", (organization_id,)).fetchall()
            opportunity_runs = connection.execute("SELECT id,deal_id,content_json,content_sha256 FROM opportunity_runs WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
            opportunity_decisions = connection.execute("SELECT * FROM opportunity_decisions WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
            opportunity_handoffs = connection.execute("SELECT * FROM opportunity_handoffs WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
            opportunity_candidates = connection.execute("SELECT * FROM opportunity_candidates WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
            opportunity_candidate_versions = connection.execute("SELECT * FROM opportunity_candidate_versions WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
            opportunity_screening_runs = connection.execute("SELECT * FROM opportunity_screening_runs WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
            extracted_membership = {(row["id"], row["deal_id"], row["document_id"]) for row in connection.execute("SELECT id,deal_id,document_id FROM extracted_values WHERE organization_id=?", (organization_id,)).fetchall()}
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
        market_integrity = {"count": len(market_snapshots), "missingOriginals": 0, "hashMismatches": 0, "unsafePaths": 0}
        market_root = self.market_data_dir.resolve()
        for snapshot in market_snapshots:
            path = (self.market_data_dir / organization_id / (snapshot["deal_id"] or "_global") / snapshot["original_stored_name"]).resolve()
            if market_root not in path.parents:
                market_integrity["unsafePaths"] += 1
            elif not path.is_file():
                market_integrity["missingOriginals"] += 1
            elif _sha256_file(path) != snapshot["content_sha256"]:
                market_integrity["hashMismatches"] += 1
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
        semantic_hash_mismatches, semantic_source_mismatches = 0, 0
        for entity in semantic_entities:
            if hashlib.sha256(entity["data_json"].encode()).hexdigest() != entity["data_sha256"]:
                semantic_hash_mismatches += 1
            try:
                source_ids = json.loads(entity["source_value_ids_json"])
                if not isinstance(source_ids, list) or not source_ids or any((source_id, entity["deal_id"], entity["document_id"]) not in extracted_membership for source_id in source_ids):
                    semantic_source_mismatches += 1
            except (json.JSONDecodeError, TypeError):
                semantic_source_mismatches += 1
        semantic_integrity = {"count": len(semantic_entities), "hashMismatches": semantic_hash_mismatches, "sourceMismatches": semantic_source_mismatches}
        opportunity_membership = {(item["id"], item["deal_id"], item["content_sha256"]) for item in opportunity_runs}
        opportunity_hash_mismatches = 0
        for run in opportunity_runs:
            try:
                content = json.loads(run["content_json"])
                if self._opportunity_artifact_hash(content) != run["content_sha256"] or content.get("artifactHash") != run["content_sha256"]:
                    opportunity_hash_mismatches += 1
            except (json.JSONDecodeError, TypeError):
                opportunity_hash_mismatches += 1
        opportunity_decision_mismatches, expected_previous = 0, None
        for item in opportunity_decisions:
            try:
                acknowledgements = json.loads(item["acknowledgements_json"])
                modifications = json.loads(item["modifications_json"])
                payload = {"id": item["id"], "organization_id": item["organization_id"], "deal_id": item["deal_id"],
                           "opportunity_run_id": item["opportunity_run_id"], "actor_id": item["actor_id"],
                           "decision": item["decision"], "rationale": item["rationale"],
                           "acknowledgements": acknowledgements, "modifications": modifications,
                           "artifact_sha256": item["artifact_sha256"], "previous": item["previous_hash"],
                           "created_at": item["created_at"]}
                calculated = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if (item["opportunity_run_id"], item["deal_id"], item["artifact_sha256"]) not in opportunity_membership or item["previous_hash"] != expected_previous or calculated != item["decision_hash"]:
                    opportunity_decision_mismatches += 1
            except (json.JSONDecodeError, TypeError):
                opportunity_decision_mismatches += 1
            expected_previous = item["decision_hash"]
        opportunity_integrity = {"runCount": len(opportunity_runs), "runHashMismatches": opportunity_hash_mismatches,
                                 "decisionCount": len(opportunity_decisions), "decisionMismatches": opportunity_decision_mismatches}
        decision_membership = {(item["id"], item["opportunity_run_id"], item["artifact_sha256"], item["decision"]) for item in opportunity_decisions}
        opportunity_handoff_mismatches = 0
        for item in opportunity_handoffs:
            if (hashlib.sha256(item["content_json"].encode()).hexdigest() != item["content_sha256"]
                    or (item["opportunity_decision_id"], item["opportunity_run_id"],
                        next((run["content_sha256"] for run in opportunity_runs if run["id"] == item["opportunity_run_id"]), None),
                        "approved") not in decision_membership):
                opportunity_handoff_mismatches += 1
        opportunity_integrity["handoffCount"] = len(opportunity_handoffs)
        opportunity_integrity["handoffMismatches"] = opportunity_handoff_mismatches
        candidate_membership = {item["id"] for item in opportunity_candidates}
        candidate_property_types = {item["id"]: item["property_type"] for item in opportunity_candidates}
        version_membership = {(item["id"], item["candidate_id"]) for item in opportunity_candidate_versions}
        candidate_version_mismatches = 0
        version_snapshots = {}
        for item in opportunity_candidate_versions:
            try:
                snapshot = json.loads(item["content_json"])
                version_snapshots[item["id"]] = snapshot
                if (item["candidate_id"] not in candidate_membership
                        or sha256_json(snapshot) != item["content_sha256"]
                        or snapshot.get("candidateId") != item["candidate_id"]
                        or snapshot.get("propertyType") != candidate_property_types.get(item["candidate_id"])
                        or snapshot.get("schemaVersion") != item["schema_version"]
                        or (snapshot.get("inputs") or {}).get("analysis_as_of") != item["analysis_as_of"]):
                    candidate_version_mismatches += 1
            except (json.JSONDecodeError, TypeError, ValueError):
                candidate_version_mismatches += 1
        screening_run_mismatches, policy_implementation_unavailable = 0, 0
        for item in opportunity_screening_runs:
            try:
                result = json.loads(item["result_json"])
                snapshot = version_snapshots.get(item["candidate_version_id"])
                evaluated = datetime.fromisoformat(item["evaluated_at"])
                policy = registered_screening_policy(item["policy_id"], item["policy_version"], item["policy_sha256"])
                if policy is None:
                    policy_implementation_unavailable += 1
                    screening_run_mismatches += 1
                    continue
                reproduced = screen_opportunity(screening_input_from_snapshot(snapshot), policy=policy,
                                                evaluated_at=evaluated).to_dict()
                if ((item["candidate_version_id"], item["candidate_id"]) not in version_membership
                        or item["candidate_id"] not in candidate_membership
                        or sha256_json(result) != item["result_sha256"]
                        or result != reproduced
                        or result.get("policyId") != item["policy_id"]
                        or result.get("policyVersion") != item["policy_version"]
                        or result.get("policyHash") != item["policy_sha256"]
                        or result.get("inputSnapshotHash") != item["input_snapshot_sha256"]
                        or result.get("evidenceHash") != item["evidence_sha256"]
                        or result.get("screeningTier") != item["screening_tier"]
                        or result.get("evaluatedAt") != item["evaluated_at"]):
                    screening_run_mismatches += 1
            except (json.JSONDecodeError, TypeError, ValueError, KeyError, AttributeError):
                screening_run_mismatches += 1
        finder_integrity = {"candidateCount": len(opportunity_candidates),
                            "versionCount": len(opportunity_candidate_versions),
                            "versionMismatches": candidate_version_mismatches,
                            "screeningRunCount": len(opportunity_screening_runs),
                            "screeningRunMismatches": screening_run_mismatches,
                            "policyImplementationUnavailable": policy_implementation_unavailable}
        market_ok = not any(market_integrity[key] for key in ("missingOriginals", "hashMismatches", "unsafePaths"))
        return {"ok": database["ok"] and audit_valid and review_valid and storage_ok and market_ok and artifact_mismatches == 0 and semantic_hash_mismatches == 0 and semantic_source_mismatches == 0 and opportunity_hash_mismatches == 0 and opportunity_decision_mismatches == 0 and opportunity_handoff_mismatches == 0 and candidate_version_mismatches == 0 and screening_run_mismatches == 0, "checkedAt": now(), "database": database, "chains": chains, "storage": storage, "marketData": market_integrity, "exports": artifact_integrity, "semanticEntities": semantic_integrity, "propertyOpportunity": opportunity_integrity, "opportunityFinder": finder_integrity, "purgeStagingFiles": staging_files, "networkRequests": 0}

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
            approved_intelligence = [item for item in approved if item["field_name"] in BY_NAME]
            model_ids = sorted({item.get("model_artifact_id") for item in snapshot.get("assumption_runs", []) if item.get("model_artifact_id")})
            model_evidence = []
            if model_ids:
                with self.db.connect() as connection:
                    placeholders = ",".join("?" for _ in model_ids)
                    rows = connection.execute(f"""SELECT id,model_name,model_version,target_assumption,
                        training_data_snapshot_hash,feature_schema_version,training_window,validation_window,
                        model_metrics_json,residual_diagnostics_json,artifact_content_hash,data_status,validation_state
                        FROM model_artifacts WHERE organization_id=? AND id IN ({placeholders})""",
                        (organization_id, *model_ids)).fetchall()
                for row in rows:
                    item = dict(row)
                    item["model_metrics"] = json.loads(item.pop("model_metrics_json"))
                    item["residual_diagnostics"] = json.loads(item.pop("residual_diagnostics_json"))
                    model_evidence.append(item)
            intelligence = {
                "observedEvidence": snapshot.get("market_observations", []),
                "modelRecommendations": snapshot.get("assumption_runs", []),
                "analystApprovedAssumptions": [{"id": item["id"], "field": item["field_name"], "value": item["normalized_value"], "decisionId": item.get("latest_decision_id")} for item in approved_intelligence],
                "provenance": snapshot.get("assumption_decision_contexts", []),
                "modelEvidence": model_evidence,
                "snapshotMetadata": snapshot.get("data_source_snapshots", []),
                "mappingNote": "Only analyst-approved supported growth assumptions map to standalone Test2 growth curves. Linking curves or unsupported assumptions to specific underwriting objects remains an explicit Test2 analyst action.",
            }
            result = test2_export(snapshot["deal"], approved, snapshot["findings"], snapshot["entities"], assumption_intelligence=intelligence)
        elif kind == "memo":
            result = diligence_summary(snapshot["deal"], approved, snapshot["findings"], snapshot["documents"], snapshot["values"])
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
