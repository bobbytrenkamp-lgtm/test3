from __future__ import annotations

from dataclasses import asdict

from .spec import CRETargetSourceSpec


CRE_TARGET_SOURCES = {
    "sec_maa_same_store": CRETargetSourceSpec(
        "sec_maa_same_store", "MAA SEC quarterly supplemental schedules", "public_company_filing",
        "institutional_target", ("multifamily",),
        ("effective_rent", "rent_growth_yoy", "revenue_growth_yoy", "operating_expense_growth_yoy",
         "noi_growth_yoy", "occupancy_rate", "vacancy_rate", "inventory"),
        ("market",), ("quarterly",), "Quarterly exhibits; useful history identified from 2019 onward",
        "sec_fair_access", "https://www.sec.gov/edgar/sec-api-documentation", False, False, True, "no",
        "Cite issuer, accession, exhibit 99.2, filing date, table, market row, and retrieval date.",
        "Public SEC-filed numeric facts are retained locally. Test3 does not redistribute filing text or assume "
        "source markets equal CBSAs. Analyst review and same-store methodology checks remain mandatory.",
        "high", "approved"),
    "user_owned_cre_history": CRETargetSourceSpec(
        "user_owned_cre_history", "User-owned CRE market history", "user_owned", "institutional_target",
        ("multifamily", "industrial", "office", "retail"),
        ("asking_rent", "effective_rent", "rent_growth_yoy", "vacancy_rate", "availability_rate",
         "net_absorption", "inventory", "deliveries", "under_construction", "transaction_cap_rate",
         "sale_price_per_unit", "sale_price_per_sf", "transaction_volume"),
        ("market", "submarket"), ("monthly", "quarterly", "annual"), "As supplied by the analyst",
        "local_file", None, False, False, False, "no",
        "Analyst must record the lawful source and contractual citation requirements.",
        "Local use only by default; Test3 never assumes redistribution rights.", "source_dependent", "approved"),
    "public_brokerage_report": CRETargetSourceSpec(
        "public_brokerage_report", "Public brokerage market report", "public_brokerage_report",
        "institutional_target", ("multifamily", "industrial", "office", "retail"),
        ("asking_rent", "rent_growth_yoy", "vacancy_rate", "availability_rate", "net_absorption",
         "inventory", "deliveries", "under_construction", "transaction_cap_rate"),
        ("market", "submarket"), ("quarterly", "annual"), "Report-specific", "reviewed_document", None,
        False, False, False, "unknown", "Cite publisher, report title, period, page, table, and retrieval date.",
        "Public visibility does not establish automation or redistribution rights; analyst review is mandatory.",
        "moderate", "manual_review"),
    "census_hvs": CRETargetSourceSpec(
        "census_hvs", "Census Housing Vacancy Survey", "federal_public", "residential_proxy",
        ("multifamily",), ("residential_rental_vacancy_rate", "median_asking_rent_vacant_units"),
        ("national", "region", "state", "cbsa"), ("quarterly", "annual"), "1956-present; geography varies",
        "official_download", "https://www.census.gov/housing/hvs/", False, False, True, "yes",
        "Cite the Census HVS table, period, vintage, and retrieval date.",
        "Housing survey proxy; not institutional apartment market vacancy or asking rent.", "high", "context_only"),
    "hud_fmr": CRETargetSourceSpec(
        "hud_fmr", "HUD Fair Market Rents", "federal_public", "market_proxy", ("multifamily",),
        ("fair_market_rent",), ("county", "hud_area"), ("annual",), "1983-present",
        "official_download", "https://www.huduser.gov/portal/datasets/fmr.html", False, False, True, "yes",
        "Cite HUD fiscal year, geography, bedroom count, and retrieval date.",
        "Regulatory gross-rent benchmark; never relabeled as institutional asking or effective rent.", "high", "context_only"),
    "fred_cre_price": CRETargetSourceSpec(
        "fred_cre_price", "FRED/IMF U.S. commercial real estate price series", "federal_public", "context_feature",
        ("other",), ("commercial_real_estate_price_growth",), ("national",), ("quarterly",), "2005-present",
        "official_download", "https://fred.stlouisfed.org/series/COMREPUSQ159N", False, False, True, "unknown",
        "Use the FRED suggested citation and underlying IMF terms.",
        "National mixed-CRE price growth; not a local rent, vacancy, or cap-rate target.", "moderate", "context_only"),
    "bis_commercial_property_prices": CRETargetSourceSpec(
        "bis_commercial_property_prices", "BIS Commercial Property Prices", "academic_open", "context_feature",
        ("industrial", "office", "retail", "other"), ("commercial_property_price_index",),
        ("national", "city"), ("monthly", "quarterly", "annual"), "Country/series-specific",
        "manual_download", "https://data.bis.org/topics/CPP", False, False, False, "unknown",
        "Cite BIS and the underlying national/private compiler shown in series metadata.",
        "Cross-country definitions and underlying rights vary; keep manual until series-level terms are reviewed.",
        "moderate", "manual_review"),
    "fhfa_multifamily_pudb": CRETargetSourceSpec(
        "fhfa_multifamily_pudb", "FHFA Enterprise Multifamily Public Use Database", "federal_public",
        "context_feature", ("multifamily",), ("mortgage_acquisition_characteristics",),
        ("national", "census_tract"), ("annual",), "Annual public-use files",
        "manual_download", "https://www.fhfa.gov/data/public-use-database", False, False, False, "yes",
        "Cite FHFA, file year, table/file, and retrieval date.",
        "Loan acquisition data can inform capital-market context but is not market rent/vacancy history.",
        "high", "context_only"),
}


def source_catalog() -> list[dict]:
    return [asdict(CRE_TARGET_SOURCES[key]) for key in sorted(CRE_TARGET_SOURCES)]
