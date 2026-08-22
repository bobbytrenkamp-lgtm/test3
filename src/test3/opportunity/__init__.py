"""Local, evidence-first property acquisition screening."""

from .engine import analyze_property_opportunity
from .economics import economic_screen, normalize_economic_evidence
from .location import analyze_location_evidence, parse_location_evidence
from .sales import parse_sale_comps
from .scoring import current_score_status, promotion_decision, score_dataset_readiness
from .outcomes import approve_outcome_review, approved_outcome_readiness, prepare_outcome_review
from .screening import (
    DEFAULT_SCREENING_POLICY,
    SCREENING_POLICIES,
    OpportunityReason,
    OpportunityScreeningInput,
    OpportunityScreeningPolicy,
    OpportunityScreeningResult,
    OpportunityScreeningTier,
    OpportunityWarning,
    calculate_screening_metrics,
    registered_screening_policy,
    screen_opportunity,
)
from .persistence import (CANDIDATE_EVIDENCE_SCHEMA_VERSION, CANDIDATE_STATUSES, ORIGIN_TYPES,
                          PROPERTY_TYPES, canonical_json, normalize_evidence_payload,
                          normalized_address_hash, screening_input_from_snapshot, sha256_json)

__all__ = ["analyze_location_evidence", "analyze_property_opportunity", "economic_screen",
           "normalize_economic_evidence", "parse_location_evidence", "parse_sale_comps",
           "current_score_status", "promotion_decision", "score_dataset_readiness",
           "approve_outcome_review", "approved_outcome_readiness", "prepare_outcome_review",
           "DEFAULT_SCREENING_POLICY", "SCREENING_POLICIES", "OpportunityReason", "OpportunityScreeningInput",
           "OpportunityScreeningPolicy", "OpportunityScreeningResult", "OpportunityScreeningTier",
           "OpportunityWarning", "calculate_screening_metrics", "registered_screening_policy", "screen_opportunity"]
__all__ += ["CANDIDATE_EVIDENCE_SCHEMA_VERSION", "CANDIDATE_STATUSES", "ORIGIN_TYPES",
            "PROPERTY_TYPES", "canonical_json", "normalize_evidence_payload", "normalized_address_hash",
            "screening_input_from_snapshot", "sha256_json"]
