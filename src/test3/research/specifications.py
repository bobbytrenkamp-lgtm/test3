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
    purpose: str = "inference_only"
    expected_signs: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.purpose not in {"inference_only", "forecast"}:
            raise ValueError("model purpose must be inference_only or forecast")
        if self.purpose == "forecast" and self.time_fixed_effects:
            raise ValueError("forecast specifications cannot require unknown future time fixed effects")


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


MULTIFAMILY_EXPENSE_GROWTH_SPECS = (
    ModelSpecification(
        "mf_operating_expense_growth_macro", "1.0.0", "operating_expense_growth_yoy", "multifamily", "quarterly",
        ("cpi_growth_yoy", "personal_income_growth_yoy"), True, True, "cluster_entity",
        rationale="Transparent inflation and local-income candidate for same-store operating-expense growth.",
    ),
)


MULTIFAMILY_RENT_GROWTH_FORECAST_SPECS = (
    ModelSpecification(
        "mf_rent_growth_demand_forecast", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("population_growth_yoy", "personal_income_growth_yoy", "covered_employment_growth_yoy"),
        True, False, "cluster_entity", rationale="Leakage-safe demand forecast for existing governed markets.",
        purpose="forecast", expected_signs=(("population_growth_yoy", "positive"),
                                             ("personal_income_growth_yoy", "positive"),
                                             ("covered_employment_growth_yoy", "positive")),
    ),
    ModelSpecification(
        "mf_rent_growth_macro_forecast", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("treasury_10y_mean", "treasury_10y_change_1y"), True, False, "cluster_entity",
        rationale="Leakage-safe macro forecast; coefficient signs are empirically evaluated.", purpose="forecast",
    ),
    ModelSpecification(
        "mf_rent_growth_combined_forecast", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("population_growth_yoy", "covered_employment_growth_yoy", "personal_income_growth_yoy",
         "housing_unit_growth_yoy", "treasury_10y_mean", "treasury_10y_change_1y"),
        True, False, "cluster_entity", rationale="Limited leakage-safe demand, supply-proxy, and macro forecast.",
        purpose="forecast",
    ),
    ModelSpecification(
        "mf_rent_growth_demand_lag2q_forecast", "1.0.0", "rent_growth_yoy", "multifamily", "quarterly",
        ("population_growth_yoy_lag_2q", "personal_income_growth_yoy", "covered_employment_growth_yoy"),
        True, False, "cluster_entity", rationale="Governed two-quarter population-signal lag experiment.",
        purpose="forecast", expected_signs=(("population_growth_yoy_lag_2q", "positive"),),
    ),
)


MODEL_SPECIFICATIONS = {item.name: item for item in (*MULTIFAMILY_RENT_GROWTH_SPECS,
                                                     *MULTIFAMILY_EXPENSE_GROWTH_SPECS,
                                                     *MULTIFAMILY_RENT_GROWTH_FORECAST_SPECS)}
