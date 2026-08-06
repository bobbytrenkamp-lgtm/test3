from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

ASSUMPTION_TYPES = (
    "market_rent_growth", "market_rent", "vacancy", "renewal_probability", "downtime",
    "tenant_improvements", "leasing_commissions", "expense_growth", "property_tax_growth",
    "insurance_growth", "exit_cap_rate", "discount_rate", "debt_interest_rate",
    "construction_cost_growth", "lease_up_pace",
)
PROPERTY_TYPES = frozenset({"office", "industrial", "retail", "multifamily", "mixed_use", "student_housing", "self_storage", "medical_office", "life_science", "data_center", "hotel", "senior_housing", "manufactured_housing", "parking", "land", "ground_lease"})
RATE_METRICS = frozenset({"rent_growth_12m", "vacancy_rate", "availability_rate", "transaction_cap_rate", "employment_growth", "population_growth", "income_growth", "inflation", "treasury_rate", "treasury_rate_2y", "sofr_rate", "high_yield_spread", "mortgage_rate_30y", "cre_delinquency_rate", "renewal_probability", "leasing_commission_rate", "expense_growth", "property_tax_growth", "insurance_growth", "discount_rate", "debt_interest_rate", "construction_cost_growth"})
DECIMAL_METRICS = RATE_METRICS | frozenset({"effective_rent", "asking_rent", "net_absorption", "inventory", "new_deliveries", "construction_pipeline", "transaction_count", "lease_comp_count", "building_permits", "downtime_months", "tenant_improvements", "lease_up_units_per_month", "operating_expense_per_area", "property_tax_per_area", "insurance_per_area", "utility_cost_per_area", "payroll_cost_per_area", "repair_maintenance_per_area", "treasury_rate_2y", "sofr_rate", "high_yield_spread", "mortgage_rate_30y", "corporate_profit_after_tax", "housing_starts", "housing_supply_months", "retail_sales", "vehicle_sales", "industrial_production_index", "commercial_industrial_loans", "cre_delinquency_rate", "equity_market_index", "inflation_index", "rent_primary_residence_index", "owners_equivalent_rent_index", "construction_input_price_index", "financial_activities_employment", "professional_services_employment", "leisure_hospitality_employment", "population", "median_household_income", "renter_households", "vacant_housing_units", "median_gross_rent"})
REQUIRED_MARKET_COLUMNS = frozenset({"period", "market_id", "market_name", "property_type", "source", "source_date", "source_reference", "usage_rights"})


def iso_date(value: object, field: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error


def finite_decimal(value: object, field: str, rate: bool = False) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"{field} must be a decimal") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    if rate and not Decimal("-1") <= number <= Decimal("1"):
        raise ValueError(f"{field} must be a decimal fraction from -1 through 1")
    return format(number, "f")


def validate_county_fips(value: object) -> str | None:
    result = str(value or "").strip()
    if not result:
        return None
    if len(result) != 5 or not result.isdigit():
        raise ValueError("county_fips must contain exactly five digits")
    return result
