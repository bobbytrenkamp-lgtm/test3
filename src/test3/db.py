from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA_VERSION = 12


def _decimal_compare(left: object, right: object, operator) -> int:
    """Losslessly compare canonical decimal text inside SQLite queries."""
    if left is None or right is None:
        return 0
    try:
        first, second = Decimal(str(left)), Decimal(str(right))
    except (InvalidOperation, ValueError):
        return 0
    if not first.is_finite() or not second.is_finite():
        return 0
    return int(operator(first, second))


def _decimal_gte(left: object, right: object) -> int:
    return _decimal_compare(left, right, lambda first, second: first >= second)


def _decimal_lte(left: object, right: object) -> int:
    return _decimal_compare(left, right, lambda first, second: first <= second)

def now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), email TEXT NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','analyst','reviewer','viewer')), password_hash TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(organization_id,email));
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, csrf_token TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deals(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), name TEXT NOT NULL, address TEXT, property_type TEXT, status TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), original_name TEXT NOT NULL, stored_name TEXT NOT NULL, detected_mime TEXT NOT NULL, category TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, uploader_id TEXT NOT NULL REFERENCES users(id), uploaded_at TEXT NOT NULL, processing_status TEXT NOT NULL, malware_scan_status TEXT NOT NULL DEFAULT 'not_available', original_purged_at TEXT, original_purged_by TEXT REFERENCES users(id), original_purge_reason TEXT, UNIQUE(deal_id,sha256));
CREATE TABLE IF NOT EXISTS document_purges(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), document_id TEXT NOT NULL REFERENCES documents(id), actor_id TEXT NOT NULL REFERENCES users(id), original_sha256 TEXT NOT NULL, original_size_bytes INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS document_purges_no_update BEFORE UPDATE ON document_purges BEGIN SELECT RAISE(ABORT, 'document purges are append-only'); END;
CREATE TRIGGER IF NOT EXISTS document_purges_no_delete BEFORE DELETE ON document_purges BEGIN SELECT RAISE(ABORT, 'document purges are append-only'); END;
CREATE TABLE IF NOT EXISTS document_versions(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), version INTEGER NOT NULL, extractor_version TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(document_id,version));
CREATE TABLE IF NOT EXISTS extracted_values(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), document_id TEXT NOT NULL REFERENCES documents(id), document_version INTEGER NOT NULL, document_category TEXT NOT NULL, field_name TEXT NOT NULL, raw_value TEXT NOT NULL, normalized_value TEXT, unit TEXT, currency TEXT, page_number INTEGER, bbox_json TEXT, source_excerpt TEXT NOT NULL, source_text_hash TEXT NOT NULL, extraction_method TEXT NOT NULL, extractor_version TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1), validation_status TEXT NOT NULL, review_status TEXT NOT NULL, reviewer_id TEXT REFERENCES users(id), reviewed_at TEXT, comments TEXT, superseded_value_id TEXT REFERENCES extracted_values(id), final_approved_value_id TEXT REFERENCES extracted_values(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS semantic_entities(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), document_id TEXT NOT NULL REFERENCES documents(id), document_version INTEGER NOT NULL, document_category TEXT NOT NULL, entity_type TEXT NOT NULL CHECK(entity_type IN ('rent_roll_record','operating_account_period','lease_schedule_record','debt_term_record')), source_page INTEGER NOT NULL DEFAULT 1, source_row INTEGER NOT NULL, data_json TEXT NOT NULL, data_sha256 TEXT NOT NULL, source_value_ids_json TEXT NOT NULL, extractor_version TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(document_id,document_version,entity_type,source_page,source_row));
CREATE TRIGGER IF NOT EXISTS semantic_entities_no_update BEFORE UPDATE ON semantic_entities BEGIN SELECT RAISE(ABORT, 'semantic entities are immutable derived evidence'); END;
CREATE TRIGGER IF NOT EXISTS semantic_entities_no_delete BEFORE DELETE ON semantic_entities BEGIN SELECT RAISE(ABORT, 'semantic entities are retained evidence'); END;
CREATE TABLE IF NOT EXISTS data_source_snapshots(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT REFERENCES deals(id), source_type TEXT NOT NULL CHECK(source_type IN ('test1_economic','market_panel','public_extract','analyst_comp_package')), source_name TEXT NOT NULL, source_version TEXT NOT NULL, as_of_date TEXT, imported_at TEXT NOT NULL, file_hashes_json TEXT NOT NULL, schema_version TEXT NOT NULL, coverage_json TEXT NOT NULL, geography_level TEXT NOT NULL, property_type_coverage_json TEXT NOT NULL, licensing_notes TEXT NOT NULL, freshness_state TEXT NOT NULL CHECK(freshness_state IN ('current','stale','unknown')), validation_state TEXT NOT NULL CHECK(validation_state IN ('valid','partial','invalid')), import_actor TEXT NOT NULL REFERENCES users(id), content_sha256 TEXT NOT NULL, original_stored_name TEXT, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS data_source_snapshots_no_update BEFORE UPDATE ON data_source_snapshots BEGIN SELECT RAISE(ABORT, 'data source snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS data_source_snapshots_no_delete BEFORE DELETE ON data_source_snapshots BEGIN SELECT RAISE(ABORT, 'data source snapshots are retained evidence'); END;
CREATE TABLE IF NOT EXISTS market_observations(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), snapshot_id TEXT NOT NULL REFERENCES data_source_snapshots(id), metric TEXT NOT NULL, value TEXT NOT NULL, unit TEXT NOT NULL, currency TEXT, observation_date TEXT NOT NULL, effective_date TEXT, geography_type TEXT NOT NULL, geography_id TEXT NOT NULL, county_fips TEXT, cbsa TEXT, submarket TEXT, property_type TEXT, property_subtype TEXT, source_label TEXT NOT NULL, source_reference TEXT NOT NULL, sample_count INTEGER, quality_level TEXT NOT NULL CHECK(quality_level IN ('high','moderate','low','unknown')), methodology_notes TEXT NOT NULL, original_field_name TEXT NOT NULL, transformation_version TEXT NOT NULL, original_row_hash TEXT NOT NULL, source_row INTEGER, validation_errors_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(snapshot_id,metric,observation_date,geography_type,geography_id,property_type,property_subtype,original_row_hash));
CREATE TRIGGER IF NOT EXISTS market_observations_no_update BEFORE UPDATE ON market_observations BEGIN SELECT RAISE(ABORT, 'market observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS market_observations_no_delete BEFORE DELETE ON market_observations BEGIN SELECT RAISE(ABORT, 'market observations are retained evidence'); END;
CREATE INDEX IF NOT EXISTS market_observations_metric_date ON market_observations(organization_id,metric,observation_date);
CREATE INDEX IF NOT EXISTS market_observations_geography ON market_observations(organization_id,geography_type,geography_id,property_type,metric);
CREATE INDEX IF NOT EXISTS market_observations_snapshot ON market_observations(snapshot_id);
CREATE TABLE IF NOT EXISTS model_artifacts(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), model_name TEXT NOT NULL, model_version TEXT NOT NULL, target_assumption TEXT NOT NULL, training_data_snapshot_hash TEXT NOT NULL, feature_schema_version TEXT NOT NULL, training_window TEXT NOT NULL, validation_window TEXT NOT NULL, property_types_json TEXT NOT NULL, geographic_coverage_json TEXT NOT NULL, sample_size INTEGER NOT NULL, coefficients_json TEXT NOT NULL, standard_errors_json TEXT NOT NULL, model_metrics_json TEXT NOT NULL, residual_diagnostics_json TEXT NOT NULL, limitations_json TEXT NOT NULL, source_code_path TEXT NOT NULL, source_code_sha256 TEXT NOT NULL, repository_commit_sha TEXT NOT NULL, r_version TEXT NOT NULL, package_lock_sha256 TEXT, artifact_content_hash TEXT NOT NULL, model_card_path TEXT NOT NULL, validation_results_path TEXT NOT NULL, input_schema_path TEXT NOT NULL, data_status TEXT NOT NULL CHECK(data_status IN ('real','fictional_synthetic')), validation_state TEXT NOT NULL CHECK(validation_state IN ('validated','rejected')), created_at TEXT NOT NULL, UNIQUE(organization_id,artifact_content_hash));
CREATE TRIGGER IF NOT EXISTS model_artifacts_no_update BEFORE UPDATE ON model_artifacts BEGIN SELECT RAISE(ABORT, 'model artifacts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS model_artifacts_no_delete BEFORE DELETE ON model_artifacts BEGIN SELECT RAISE(ABORT, 'model artifacts are retained evidence'); END;
CREATE TABLE IF NOT EXISTS assumption_runs(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), assumption_type TEXT NOT NULL, model_artifact_id TEXT REFERENCES model_artifacts(id), evidence_snapshot_ids_json TEXT NOT NULL, input_features_json TEXT NOT NULL, input_sha256 TEXT NOT NULL, run_at TEXT NOT NULL, low_recommendation TEXT, base_recommendation TEXT, high_recommendation TEXT, model_estimate TEXT, benchmark_estimate TEXT, confidence TEXT NOT NULL CHECK(confidence IN ('high','moderate','low','unavailable')), confidence_components_json TEXT NOT NULL, data_completeness REAL NOT NULL CHECK(data_completeness BETWEEN 0 AND 1), freshness_score REAL NOT NULL CHECK(freshness_score BETWEEN 0 AND 1), geographic_match_score REAL NOT NULL CHECK(geographic_match_score BETWEEN 0 AND 1), property_match_score REAL NOT NULL CHECK(property_match_score BETWEEN 0 AND 1), out_of_domain INTEGER NOT NULL CHECK(out_of_domain IN (0,1)), method TEXT NOT NULL, fallback_level TEXT NOT NULL, limitations_json TEXT NOT NULL, rationale TEXT NOT NULL, data_window TEXT, sample_count INTEGER NOT NULL, run_hash TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS assumption_runs_no_update BEFORE UPDATE ON assumption_runs BEGIN SELECT RAISE(ABORT, 'assumption runs are immutable candidates'); END;
CREATE TRIGGER IF NOT EXISTS assumption_runs_no_delete BEFORE DELETE ON assumption_runs BEGIN SELECT RAISE(ABORT, 'assumption runs are retained evidence'); END;
CREATE INDEX IF NOT EXISTS assumption_runs_deal_type ON assumption_runs(organization_id,deal_id,assumption_type,created_at);
CREATE TABLE IF NOT EXISTS assumption_evidence(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), run_id TEXT NOT NULL REFERENCES assumption_runs(id), observation_id TEXT NOT NULL REFERENCES market_observations(id), evidence_role TEXT NOT NULL CHECK(evidence_role IN ('included','excluded')), reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,observation_id));
CREATE TRIGGER IF NOT EXISTS assumption_evidence_no_update BEFORE UPDATE ON assumption_evidence BEGIN SELECT RAISE(ABORT, 'assumption evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS assumption_evidence_no_delete BEFORE DELETE ON assumption_evidence BEGIN SELECT RAISE(ABORT, 'assumption evidence is retained'); END;
CREATE TABLE IF NOT EXISTS assumption_decision_context(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), run_id TEXT NOT NULL REFERENCES assumption_runs(id), manual_assumption_id TEXT NOT NULL REFERENCES manual_assumptions(id), review_decision_id TEXT NOT NULL REFERENCES review_decisions(id), selection TEXT NOT NULL CHECK(selection IN ('low','base','high','custom','rejected')), controlling_source TEXT NOT NULL, context_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(review_decision_id));
CREATE TRIGGER IF NOT EXISTS assumption_decision_context_no_update BEFORE UPDATE ON assumption_decision_context BEGIN SELECT RAISE(ABORT, 'assumption decision context is append-only'); END;
CREATE TRIGGER IF NOT EXISTS assumption_decision_context_no_delete BEFORE DELETE ON assumption_decision_context BEGIN SELECT RAISE(ABORT, 'assumption decision context is retained'); END;
CREATE TABLE IF NOT EXISTS manual_assumptions(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), field_name TEXT NOT NULL, proposed_value TEXT NOT NULL, unit TEXT, currency TEXT, rationale TEXT NOT NULL, review_status TEXT NOT NULL CHECK(review_status IN ('needs_review','approved','rejected','superseded')), reviewer_id TEXT REFERENCES users(id), reviewed_at TEXT, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_decisions(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), actor_id TEXT NOT NULL REFERENCES users(id), entity_type TEXT NOT NULL CHECK(entity_type IN ('extracted_value','manual_assumption')), entity_id TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('approved','rejected','needs_review')), proposed_normalized_value TEXT, comments TEXT NOT NULL, previous_hash TEXT, decision_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS review_decisions_no_update BEFORE UPDATE ON review_decisions BEGIN SELECT RAISE(ABORT, 'review decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete BEFORE DELETE ON review_decisions BEGIN SELECT RAISE(ABORT, 'review decisions are append-only'); END;
CREATE TABLE IF NOT EXISTS reconciliation_runs(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), actor_id TEXT NOT NULL REFERENCES users(id), rule_engine_version TEXT NOT NULL, input_sha256 TEXT NOT NULL, finding_count INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS reconciliation_runs_no_update BEFORE UPDATE ON reconciliation_runs BEGIN SELECT RAISE(ABORT, 'reconciliation runs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS reconciliation_runs_no_delete BEFORE DELETE ON reconciliation_runs BEGIN SELECT RAISE(ABORT, 'reconciliation runs are append-only'); END;
CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), rule_code TEXT NOT NULL, severity TEXT NOT NULL, explanation TEXT NOT NULL, compared_values_json TEXT NOT NULL, source_documents_json TEXT NOT NULL, page_references_json TEXT NOT NULL, suggested_next_step TEXT NOT NULL, resolution_status TEXT NOT NULL CHECK(resolution_status IN ('open','resolved','superseded')), resolution_notes TEXT, created_at TEXT NOT NULL, reconciliation_run_id TEXT REFERENCES reconciliation_runs(id), superseded_at TEXT);
CREATE TRIGGER IF NOT EXISTS findings_no_delete BEFORE DELETE ON findings BEGIN SELECT RAISE(ABORT, 'findings are retained for reconciliation history'); END;
CREATE TABLE IF NOT EXISTS export_artifacts(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), kind TEXT NOT NULL CHECK(kind IN ('test1','test2','memo')), version INTEGER NOT NULL CHECK(version > 0), schema_version TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, approval_snapshot_json TEXT NOT NULL, approval_snapshot_sha256 TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(deal_id,kind,version));
CREATE TRIGGER IF NOT EXISTS export_artifacts_no_update BEFORE UPDATE ON export_artifacts BEGIN SELECT RAISE(ABORT, 'export artifacts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS export_artifacts_no_delete BEFORE DELETE ON export_artifacts BEGIN SELECT RAISE(ABORT, 'export artifacts are append-only'); END;
CREATE TABLE IF NOT EXISTS opportunity_runs(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), schema_version TEXT NOT NULL, policy_version TEXT NOT NULL, analysis_as_of TEXT NOT NULL, input_sha256 TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('research_candidate','analyst_approved','rejected')), created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(organization_id,deal_id,content_sha256));
CREATE TRIGGER IF NOT EXISTS opportunity_runs_no_update BEFORE UPDATE ON opportunity_runs BEGIN SELECT RAISE(ABORT, 'opportunity runs are immutable research evidence'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_runs_no_delete BEFORE DELETE ON opportunity_runs BEGIN SELECT RAISE(ABORT, 'opportunity runs are retained evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_runs_deal ON opportunity_runs(organization_id,deal_id,created_at);
CREATE TABLE IF NOT EXISTS opportunity_decisions(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), opportunity_run_id TEXT NOT NULL REFERENCES opportunity_runs(id), actor_id TEXT NOT NULL REFERENCES users(id), decision TEXT NOT NULL CHECK(decision IN ('approved','rejected','changes_requested')), rationale TEXT NOT NULL, acknowledgements_json TEXT NOT NULL, modifications_json TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, previous_hash TEXT, decision_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS opportunity_decisions_no_update BEFORE UPDATE ON opportunity_decisions BEGIN SELECT RAISE(ABORT, 'opportunity decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_decisions_no_delete BEFORE DELETE ON opportunity_decisions BEGIN SELECT RAISE(ABORT, 'opportunity decisions are retained governance evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_decisions_run ON opportunity_decisions(organization_id,opportunity_run_id,created_at);
CREATE TABLE IF NOT EXISTS opportunity_handoffs(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), opportunity_run_id TEXT NOT NULL REFERENCES opportunity_runs(id), opportunity_decision_id TEXT NOT NULL REFERENCES opportunity_decisions(id), version INTEGER NOT NULL CHECK(version > 0), schema_version TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(deal_id,opportunity_run_id,version));
CREATE TRIGGER IF NOT EXISTS opportunity_handoffs_no_update BEFORE UPDATE ON opportunity_handoffs BEGIN SELECT RAISE(ABORT, 'opportunity handoffs are immutable advisory evidence'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_handoffs_no_delete BEFORE DELETE ON opportunity_handoffs BEGIN SELECT RAISE(ABORT, 'opportunity handoffs are retained evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_handoffs_deal ON opportunity_handoffs(organization_id,deal_id,created_at);
CREATE TABLE IF NOT EXISTS opportunity_candidates(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT REFERENCES deals(id), created_by TEXT NOT NULL REFERENCES users(id), property_type TEXT NOT NULL, display_name TEXT, address TEXT, normalized_address_sha256 TEXT, market TEXT, submarket TEXT, status TEXT NOT NULL CHECK(status IN ('candidate','promoted_to_diligence','archived')), origin_type TEXT NOT NULL CHECK(origin_type IN ('manual','authorized_csv','existing_deal','test1_handoff')), created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS opportunity_candidates_list ON opportunity_candidates(organization_id,status,property_type,created_at);
CREATE INDEX IF NOT EXISTS opportunity_candidates_address ON opportunity_candidates(organization_id,normalized_address_sha256);
CREATE TABLE IF NOT EXISTS opportunity_candidate_versions(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), candidate_id TEXT NOT NULL REFERENCES opportunity_candidates(id), version INTEGER NOT NULL CHECK(version > 0), schema_version TEXT NOT NULL, analysis_as_of TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(candidate_id,version), UNIQUE(organization_id,candidate_id,content_sha256));
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_versions_no_update BEFORE UPDATE ON opportunity_candidate_versions BEGIN SELECT RAISE(ABORT, 'opportunity candidate versions are immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_versions_no_delete BEFORE DELETE ON opportunity_candidate_versions BEGIN SELECT RAISE(ABORT, 'opportunity candidate versions are retained evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_candidate_versions_candidate ON opportunity_candidate_versions(organization_id,candidate_id,version);
CREATE TABLE IF NOT EXISTS opportunity_screening_runs(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), candidate_id TEXT NOT NULL REFERENCES opportunity_candidates(id), candidate_version_id TEXT NOT NULL REFERENCES opportunity_candidate_versions(id), policy_id TEXT NOT NULL, policy_version TEXT NOT NULL, policy_sha256 TEXT NOT NULL, input_snapshot_sha256 TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, screening_tier TEXT NOT NULL CHECK(screening_tier IN ('HIGH_PRIORITY_REVIEW','WORTH_REVIEWING','LOW_PRIORITY','INSUFFICIENT_EVIDENCE')), result_json TEXT NOT NULL, result_sha256 TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), evaluated_at TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS opportunity_screening_runs_no_update BEFORE UPDATE ON opportunity_screening_runs BEGIN SELECT RAISE(ABORT, 'opportunity screening runs are immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_screening_runs_no_delete BEFORE DELETE ON opportunity_screening_runs BEGIN SELECT RAISE(ABORT, 'opportunity screening runs are retained evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_screening_runs_candidate ON opportunity_screening_runs(organization_id,candidate_id,evaluated_at);
CREATE TABLE IF NOT EXISTS opportunity_candidate_review_artifacts(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), candidate_id TEXT NOT NULL REFERENCES opportunity_candidates(id), candidate_version_id TEXT NOT NULL REFERENCES opportunity_candidate_versions(id), screening_run_id TEXT NOT NULL REFERENCES opportunity_screening_runs(id), schema_version TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(organization_id,screening_run_id));
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_review_artifacts_no_update BEFORE UPDATE ON opportunity_candidate_review_artifacts BEGIN SELECT RAISE(ABORT, 'candidate review artifacts are immutable evidence'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_review_artifacts_no_delete BEFORE DELETE ON opportunity_candidate_review_artifacts BEGIN SELECT RAISE(ABORT, 'candidate review artifacts are retained evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_candidate_review_artifacts_list ON opportunity_candidate_review_artifacts(organization_id,candidate_id,created_at);
CREATE TABLE IF NOT EXISTS opportunity_candidate_review_decisions(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), artifact_id TEXT NOT NULL REFERENCES opportunity_candidate_review_artifacts(id), actor_id TEXT NOT NULL REFERENCES users(id), decision TEXT NOT NULL CHECK(decision IN ('approved','rejected','changes_requested')), rationale TEXT NOT NULL, acknowledgements_json TEXT NOT NULL, modifications_json TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, previous_hash TEXT, decision_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_review_decisions_no_update BEFORE UPDATE ON opportunity_candidate_review_decisions BEGIN SELECT RAISE(ABORT, 'candidate review decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_review_decisions_no_delete BEFORE DELETE ON opportunity_candidate_review_decisions BEGIN SELECT RAISE(ABORT, 'candidate review decisions are retained governance evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_candidate_review_decisions_artifact ON opportunity_candidate_review_decisions(organization_id,artifact_id,created_at);
CREATE TABLE IF NOT EXISTS opportunity_candidate_promotions(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), candidate_id TEXT NOT NULL REFERENCES opportunity_candidates(id), artifact_id TEXT NOT NULL REFERENCES opportunity_candidate_review_artifacts(id), decision_id TEXT NOT NULL REFERENCES opportunity_candidate_review_decisions(id), deal_id TEXT NOT NULL REFERENCES deals(id), schema_version TEXT NOT NULL, content_json TEXT NOT NULL, content_sha256 TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(organization_id,candidate_id), UNIQUE(organization_id,deal_id));
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_promotions_no_update BEFORE UPDATE ON opportunity_candidate_promotions BEGIN SELECT RAISE(ABORT, 'candidate promotions are immutable lifecycle evidence'); END;
CREATE TRIGGER IF NOT EXISTS opportunity_candidate_promotions_no_delete BEFORE DELETE ON opportunity_candidate_promotions BEGIN SELECT RAISE(ABORT, 'candidate promotions are retained lifecycle evidence'); END;
CREATE INDEX IF NOT EXISTS opportunity_candidate_promotions_candidate ON opportunity_candidate_promotions(organization_id,candidate_id,created_at);
CREATE TABLE IF NOT EXISTS creos_entity_links(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), entity_kind TEXT NOT NULL CHECK(entity_kind IN ('property','deal','market','assumption','source','provenance','handoff')), local_record_type TEXT NOT NULL, local_record_id TEXT NOT NULL, creos_ulid TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(organization_id,entity_kind,local_record_type,local_record_id), UNIQUE(organization_id,creos_ulid));
CREATE TRIGGER IF NOT EXISTS creos_entity_links_no_update BEFORE UPDATE ON creos_entity_links BEGIN SELECT RAISE(ABORT, 'CREOS entity links are immutable identity evidence'); END;
CREATE TRIGGER IF NOT EXISTS creos_entity_links_no_delete BEFORE DELETE ON creos_entity_links BEGIN SELECT RAISE(ABORT, 'CREOS entity links are retained identity evidence'); END;
CREATE INDEX IF NOT EXISTS creos_entity_links_local ON creos_entity_links(organization_id,local_record_type,local_record_id);
CREATE TABLE IF NOT EXISTS audit_events(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT, actor_id TEXT REFERENCES users(id), action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT, details_json TEXT NOT NULL, previous_hash TEXT, event_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}")
            connection.executescript(SCHEMA)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
            if columns and "token_hash" not in columns:
                # Sessions are deliberately ephemeral; invalidate legacy plaintext-token sessions.
                connection.execute("DROP TABLE sessions")
                connection.execute("CREATE TABLE sessions(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, csrf_token TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL, created_at TEXT NOT NULL)")
            finding_columns = {row[1] for row in connection.execute("PRAGMA table_info(findings)")}
            if "reconciliation_run_id" not in finding_columns:
                connection.execute("ALTER TABLE findings ADD COLUMN reconciliation_run_id TEXT REFERENCES reconciliation_runs(id)")
            if "superseded_at" not in finding_columns:
                connection.execute("ALTER TABLE findings ADD COLUMN superseded_at TEXT")
            document_columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
            if "original_purged_at" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN original_purged_at TEXT")
            if "original_purged_by" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN original_purged_by TEXT REFERENCES users(id)")
            if "original_purge_reason" not in document_columns:
                connection.execute("ALTER TABLE documents ADD COLUMN original_purge_reason TEXT")
            semantic_columns = {row[1] for row in connection.execute("PRAGMA table_info(semantic_entities)")}
            if semantic_columns and "source_page" not in semantic_columns:
                connection.execute("DROP TRIGGER IF EXISTS semantic_entities_no_update")
                connection.execute("DROP TRIGGER IF EXISTS semantic_entities_no_delete")
                connection.execute("ALTER TABLE semantic_entities RENAME TO semantic_entities_v4")
                connection.execute("CREATE TABLE semantic_entities(id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id), deal_id TEXT NOT NULL REFERENCES deals(id), document_id TEXT NOT NULL REFERENCES documents(id), document_version INTEGER NOT NULL, document_category TEXT NOT NULL, entity_type TEXT NOT NULL CHECK(entity_type IN ('rent_roll_record','operating_account_period','lease_schedule_record','debt_term_record')), source_page INTEGER NOT NULL DEFAULT 1, source_row INTEGER NOT NULL, data_json TEXT NOT NULL, data_sha256 TEXT NOT NULL, source_value_ids_json TEXT NOT NULL, extractor_version TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(document_id,document_version,entity_type,source_page,source_row))")
                connection.execute("INSERT INTO semantic_entities(id,organization_id,deal_id,document_id,document_version,document_category,entity_type,source_page,source_row,data_json,data_sha256,source_value_ids_json,extractor_version,created_at) SELECT id,organization_id,deal_id,document_id,document_version,document_category,entity_type,1,source_row,data_json,data_sha256,source_value_ids_json,extractor_version,created_at FROM semantic_entities_v4")
                connection.execute("DROP TABLE semantic_entities_v4")
                connection.execute("CREATE TRIGGER semantic_entities_no_update BEFORE UPDATE ON semantic_entities BEGIN SELECT RAISE(ABORT, 'semantic entities are immutable derived evidence'); END")
                connection.execute("CREATE TRIGGER semantic_entities_no_delete BEFORE DELETE ON semantic_entities BEGIN SELECT RAISE(ABORT, 'semantic entities are retained evidence'); END")
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.create_function("decimal_gte", 2, _decimal_gte, deterministic=True)
        connection.create_function("decimal_lte", 2, _decimal_lte, deterministic=True)
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

    def verify_review_chain(self, organization_id: str) -> tuple[bool, str | None]:
        import hashlib
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM review_decisions WHERE organization_id=? ORDER BY rowid", (organization_id,)).fetchall()
        previous = None
        for row in rows:
            payload = json.dumps({
                "id": row["id"], "organization_id": row["organization_id"],
                "deal_id": row["deal_id"], "actor_id": row["actor_id"],
                "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                "decision": row["decision"],
                "proposed_normalized_value": row["proposed_normalized_value"],
                "comments": row["comments"], "previous": previous,
                "created_at": row["created_at"],
            }, sort_keys=True)
            if row["previous_hash"] != previous or row["decision_hash"] != hashlib.sha256(payload.encode()).hexdigest():
                return False, row["id"]
            previous = row["decision_hash"]
        return True, None

    def health(self) -> dict:
        with self.connect() as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        return {
            "quickCheck": quick_check,
            "foreignKeyErrors": len(foreign_key_errors),
            "schemaVersion": version,
            "supportedSchemaVersion": SCHEMA_VERSION,
            "schemaCurrent": version == SCHEMA_VERSION,
            "ok": quick_check == "ok" and not foreign_key_errors and version == SCHEMA_VERSION,
        }
