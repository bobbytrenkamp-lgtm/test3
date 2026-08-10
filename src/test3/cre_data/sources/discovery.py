from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CRESourceCandidate:
    source_id: str
    source: str
    domain: str
    property_types: tuple[str, ...]
    metrics: tuple[str, ...]
    geography: str
    frequency: str
    history: str
    access: str
    automation: str
    redistribution: str
    citation: str
    license_notes: str
    classification: str
    recommended_ingestion: str
    scores: tuple[int, int, int, int, int, int, int, int, int]

    @property
    def acquisition_score(self) -> float:
        weights = (3, 2, 2, 2, 2, 2, 1, 2, 1)
        return round(sum(value * weight for value, weight in zip(self.scores, weights, strict=True)) / sum(weights), 2)


CANDIDATES = (
    CRESourceCandidate("user_owned_history", "Authorized user-owned brokerage/export history", "local",
        ("multifamily", "industrial", "office", "retail"),
        ("asking_rent", "effective_rent", "rent_growth_yoy", "vacancy_rate", "inventory", "deliveries", "net_absorption", "under_construction"),
        "market/submarket", "monthly/quarterly/annual", "source-dependent", "local lawful file", "local_only",
        "no redistribution assumed", "Record provider, file, period, and contractual citation terms.",
        "Rights depend on the analyst license; data stays local and ignored by Git.", "institutional_target", "bulk_local_import", (5,5,5,5,4,5,5,5,5)),
    CRESourceCandidate("sec_maa_same_store", "MAA SEC quarterly supplemental schedules", "sec.gov", ("multifamily",),
        ("effective_rent", "rent_growth_yoy", "occupancy_rate", "vacancy_rate"),
        "27 source-defined MAA markets", "quarterly", "2019-Q1 through 2026-Q2 acquired locally",
        "official SEC filing", "permitted_with_SEC_fair_access", "numeric facts local; filing text not redistributed",
        "Cite issuer, accession, Exhibit 99.2, filing date, table, market row, and retrieval date.",
        "MAA same-store portfolio markets are not CBSAs; analyst compatibility review remains mandatory.",
        "institutional_target", "acquired_local_review_required", (5,5,5,5,4,5,5,5,4)),
    CRESourceCandidate("berkadia_reports", "Berkadia Apartment Update market reports", "berkadia.com", ("multifamily",),
        ("rent", "occupancy", "supply", "demand"), "national and individual markets", "quarterly", "report-specific archive",
        "public report search/download", "manual_download_required", "unknown; do not redistribute report files",
        "Cite publisher, market, quarter, page/table, and retrieval date.",
        "Public download does not establish bulk automation or redistribution permission.", "institutional_target", "report_inbox_manual_review", (5,5,3,5,3,4,4,3,1)),
    CRESourceCandidate("colliers_reports", "Colliers public market reports", "colliers.com",
        ("multifamily", "industrial", "office", "retail"),
        ("asking_rent", "effective_rent", "rent_growth_yoy", "vacancy_rate", "inventory", "deliveries", "net_absorption", "under_construction"),
        "market/submarket; report-specific definition", "quarterly/annual", "varies by market", "public report page/PDF",
        "manual_download_required", "unknown; local numeric analysis only", "Cite report, market, period, page/table, and retrieval date.",
        "Some reports disclose methodology; automated archive collection is not approved.", "institutional_target", "report_inbox_manual_review", (5,4,4,4,4,4,4,3,1)),
    CRESourceCandidate("cbre_figures", "CBRE Multifamily Figures", "cbre.com", ("multifamily",),
        ("asking_rent", "rent_growth_yoy", "vacancy_rate", "net_absorption", "completions", "investment_volume"),
        "national and selected markets", "quarterly", "archive availability varies", "public figures page/PDF",
        "manual_download_required", "unknown; do not redistribute report files", "Cite report, period, page/figure, and retrieval date.",
        "Public presentation may include third-party inputs; automated reuse is not presumed.", "institutional_target", "report_inbox_manual_review", (5,4,3,5,3,4,4,3,1)),
    CRESourceCandidate("cushman_marketbeat", "Cushman & Wakefield MarketBeat", "cushmanwakefield.com",
        ("multifamily", "industrial", "office", "retail"),
        ("asking_rent", "effective_rent", "rent_growth_yoy", "vacancy_rate", "inventory", "deliveries", "net_absorption", "under_construction"),
        "national and 70+ local markets; report-specific definitions", "quarterly", "multi-year public report archive",
        "public MarketBeat page/PDF", "manual_download_required", "unknown; do not redistribute report files",
        "Cite publisher, market, quarter, page/table, retrieval date, and disclosed source.",
        "Reports expose useful multi-quarter tables, but archive automation and redistribution are not presumed.",
        "institutional_target", "report_inbox_manual_review", (5,5,4,5,4,4,4,3,1)),
    CRESourceCandidate("freddie_aimi", "Freddie Mac Apartment Investment Market Index", "mf.freddiemac.com", ("multifamily",),
        ("multifamily_noi_index", "multifamily_property_price_index", "multifamily_mortgage_rate"),
        "national and selected metros", "quarterly", "2000-present", "official XLS export", "official_download_review_terms",
        "official citation; underlying inputs have separate sources", "Cite Freddie Mac AIMI, quarter, metro, vintage, and component.",
        "Rental income combines rent and vacancy and is not a direct asking-rent target.", "market_proxy", "governed_official_file_adapter", (3,4,5,5,5,5,5,4,4)),
    CRESourceCandidate("zillow_zori", "Zillow Observed Rent Index", "zillow.com/research/data", ("multifamily",),
        ("observed_rent_index", "observed_rent_growth"), "national/metro/county/city/ZIP", "monthly", "series-dependent",
        "public CSV download", "official_download_review_terms", "terms review required before redistribution",
        "Cite Zillow Research, series, geography, date, and methodology.",
        "Repeat-listing asking-rent index; a market proxy, not institutional brokerage history.", "market_proxy", "manual_or_governed_download_after_terms_review", (3,5,4,4,5,4,5,3,3)),
    CRESourceCandidate("hud_chma", "HUD Comprehensive Housing Market Analysis", "huduser.gov", ("multifamily",),
        ("apartment_rent", "apartment_vacancy_rate", "rent_growth_yoy"), "selected housing market areas", "irregular", "report-specific",
        "official PDF", "manual_download_required", "underlying cited datasets may restrict reuse",
        "Cite HUD report, as-of date, page/table, and named underlying source.",
        "Useful spot observations, but irregular and often sourced from commercial data.", "market_proxy", "report_inbox_manual_review", (3,4,3,1,3,4,4,4,1)),
    CRESourceCandidate("sec_reit_filings", "SEC EDGAR public REIT filings", "sec.gov", ("multifamily", "industrial", "office", "retail"),
        ("same_store_rent_growth", "occupancy_rate", "noi_growth"), "issuer portfolio/market disclosures", "quarterly/annual", "issuer-dependent",
        "official filing/API/bulk files", "permitted_with_SEC_fair_access", "public filings",
        "Cite issuer, form, accession number, filing date, fact/table, and period.",
        "Issuer definitions and portfolios differ; careful market mapping is mandatory.", "institutional_target", "issuer_specific_adapter_after_methodology_review", (4,2,4,4,2,5,5,5,4)),
)


def discovery_catalog() -> list[dict]:
    output = []
    dimensions = ("target_relevance", "market_breadth", "historical_depth", "quarterly_consistency",
                  "methodology_consistency", "data_quality", "accessibility", "legal_clarity", "automation_suitability")
    for candidate in CANDIDATES:
        item = asdict(candidate); item["acquisition_score"] = candidate.acquisition_score
        item["score_dimensions"] = dict(zip(dimensions, item.pop("scores"), strict=True))
        item.update({"publicly_accessible": candidate.domain != "local", "downloadable": True,
                     "requires_login": False, "requires_payment": False,
                     "automation_permitted": candidate.automation in {"local_only", "permitted_with_SEC_fair_access"}})
        output.append(item)
    return sorted(output, key=lambda item: (-item["acquisition_score"], item["source_id"]))
