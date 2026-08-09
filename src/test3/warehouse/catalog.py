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
        _public("bls_laus_ces", "U.S. Bureau of Labor Statistics", "LAUS and QCEW", ("employment", "unemployment_rate", "labor_force", "covered_employment", "establishments", "wages", "pay"), ("national", "state", "county", "cbsa"), ("monthly", "annual"), "1975", "monthly/quarterly", "U.S. federal government data; preserve series IDs, disclosure status, footnotes and revisions."),
        _public("bea_regional", "U.S. Bureau of Economic Analysis", "Regional accounts", ("gdp", "personal_income", "economic_output"), ("state", "county", "cbsa"), ("quarterly", "annual"), "1969", "quarterly", "U.S. federal government data; attribution requested."),
        _public("fred_public", "Federal Reserve Bank of St. Louis", "FRED public series", ("treasury_rate", "sofr", "fed_funds", "mortgage_rate", "inflation", "cre_lending_standards", "cre_loan_demand", "cre_loan_delinquency", "cre_bank_loans"), ("national",), ("daily", "weekly", "monthly", "quarterly"), "1954", "varies", "Series rights vary; governed CRE additions are Federal Reserve Board public-domain series with citation requested."),
        _public("hud_public", "U.S. Department of Housing and Urban Development", "Fair Market Rent history", ("fair_market_rent",), ("county", "county_subdivision"), ("annual",), "1983", "annual", "U.S. federal government data; preserve fiscal year, bedroom count and HUD area definitions."),
        _public("census_hvs", "U.S. Census Bureau", "Housing Vacancy Survey historical tables", ("rental_vacancy_rate", "median_asking_rent_vacant_units"), ("national",), ("quarterly",), "1956", "quarterly", "U.S. federal government data; HVS residential measures are not institutional brokerage CRE metrics and historical tables do not provide real-time release vintages."),
        _public("census_cbsa_crosswalk", "U.S. Census Bureau / Office of Management and Budget", "Metropolitan and Micropolitan Delineation Files", ("county_cbsa_membership",), ("county", "cbsa"), ("irregular",), "2023-07-21", "when OMB revises delineations", "U.S. federal government data; preserve the OMB delineation vintage and effective date."),
        _public("census_bps", "U.S. Census Bureau", "Building Permits Survey", ("permits", "units_authorized", "multifamily_permits"), ("state", "county", "place"), ("monthly", "annual"), "1980", "monthly", "U.S. federal government data."),
        SourceSpec("test1_local", "Test1", "Normalized local exports", ("geography", "zoning", "policy", "facilities"), ("state", "county", "place", "property"), ("irregular",), None, "user controlled", "User-owned local output; Test3 does not redistribute Test1 data.", "local_file", False, False, False, False, False, "Contract-validated local adapter; do not duplicate Test1 pipelines."),
        SourceSpec("test3_derived", "Test3", "Deterministic derived metrics", ("growth",), ("national", "state", "county", "cbsa", "place"), ("annual",), None, "after source refresh", "MIT-licensed Test3 transformation; inputs retain their own source terms.", "local_processing", False, False, False, False, True, "Versioned deterministic transformations with input observation IDs."),
        SourceSpec("user_import", "User-provided", "CRE market imports", ("rent", "rent_growth", "vacancy", "supply", "transactions", "expenses"), ("market", "submarket", "property"), ("monthly", "quarterly", "annual"), None, "user controlled", "Rights and redistribution status must be supplied for every import.", "local_file", False, False, False, False, None, "Saved mapping template plus row-level lineage; analyst approval required.", ("Quality depends on user-provided source and methodology.",)),
    )
}

# Explicitly reviewed prior catalog contracts remain verifiable for immutable historical manifests.
# Never add a fingerprint here without reviewing the exact prior SourceSpec and documenting the change.
LEGACY_SOURCE_FINGERPRINTS = {
    "hud_public": frozenset({"8538dffbf9024742f0a04dd10929919fe744f9609221d059117b24abf7006e92"}),
    "fred_public": frozenset({"300f45bdff85f2eabda787fdf6d9b43fe68d26388445da0e3f4723a80eda009d"}),
}


def get_source(source_id: str) -> SourceSpec:
    try:
        return SOURCE_CATALOG[source_id]
    except KeyError as exc:
        raise ValueError(f"unknown governed source: {source_id}") from exc


def approved_source_fingerprints(source_id: str) -> frozenset[str]:
    return frozenset({get_source(source_id).fingerprint, *LEGACY_SOURCE_FINGERPRINTS.get(source_id, ())})
