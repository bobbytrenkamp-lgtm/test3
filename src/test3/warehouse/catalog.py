from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source: str
    dataset: str
    metrics: tuple[str, ...]
    geography_levels: tuple[str, ...]
    frequency: tuple[str, ...]
    first_available_date: str | None
    update_frequency: str
    licensing_notes: str
    refresh_method: str
    account_required: bool
    payment_method_required: bool
    required_key: bool
    can_become_billable: bool
    redistribution_permitted: bool | None
    transformation: str
    quality_caveats: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def _public(source_id: str, source: str, dataset: str, metrics: tuple[str, ...], geographies: tuple[str, ...], frequency: tuple[str, ...], first: str, update: str, license_note: str) -> SourceSpec:
    return SourceSpec(source_id, source, dataset, metrics, geographies, frequency, first, update, license_note,
                      "governed_official_https_or_validated_local_file", False, False, False, False, True,
                      "Source-specific normalization into canonical observation schema; original frequency retained.")


SOURCE_CATALOG = {
    spec.source_id: spec for spec in (
        _public("census_acs", "U.S. Census Bureau", "American Community Survey", ("population", "households", "income", "housing_units", "vacancy"), ("state", "county", "place"), ("annual",), "2005", "annual", "U.S. federal government data; verify table-specific notes."),
        _public("bls_laus_ces", "U.S. Bureau of Labor Statistics", "LAUS and CES", ("employment", "unemployment_rate", "labor_force", "industry_employment", "wages"), ("state", "county", "cbsa"), ("monthly", "annual"), "1976", "monthly", "U.S. federal government data; preserve series footnotes and revisions."),
        _public("bea_regional", "U.S. Bureau of Economic Analysis", "Regional accounts", ("gdp", "personal_income", "economic_output"), ("state", "county", "cbsa"), ("quarterly", "annual"), "1969", "quarterly", "U.S. federal government data; attribution requested."),
        _public("fred_public", "Federal Reserve Bank of St. Louis", "FRED public series", ("treasury_rate", "sofr", "fed_funds", "mortgage_rate", "inflation"), ("national",), ("daily", "monthly", "quarterly"), "1954", "varies", "Series rights vary; record each series' source and copyright notes."),
        _public("hud_public", "U.S. Department of Housing and Urban Development", "Public housing datasets", ("fair_market_rent", "affordability"), ("county", "metro", "zip"), ("annual",), "1983", "annual", "U.S. federal government data; verify dataset-specific terms."),
        _public("census_bps", "U.S. Census Bureau", "Building Permits Survey", ("permits", "units_authorized", "multifamily_permits"), ("state", "county", "place"), ("monthly", "annual"), "1980", "monthly", "U.S. federal government data."),
        SourceSpec("test1_local", "Test1", "Normalized local exports", ("geography", "zoning", "policy", "facilities"), ("state", "county", "place", "property"), ("irregular",), None, "user controlled", "User-owned local output; Test3 does not redistribute Test1 data.", "local_file", False, False, False, False, False, "Contract-validated local adapter; do not duplicate Test1 pipelines."),
        SourceSpec("test3_derived", "Test3", "Deterministic derived metrics", ("growth",), ("national", "state", "county", "cbsa", "place"), ("annual",), None, "after source refresh", "MIT-licensed Test3 transformation; inputs retain their own source terms.", "local_processing", False, False, False, False, True, "Versioned deterministic transformations with input observation IDs."),
        SourceSpec("user_import", "User-provided", "CRE market imports", ("rent", "rent_growth", "vacancy", "supply", "transactions", "expenses"), ("market", "submarket", "property"), ("monthly", "quarterly", "annual"), None, "user controlled", "Rights and redistribution status must be supplied for every import.", "local_file", False, False, False, False, None, "Saved mapping template plus row-level lineage; analyst approval required.", ("Quality depends on user-provided source and methodology.",)),
    )
}


def get_source(source_id: str) -> SourceSpec:
    try:
        return SOURCE_CATALOG[source_id]
    except KeyError as exc:
        raise ValueError(f"unknown governed source: {source_id}") from exc
