from __future__ import annotations

from dataclasses import dataclass


TARGET_CLASSIFICATIONS = frozenset({"institutional_target", "market_proxy", "residential_proxy", "context_feature"})
ACCESS_METHODS = frozenset({"official_download", "manual_download", "local_file", "reviewed_document"})


@dataclass(frozen=True)
class CRETargetSourceSpec:
    source_id: str
    source_name: str
    source_class: str
    target_classification: str
    property_types: tuple[str, ...]
    metrics_available: tuple[str, ...]
    geographic_levels: tuple[str, ...]
    frequency: tuple[str, ...]
    history_available: str
    access_method: str
    source_url: str | None
    requires_login: bool
    requires_payment: bool
    automation_permitted: bool
    redistribution_permitted: str
    citation_requirements: str
    license_notes: str
    quality_tier: str
    status: str

    def __post_init__(self) -> None:
        if self.target_classification not in TARGET_CLASSIFICATIONS:
            raise ValueError("unsupported CRE target classification")
        if self.access_method not in ACCESS_METHODS:
            raise ValueError("unsupported CRE source access method")
        if self.requires_payment:
            raise ValueError("billable CRE sources cannot be approved")
        if self.redistribution_permitted not in {"yes", "no", "unknown"}:
            raise ValueError("redistribution status must be yes, no, or unknown")
        if self.status not in {"approved", "manual_review", "context_only", "rejected"}:
            raise ValueError("unsupported source status")
