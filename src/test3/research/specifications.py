from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpecification:
    name: str
    version: str
    target: str
    property_type: str
    frequency: str
    features: tuple[str, ...]
    entity_fixed_effects: bool
    time_fixed_effects: bool
    covariance: str
    minimum_sample: int = 100
    minimum_markets: int = 5
    minimum_periods: int = 20
    rationale: str = ""


MULTIFAMILY_RENT_GROWTH_SPECS = (
    ModelSpecification(
        "mf_rent_growth_demand", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("population_growth_yoy", "personal_income_growth_yoy", "covered_employment_growth_yoy"),
        True, True, "cluster_entity", rationale="Demand-side demographic, income and labor conditions.",
    ),
    ModelSpecification(
        "mf_rent_growth_supply", "1.0.0", "rent_growth_yoy", "multifamily", "annual",
        ("multifamily_permits_per_1000_population", "housing_unit_growth_yoy"),
        True, True, "cluster_entity", rationale="Governed public supply proxies; permits are not deliveries.",
    ),
    ModelSpecification(
        "mf_rent_growth_macro", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("treasury_10y_mean", "treasury_10y_change_1y"),
        True, True, "cluster_entity", rationale="Capital-market and inflation environment.",
    ),
    ModelSpecification(
        "mf_rent_growth_combined", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("population_growth_yoy", "covered_employment_growth_yoy", "personal_income_growth_yoy",
         "housing_unit_growth_yoy", "treasury_10y_mean", "treasury_10y_change_1y"),
        True, True, "cluster_entity", rationale="Controlled demand, supply-proxy and macro candidate set.",
    ),
)


MODEL_SPECIFICATIONS = {item.name: item for item in MULTIFAMILY_RENT_GROWTH_SPECS}
