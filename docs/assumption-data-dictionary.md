# Assumption data dictionary

All rates are decimal fractions, all dates are ISO `YYYY-MM-DD`, currency is explicit, and missing values remain null/blank rather than zero.

| Metric | Meaning | Typical unit | Candidate assumption |
|---|---|---|---|
| rent_growth_12m | Trailing twelve-month change in market/effective rent | decimal_fraction | market_rent_growth |
| effective_rent / asking_rent | Market rent after/before concessions according to source methodology | USD_per_area | market_rent |
| vacancy_rate / availability_rate | Vacant or marketed space divided by relevant inventory | decimal_fraction | vacancy |
| renewal_probability | Observed renewals divided by eligible expirations | decimal_fraction | renewal_probability |
| downtime_months | Months from expiration/vacancy to new rent commencement | months | downtime |
| tenant_improvements | Landlord TI contribution | USD_per_area | tenant_improvements |
| leasing_commission_rate | Commission divided by documented rent/consideration basis | decimal_fraction | leasing_commissions |
| expense_growth | Comparable-period operating expense growth | decimal_fraction | expense_growth |
| property_tax_growth | Comparable-period property-tax growth | decimal_fraction | property_tax_growth |
| insurance_growth | Comparable-period insurance-premium growth | decimal_fraction | insurance_growth |
| transaction_cap_rate | NOI divided by transaction price under source methodology | decimal_fraction | exit_cap_rate |
| discount_rate | Observed/approved discount rate | decimal_fraction | discount_rate |
| debt_interest_rate | All-in debt coupon/rate | decimal_fraction | debt_interest_rate |
| construction_cost_growth | Comparable construction-cost-index growth | decimal_fraction | construction_cost_growth |
| lease_up_units_per_month | Net newly occupied units/area-equivalent per month | units_per_month | lease_up_pace |

Additional context metrics include absorption, inventory, deliveries, pipeline, transactions, permits, employment/population/income growth, inflation, Treasury rate, and granular operating costs per area. Definitions and transformations must be source-specific in `methodology_notes`; incompatible definitions should not be pooled.
