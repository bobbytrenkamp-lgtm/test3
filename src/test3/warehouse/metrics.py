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
    _level("working_age_population_universe", "Working-age population universe", "persons"),
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
    MetricSpec("unemployment_rate", "Unemployment rate", "Share of labor force unemployed.", "percent", "rate", "mean", ("national", "state", "county", "cbsa"), ("monthly", "annual"), 0, 100),
    MetricSpec("fed_funds_rate", "Federal funds rate", "Effective federal funds rate.", "percent", "rate", "mean", ("national",), ("daily",), None, None),
    *[MetricSpec(name, label, "Market interest-rate series.", "percent", "rate", "mean", ("national",), ("daily", "weekly"), None, None) for name, label in (("sofr", "SOFR"), ("treasury_2y", "2-year Treasury"), ("treasury_5y", "5-year Treasury"), ("treasury_10y", "10-year Treasury"), ("treasury_30y", "30-year Treasury"), ("mortgage_rate", "30-year mortgage rate"))],
    MetricSpec("cpi", "Consumer Price Index", "Consumer price index level.", "index_1982_1984_100", "index", "mean", ("national",), ("monthly",), 0, None),
)}


def get_metric(metric: str) -> MetricSpec:
    if metric not in METRICS:
        raise ValueError(f"unknown governed metric: {metric}")
    return METRICS[metric]
