from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssumptionSpec:
    name: str
    label: str
    metric: str
    unit: str
    signed: bool = False
    preferred_history: int = 12
    test2_target: str | None = None


ASSUMPTION_CATALOG = (
    AssumptionSpec("market_rent_growth", "Market rent growth", "rent_growth_12m", "decimal_fraction", True, 12, "growthCurves"),
    AssumptionSpec("market_rent", "Market rent", "effective_rent", "USD_per_area", False, 8, "marketLeasingProfiles.marketRent"),
    AssumptionSpec("vacancy", "Vacancy", "vacancy_rate", "decimal_fraction", False, 12, "vacancy.generalVacancyRate"),
    AssumptionSpec("renewal_probability", "Renewal probability", "renewal_probability", "decimal_fraction", False, 20, "marketLeasingProfiles.renewalProbability"),
    AssumptionSpec("downtime", "Downtime", "downtime_months", "months", False, 20, "marketLeasingProfiles.downtimeMonths"),
    AssumptionSpec("tenant_improvements", "Tenant improvements", "tenant_improvements", "USD_per_area", False, 20, "marketLeasingProfiles.tenantImprovements"),
    AssumptionSpec("leasing_commissions", "Leasing commissions", "leasing_commission_rate", "decimal_fraction", False, 20, "marketLeasingProfiles.leasingCommissionRate"),
    AssumptionSpec("expense_growth", "Expense growth", "expense_growth", "decimal_fraction", True, 12, "growthCurves"),
    AssumptionSpec("property_tax_growth", "Property tax growth", "property_tax_growth", "decimal_fraction", True, 12, "growthCurves"),
    AssumptionSpec("insurance_growth", "Insurance growth", "insurance_growth", "decimal_fraction", True, 12, "growthCurves"),
    AssumptionSpec("exit_cap_rate", "Exit capitalization rate", "transaction_cap_rate", "decimal_fraction", False, 20, "valuation.terminalCapRate"),
    AssumptionSpec("discount_rate", "Discount rate", "discount_rate", "decimal_fraction", False, 20, "valuation.discountRate"),
    AssumptionSpec("debt_interest_rate", "Debt interest rate", "debt_interest_rate", "decimal_fraction", False, 20, "debt.fixedRate"),
    AssumptionSpec("construction_cost_growth", "Construction cost growth", "construction_cost_growth", "decimal_fraction", True, 12, "growthCurves"),
    AssumptionSpec("lease_up_pace", "Lease-up pace", "lease_up_units_per_month", "units_per_month", False, 12, None),
)

BY_NAME = {item.name: item for item in ASSUMPTION_CATALOG}


def public_catalog() -> list[dict]:
    return [
        {"name": item.name, "label": item.label, "metric": item.metric, "unit": item.unit, "signed": item.signed, "preferredHistory": item.preferred_history, "test2Target": item.test2_target}
        for item in ASSUMPTION_CATALOG
    ]
