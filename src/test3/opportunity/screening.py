"""Deterministic, evidence-linked screening for Opportunity Finder candidates.

Screening tiers are workflow priorities.  They are deliberately distinct from
the statistically validated opportunity score governed by ``scoring.py``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hashlib
import json
from typing import Mapping, Sequence

from .scoring import current_score_status


SCREENING_SCHEMA_VERSION = "test3-opportunity-screening-result/1.0.0"
DIMENSIONS = ("rent", "basis", "noi", "cap_rate", "vacancy", "comparables", "location")


class OpportunityScreeningTier(StrEnum):
    HIGH_PRIORITY_REVIEW = "HIGH_PRIORITY_REVIEW"
    WORTH_REVIEWING = "WORTH_REVIEWING"
    LOW_PRIORITY = "LOW_PRIORITY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class OpportunityScreeningPolicy:
    """Versioned rules for prioritizing analyst review, never investment advice."""

    policy_id: str = "opportunity-finder-deterministic-screening"
    version: str = "1.0.0"
    minimum_complete_dimensions: int = 3
    high_priority_minimum_dimensions: int = 5
    high_priority_minimum_signals: int = 2
    minimum_relevant_comps: int = 3
    rent_gap_review_threshold: Decimal = Decimal("0.05")
    rent_gap_high_threshold: Decimal = Decimal("0.10")
    basis_discount_review_threshold: Decimal = Decimal("0.05")
    basis_discount_high_threshold: Decimal = Decimal("0.075")
    noi_upside_review_threshold: Decimal = Decimal("0")
    noi_upside_high_ratio: Decimal = Decimal("0.05")
    cap_rate_spread_review_bps: Decimal = Decimal("25")
    cap_rate_spread_high_bps: Decimal = Decimal("50")
    vacancy_delta_review_threshold: Decimal = Decimal("0.01")
    vacancy_delta_high_threshold: Decimal = Decimal("0.02")
    current_evidence_maximum_age_days: int = 365
    stale_evidence_warning_days: int = 365

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_complete_dimensions <= len(DIMENSIONS):
            raise ValueError("minimum_complete_dimensions is outside the governed dimension count")
        if not self.minimum_complete_dimensions <= self.high_priority_minimum_dimensions <= len(DIMENSIONS):
            raise ValueError("high_priority_minimum_dimensions must meet the minimum and governed dimension count")
        if self.high_priority_minimum_signals < 1 or self.minimum_relevant_comps < 1:
            raise ValueError("signal and comparable minimums must be positive")
        if self.current_evidence_maximum_age_days < 1 or self.stale_evidence_warning_days < 1:
            raise ValueError("evidence age thresholds must be positive")

    @property
    def content_hash(self) -> str:
        return _hash(_canonical(asdict(self)))


DEFAULT_SCREENING_POLICY = OpportunityScreeningPolicy()


@dataclass(frozen=True)
class OpportunityScreeningInput:
    candidate_id: str
    property_type: str
    analysis_as_of: date
    subject_rent: Decimal | None = None
    market_rent: Decimal | None = None
    rent_unit: str | None = None
    acquisition_basis: Decimal | None = None
    comparable_sale_basis: Decimal | None = None
    basis_unit: str | None = None
    current_noi: Decimal | None = None
    stabilized_noi: Decimal | None = None
    subject_cap_rate: Decimal | None = None
    market_cap_rate: Decimal | None = None
    subject_vacancy: Decimal | None = None
    market_vacancy: Decimal | None = None
    rent_comp_count: int | None = None
    sale_comp_count: int | None = None
    location_evidence_complete: bool | None = None
    renovation_budget_verified: bool | None = None
    insurance_evidence_date: date | None = None
    evidence_hashes: Mapping[str, Sequence[str]] = field(default_factory=dict)
    evidence_dates: Mapping[str, date] = field(default_factory=dict)


@dataclass(frozen=True)
class OpportunityReason:
    code: str
    statement: str
    dimension: str
    value: str | None = None
    threshold: str | None = None
    evidence_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpportunityWarning:
    code: str
    statement: str
    dimension: str | None = None


@dataclass(frozen=True)
class OpportunityScreeningResult:
    screening_tier: OpportunityScreeningTier
    reasons: tuple[OpportunityReason, ...]
    warnings: tuple[OpportunityWarning, ...]
    evidence_completeness: Decimal
    evidence_freshness_days: int | None
    evidence_freshness_detail: Mapping[str, object]
    input_snapshot_hash: str
    evidence_hash: str
    policy_id: str
    policy_version: str
    policy_hash: str
    evaluated_at: datetime
    derived_metrics: Mapping[str, str | None]
    validated_opportunity_score: Mapping[str, object]
    result_hash: str

    def to_dict(self) -> dict:
        return {
            "schemaVersion": SCREENING_SCHEMA_VERSION,
            "screeningTier": self.screening_tier.value,
            "screeningTierMeaning": "deterministic_analyst_review_priority_not_investment_recommendation",
            "reasons": [_canonical(asdict(item)) for item in self.reasons],
            "warnings": [_canonical(asdict(item)) for item in self.warnings],
            "evidenceCompleteness": format(self.evidence_completeness, "f"),
            "evidenceFreshnessDays": self.evidence_freshness_days,
            "evidenceFreshnessDetail": _canonical(self.evidence_freshness_detail),
            "inputSnapshotHash": self.input_snapshot_hash,
            "evidenceHash": self.evidence_hash,
            "policyId": self.policy_id,
            "policyVersion": self.policy_version,
            "policyHash": self.policy_hash,
            "evaluatedAt": self.evaluated_at.astimezone(timezone.utc).isoformat(),
            "derivedMetrics": dict(self.derived_metrics),
            "validatedOpportunityScore": dict(self.validated_opportunity_score),
            "automaticUnderwritingApply": False,
            "resultHash": self.result_hash,
        }


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _hash(value: object) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decimal(value: Decimal | None, field_name: str, *, rate: bool = False) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field_name} must be a finite non-negative decimal")
    if rate and result > 1:
        raise ValueError(f"{field_name} must be a decimal fraction no greater than 1")
    return result


def calculate_screening_metrics(value: OpportunityScreeningInput) -> dict[str, Decimal | None]:
    """Calculate exact screening metrics without substituting missing values."""
    subject_rent = _decimal(value.subject_rent, "subject_rent")
    market_rent = _decimal(value.market_rent, "market_rent")
    acquisition_basis = _decimal(value.acquisition_basis, "acquisition_basis")
    comparable_basis = _decimal(value.comparable_sale_basis, "comparable_sale_basis")
    current_noi = _decimal(value.current_noi, "current_noi")
    stabilized_noi = _decimal(value.stabilized_noi, "stabilized_noi")
    subject_cap = _decimal(value.subject_cap_rate, "subject_cap_rate", rate=True)
    market_cap = _decimal(value.market_cap_rate, "market_cap_rate", rate=True)
    subject_vacancy = _decimal(value.subject_vacancy, "subject_vacancy", rate=True)
    market_vacancy = _decimal(value.market_vacancy, "market_vacancy", rate=True)
    if (subject_rent is None) != (market_rent is None):
        rent_gap = None
    elif subject_rent is not None:
        if not value.rent_unit or market_rent == 0:
            raise ValueError("rent comparison requires an explicit common unit and non-zero market rent")
        rent_gap = (market_rent - subject_rent) / market_rent
    else:
        rent_gap = None
    if (acquisition_basis is None) != (comparable_basis is None):
        basis_discount = None
    elif acquisition_basis is not None:
        if not value.basis_unit or comparable_basis == 0:
            raise ValueError("basis comparison requires an explicit common unit and non-zero comparable basis")
        basis_discount = (comparable_basis - acquisition_basis) / comparable_basis
    else:
        basis_discount = None
    noi_upside = stabilized_noi - current_noi if current_noi is not None and stabilized_noi is not None else None
    noi_upside_ratio = (noi_upside / current_noi if noi_upside is not None and current_noi != 0 else None)
    cap_spread_bps = ((subject_cap - market_cap) * Decimal("10000")
                      if subject_cap is not None and market_cap is not None else None)
    vacancy_delta = (subject_vacancy - market_vacancy
                     if subject_vacancy is not None and market_vacancy is not None else None)
    return {
        "rentGapPct": rent_gap,
        "basisDiscountPct": basis_discount,
        "noiUpside": noi_upside,
        "noiUpsideRatio": noi_upside_ratio,
        "capRateSpreadBps": cap_spread_bps,
        "vacancyDelta": vacancy_delta,
    }


def _valid_hashes(value: OpportunityScreeningInput, dimension: str) -> tuple[str, ...]:
    hashes = tuple(sorted(str(item).lower() for item in value.evidence_hashes.get(dimension, ())))
    if any(len(item) != 64 or any(character not in "0123456789abcdef" for character in item) for item in hashes):
        raise ValueError(f"{dimension} evidence contains an invalid SHA-256")
    return hashes


def _available_dimensions(value: OpportunityScreeningInput, metrics: Mapping[str, Decimal | None]) -> dict[str, bool]:
    return {
        "rent": metrics["rentGapPct"] is not None,
        "basis": metrics["basisDiscountPct"] is not None,
        "noi": metrics["noiUpside"] is not None,
        "cap_rate": metrics["capRateSpreadBps"] is not None,
        "vacancy": metrics["vacancyDelta"] is not None,
        "comparables": value.rent_comp_count is not None or value.sale_comp_count is not None,
        "location": value.location_evidence_complete is True,
    }


def screen_opportunity(value: OpportunityScreeningInput, *, policy: OpportunityScreeningPolicy = DEFAULT_SCREENING_POLICY,
                       evaluated_at: datetime | None = None) -> OpportunityScreeningResult:
    """Classify an evidence snapshot for review using transparent, deterministic rules."""
    if not value.candidate_id.strip() or not value.property_type.strip():
        raise ValueError("candidate_id and property_type are required")
    if value.rent_comp_count is not None and value.rent_comp_count < 0:
        raise ValueError("rent_comp_count cannot be negative")
    if value.sale_comp_count is not None and value.sale_comp_count < 0:
        raise ValueError("sale_comp_count cannot be negative")
    evaluated = evaluated_at or datetime.now(timezone.utc)
    if evaluated.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    if value.analysis_as_of > evaluated.astimezone(timezone.utc).date():
        raise ValueError("analysis_as_of cannot be after the screening evaluation date")
    metrics = calculate_screening_metrics(value)
    available = _available_dimensions(value, metrics)
    warnings: list[OpportunityWarning] = []
    governed_dimensions: list[str] = []
    all_hashes: dict[str, tuple[str, ...]] = {}
    ages: list[int] = []
    evidence_age_by_dimension: dict[str, int | None] = {dimension: None for dimension in DIMENSIONS}
    for dimension in DIMENSIONS:
        hashes = _valid_hashes(value, dimension)
        all_hashes[dimension] = hashes
        if not available[dimension]:
            warnings.append(OpportunityWarning("MISSING_EVIDENCE_DIMENSION", f"No usable {dimension.replace('_', ' ')} evidence was supplied.", dimension))
            continue
        observed = value.evidence_dates.get(dimension)
        if not hashes:
            warnings.append(OpportunityWarning("EVIDENCE_LINEAGE_MISSING", f"{dimension.replace('_', ' ').title()} evidence lacks source hashes and is excluded from completeness.", dimension))
            continue
        if observed is None:
            warnings.append(OpportunityWarning("EVIDENCE_DATE_MISSING", f"{dimension.replace('_', ' ').title()} evidence lacks an evidence date and is excluded from completeness.", dimension))
            continue
        if observed > value.analysis_as_of:
            raise ValueError(f"{dimension} evidence is dated after the analysis date")
        ages.append((value.analysis_as_of - observed).days)
        evidence_age_by_dimension[dimension] = ages[-1]
        governed_dimensions.append(dimension)
    completeness = (Decimal(len(governed_dimensions)) / Decimal(len(DIMENSIONS))).quantize(Decimal("0.0001"))
    freshness = max(ages) if ages else None
    sorted_ages = sorted(ages)
    if not sorted_ages:
        median_age: Decimal | None = None
    elif len(sorted_ages) % 2:
        median_age = Decimal(sorted_ages[len(sorted_ages) // 2])
    else:
        middle = len(sorted_ages) // 2
        median_age = (Decimal(sorted_ages[middle - 1]) + Decimal(sorted_ages[middle])) / Decimal("2")
    signal_ages = [evidence_age_by_dimension[item] for item in ("rent", "basis", "noi", "cap_rate", "vacancy")
                   if evidence_age_by_dimension[item] is not None]
    freshness_detail = {
        "oldestEvidenceAgeDays": freshness,
        "newestEvidenceAgeDays": min(ages) if ages else None,
        "medianEvidenceAgeDays": median_age,
        "signalEvidenceMaxAgeDays": max(signal_ages) if signal_ages else None,
        "evidenceAgeByDimension": evidence_age_by_dimension,
    }
    if freshness is not None and freshness > policy.stale_evidence_warning_days:
        warnings.append(OpportunityWarning("STALE_EVIDENCE", f"At least one relied-upon evidence dimension is {freshness} days old."))
    if value.renovation_budget_verified is False:
        warnings.append(OpportunityWarning("RENOVATION_BUDGET_NOT_VERIFIED", "Renovation budget evidence is not independently verified.", "noi"))
    if value.insurance_evidence_date is not None:
        if value.insurance_evidence_date > value.analysis_as_of:
            raise ValueError("insurance evidence is dated after the analysis date")
        insurance_age = (value.analysis_as_of - value.insurance_evidence_date).days
        if insurance_age > 365:
            warnings.append(OpportunityWarning("INSURANCE_EVIDENCE_STALE", f"Insurance evidence is {insurance_age} days old."))

    reasons: list[OpportunityReason] = []
    high_signals = 0
    signal_count = 0

    def add_reason(code: str, statement: str, dimension: str, metric: Decimal, threshold: Decimal, *, high: bool) -> None:
        nonlocal high_signals, signal_count
        if dimension not in governed_dimensions:
            return
        reasons.append(OpportunityReason(code, statement, dimension, format(metric, "f"), format(threshold, "f"), all_hashes[dimension]))
        signal_count += 1
        if high:
            high_signals += 1

    rent_gap = metrics["rentGapPct"]
    if rent_gap is not None and rent_gap >= policy.rent_gap_review_threshold:
        add_reason("SUBJECT_RENT_BELOW_MARKET", "Subject rent is below the source-linked market-rent evidence.", "rent", rent_gap,
                   policy.rent_gap_review_threshold, high=rent_gap >= policy.rent_gap_high_threshold)
    basis_discount = metrics["basisDiscountPct"]
    if basis_discount is not None and basis_discount >= policy.basis_discount_review_threshold:
        add_reason("BASIS_BELOW_COMPARABLES", "Acquisition basis is below the source-linked comparable-sale basis.", "basis", basis_discount,
                   policy.basis_discount_review_threshold, high=basis_discount >= policy.basis_discount_high_threshold)
    noi_upside = metrics["noiUpside"]
    noi_ratio = metrics["noiUpsideRatio"]
    if noi_upside is not None and noi_upside > policy.noi_upside_review_threshold:
        add_reason("POSITIVE_NOI_DELTA", "Source-linked stabilized NOI exceeds current NOI.", "noi", noi_upside,
                   policy.noi_upside_review_threshold, high=noi_ratio is not None and noi_ratio >= policy.noi_upside_high_ratio)
    cap_spread = metrics["capRateSpreadBps"]
    if cap_spread is not None and cap_spread >= policy.cap_rate_spread_review_bps:
        add_reason("POSITIVE_CAP_RATE_SPREAD", "Subject cap rate exceeds the source-linked market context.", "cap_rate", cap_spread,
                   policy.cap_rate_spread_review_bps, high=cap_spread >= policy.cap_rate_spread_high_bps)
    vacancy_delta = metrics["vacancyDelta"]
    if vacancy_delta is not None and vacancy_delta >= policy.vacancy_delta_review_threshold:
        add_reason("VACANCY_NORMALIZATION_POTENTIAL", "Subject vacancy exceeds source-linked market vacancy.", "vacancy", vacancy_delta,
                   policy.vacancy_delta_review_threshold, high=vacancy_delta >= policy.vacancy_delta_high_threshold)

    relevant_comp_count = (value.rent_comp_count or 0) + (value.sale_comp_count or 0)
    if "comparables" in governed_dimensions and relevant_comp_count >= policy.minimum_relevant_comps:
        reasons.append(OpportunityReason("COMPARABLE_SUPPORT", "The candidate has enough source-linked comparable observations for screening review.",
                                         "comparables", str(relevant_comp_count), str(policy.minimum_relevant_comps), all_hashes["comparables"]))
    elif available["comparables"]:
        warnings.append(OpportunityWarning("COMPARABLE_SUPPORT_BELOW_MINIMUM", f"Only {relevant_comp_count} relevant comparable observations are available.", "comparables"))

    required_signal_dimensions = {"rent", "basis", "noi", "cap_rate", "vacancy"}
    signal_evidence_available = bool(required_signal_dimensions.intersection(governed_dimensions))
    current_enough = freshness is not None and freshness <= policy.current_evidence_maximum_age_days
    enough_dimensions = len(governed_dimensions) >= policy.minimum_complete_dimensions
    if not enough_dimensions or not signal_evidence_available:
        tier = OpportunityScreeningTier.INSUFFICIENT_EVIDENCE
    elif (len(governed_dimensions) >= policy.high_priority_minimum_dimensions
          and high_signals >= policy.high_priority_minimum_signals and current_enough
          and "comparables" in governed_dimensions
          and relevant_comp_count >= policy.minimum_relevant_comps):
        tier = OpportunityScreeningTier.HIGH_PRIORITY_REVIEW
    elif signal_count and current_enough:
        tier = OpportunityScreeningTier.WORTH_REVIEWING
    else:
        tier = OpportunityScreeningTier.LOW_PRIORITY

    if tier == OpportunityScreeningTier.INSUFFICIENT_EVIDENCE:
        warnings.append(OpportunityWarning("INSUFFICIENT_EVIDENCE_FOR_SCREENING", "The governed evidence does not support a substantive review-priority classification."))
    score_status = current_score_status()
    metric_strings = {key: format(item, "f") if item is not None else None for key, item in metrics.items()}
    snapshot = {
        "candidateId": value.candidate_id,
        "propertyType": value.property_type.lower(),
        "analysisAsOf": value.analysis_as_of.isoformat(),
        "inputs": _canonical(asdict(value)),
        "derivedMetrics": metric_strings,
        "policyHash": policy.content_hash,
    }
    input_hash = _hash(snapshot)
    evidence_hash = _hash({key: list(items) for key, items in all_hashes.items()})
    result_payload = {
        "schemaVersion": SCREENING_SCHEMA_VERSION,
        "tier": tier.value,
        "reasons": [_canonical(asdict(item)) for item in reasons],
        "warnings": [_canonical(asdict(item)) for item in warnings],
        "completeness": format(completeness, "f"),
        "freshness": freshness,
        "freshnessDetail": _canonical(freshness_detail),
        "inputHash": input_hash,
        "evidenceHash": evidence_hash,
        "policyHash": policy.content_hash,
        "evaluatedAt": evaluated.astimezone(timezone.utc).isoformat(),
        "scoreStatus": score_status,
    }
    return OpportunityScreeningResult(
        screening_tier=tier,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        evidence_completeness=completeness,
        evidence_freshness_days=freshness,
        evidence_freshness_detail=freshness_detail,
        input_snapshot_hash=input_hash,
        evidence_hash=evidence_hash,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_hash=policy.content_hash,
        evaluated_at=evaluated,
        derived_metrics=metric_strings,
        validated_opportunity_score=score_status,
        result_hash=_hash(result_payload),
    )
