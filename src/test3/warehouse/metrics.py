from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    label: str
    description: str
    unit: str
    measure_type: str
    aggregation: str
    compatible_geographies: tuple[str, ...]
    compatible_frequencies: tuple[str, ...]
    minimum: float | None = 0
    maximum: float | None = None


def _level(metric, label, unit, domain="regional"):
    return MetricSpec(metric, label, f"Governed {label.lower()} measure.", unit, "level", "last_observation",
                      ("national", "state", "county", "cbsa", "place"), ("daily", "weekly", "monthly", "quarterly", "annual"))


METRICS = {item.metric: item for item in (
    _level("population", "Population", "persons"), _level("households", "Households", "households"),
    _level("median_household_income", "Median household income", "USD_current"),
    _level("per_capita_income", "Per-capita income", "USD_current"),
    _level("average_household_size", "Average household size", "persons_per_household"),
    _level("civilian_population_16_plus", "Civilian population age 16 and over", "persons"),
    _level("bachelors_degree_population", "Bachelor's-degree population", "persons"),
    _level("housing_units", "Housing units", "units"), _level("occupied_housing_units", "Occupied housing units", "units"),
    _level("vacant_housing_units", "Vacant housing units", "units"), _level("employment", "Employment", "persons"),
    _level("unemployment", "Unemployment", "persons"), _level("labor_force", "Labor force", "persons"),
    _level("personal_income", "Personal income", "thousands_USD_current"), _level("personal_income_per_capita", "Per-capita personal income", "USD_current"),
    _level("gdp", "Gross domestic product", "thousands_USD_current"), _level("units_authorized_total", "Housing units authorized", "units"),
    _level("single_family_units_authorized", "Single-family units authorized", "units"),
    _level("multifamily_2_to_4_units_authorized", "Two-to-four-unit housing authorized", "units"),
    _level("multifamily_5_plus_units_authorized", "Five-plus-unit housing authorized", "units"),
    _level("residential_permits_total", "Residential permits", "permits"),
    _level("covered_employment", "QCEW covered employment", "persons"),
    _level("annual_average_establishments", "Annual average establishments", "establishments"),
    _level("total_annual_wages", "Total annual wages", "USD_current"),
    _level("average_weekly_wage", "Average weekly wage", "USD_current_per_week"),
    _level("average_annual_pay", "Average annual pay", "USD_current_per_year"),
    MetricSpec("county_cbsa_membership", "County-to-CBSA membership", "Vintage-specific official county component membership in a CBSA.", "membership", "category", "not_applicable", ("county",), ("irregular",), 1, 1),
    MetricSpec("fair_market_rent", "HUD Fair Market Rent", "HUD fiscal-year 40th-percentile monthly gross rent by bedroom count.", "USD_per_month", "level", "last_observation", ("county", "county_subdivision"), ("annual",), 0, None),
    MetricSpec("rental_vacancy_rate", "Residential rental vacancy rate", "CPS/HVS rental vacancy rate for the rental housing stock; not institutional multifamily market vacancy.", "percent", "rate", "mean", ("national", "region", "state", "cbsa"), ("quarterly", "annual"), 0, 100),
    MetricSpec("median_asking_rent_vacant_units", "Median asking rent for vacant rental units", "CPS/HVS asking rent for vacant units offered for rent; not institutional effective rent.", "USD_current_per_month", "level", "last_observation", ("national", "region"), ("quarterly", "annual"), 0, None),
    MetricSpec("unemployment_rate", "Unemployment rate", "Share of labor force unemployed.", "percent", "rate", "mean", ("national", "state", "county", "cbsa"), ("monthly", "annual"), 0, 100),
    MetricSpec("fed_funds_rate", "Federal funds rate", "Effective federal funds rate.", "percent", "rate", "mean", ("national",), ("daily",), None, None),
    *[MetricSpec(name, label, "Market interest-rate series.", "percent", "rate", "mean", ("national",), ("daily", "weekly"), None, None) for name, label in (("sofr", "SOFR"), ("treasury_2y", "2-year Treasury"), ("treasury_5y", "5-year Treasury"), ("treasury_10y", "10-year Treasury"), ("treasury_30y", "30-year Treasury"), ("mortgage_rate", "30-year mortgage rate"))],
    MetricSpec("cpi", "Consumer Price Index", "Consumer price index level.", "index_1982_1984_100", "index", "mean", ("national",), ("monthly",), 0, None),
    *[MetricSpec(name, label, description, unit, measure, "mean", ("national",), frequencies, minimum, maximum)
      for name, label, description, unit, measure, frequencies, minimum, maximum in (
        ("cre_lending_standards_multifamily", "Multifamily CRE lending standards", "SLOOS net percentage of banks tightening standards for CRE loans secured by multifamily properties.", "percent_net_respondents", "rate", ("quarterly",), -100, 100),
        ("cre_lending_standards_nonresidential", "Nonresidential CRE lending standards", "SLOOS net percentage of banks tightening standards for loans secured by nonfarm nonresidential properties.", "percent_net_respondents", "rate", ("quarterly",), -100, 100),
        ("cre_loan_demand_multifamily", "Multifamily CRE loan demand", "SLOOS net percentage of banks reporting stronger demand for multifamily CRE loans.", "percent_net_respondents", "rate", ("quarterly",), -100, 100),
        ("cre_loan_demand_nonresidential", "Nonresidential CRE loan demand", "SLOOS net percentage of banks reporting stronger demand for nonfarm nonresidential CRE loans.", "percent_net_respondents", "rate", ("quarterly",), -100, 100),
        ("cre_loan_delinquency_rate", "CRE loan delinquency rate", "Delinquency rate on CRE loans excluding farmland at all commercial banks.", "percent", "rate", ("quarterly",), 0, 100),
        ("cre_bank_loans", "Commercial real estate bank loans", "Commercial real estate loans held by all commercial banks.", "billions_USD_current", "level", ("monthly",), 0, None),
      )],
)}


def get_metric(metric: str) -> MetricSpec:
    if metric not in METRICS:
        raise ValueError(f"unknown governed metric: {metric}")
    return METRICS[metric]
