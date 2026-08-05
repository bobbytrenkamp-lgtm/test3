from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    value_type: str
    patterns: tuple[str, ...]
    categories: frozenset[str]
    unit: str | None = None
    currency: str | None = None
    confidence: float = 0.82
    reconciliation_use: str | None = None
    export_target: str | None = None


def _spec(name: str, label: str, value_type: str, pattern: str, categories: tuple[str, ...], **kwargs: object) -> FieldSpec:
    return FieldSpec(name, label, value_type, (pattern,), frozenset(categories), **kwargs)


PROPERTY = ("offering_memorandum", "appraisal", "property_condition_report", "environmental_report")
TRANSACTION = ("offering_memorandum", "letter_of_intent", "purchase_and_sale_agreement", "appraisal")
LEASE = ("commercial_lease", "lease_amendment", "rent_roll")
OPERATIONS = ("offering_memorandum", "t12_operating_statement", "historical_operating_statement", "appraisal")
DEBT = ("debt_quote", "loan_term_sheet")
CAPITAL = ("capital_expenditure_budget", "property_condition_report")


FIELD_REGISTRY: tuple[FieldSpec, ...] = (
    _spec("property_name", "Property name", "text", r"(?im)^property(?: name)?\s*[:,-]\s*(.+)$", PROPERTY, export_target="property.name"),
    _spec("address", "Property address", "text", r"(?im)^(?:property )?address\s*[:,-]\s*(.+)$", PROPERTY, export_target="property.address"),
    _spec("rentable_square_feet", "Rentable area", "decimal", r"(?i)(?:rentable (?:area|square feet)|\brsf)\s*[: ]+([0-9,.]+)", PROPERTY + LEASE, unit="sqft", reconciliation_use="area", export_target="property.rentableArea"),
    _spec("unit_count", "Unit count", "integer", r"(?i)(?:unit count|total units|number of units)\s*[: ]+([0-9,]+)", PROPERTY + OPERATIONS, unit="units", reconciliation_use="unit_count", export_target="property.unitCount"),
    _spec("year_built", "Year built", "integer", r"(?i)year built\s*[: ]+([0-9]{4})", PROPERTY),
    _spec("land_area_acres", "Land area", "decimal", r"(?i)(?:land area|site area|acreage)\s*[: ]+([0-9,.]+)\s*(?:acres?)?", PROPERTY, unit="acres"),
    _spec("county_fips", "County FIPS", "fips", r"(?i)county fips\s*[: ]+([0-9]{5})", PROPERTY),
    _spec("state", "State", "text", r"(?im)^state\s*[:,-]\s*(.+)$", PROPERTY),
    _spec("municipality", "Municipality", "text", r"(?im)^(?:municipality|city|town)\s*[:,-]\s*(.+)$", PROPERTY),
    _spec("parcel_id", "Parcel ID", "text", r"(?im)^(?:parcel|tax parcel)(?: id| number)?\s*[:,-]\s*(.+)$", PROPERTY),
    _spec("asking_price", "Asking price", "decimal", r"(?i)(?:asking|purchase) price\s*[:$ ]+([($0-9,.]+)", TRANSACTION, currency="USD", reconciliation_use="price", export_target="valuation.acquisitionPrice"),
    _spec("loi_price", "LOI price", "decimal", r"(?i)(?:loi|proposed) (?:purchase )?price\s*[:$ ]+([($0-9,.]+)", ("letter_of_intent",), currency="USD", reconciliation_use="price"),
    _spec("psa_price", "PSA price", "decimal", r"(?i)(?:purchase price|consideration)\s*[:$ ]+([($0-9,.]+)", ("purchase_and_sale_agreement",), currency="USD", reconciliation_use="price"),
    _spec("appraised_value", "Appraised value", "decimal", r"(?i)(?:appraised|market) value\s*[:$ ]+([($0-9,.]+)", ("appraisal",), currency="USD"),
    _spec("broker_stated_noi", "Broker-stated NOI", "decimal", r"(?i)(?:broker[- ]stated )?noi\s*[:$ ]+([($0-9,.]+)", ("offering_memorandum", "appraisal"), currency="USD", reconciliation_use="cap_rate"),
    _spec("broker_stated_cap_rate", "Broker-stated cap rate", "rate", r"(?i)(?:cap(?:italization)? rate)\s*[: ]+([0-9.]+%?)", ("offering_memorandum", "appraisal"), unit="decimal_fraction", reconciliation_use="cap_rate"),
    _spec("occupancy", "Occupancy", "rate", r"(?i)(?:physical )?occupancy\s*[: ]+([0-9.]+%?)", OPERATIONS + ("rent_roll",), unit="decimal_fraction", reconciliation_use="occupancy"),
    _spec("rent_roll_occupied_area", "Rent-roll occupied area", "decimal", r"(?i)(?:occupied (?:area|square feet)|occupied rsf)\s*[: ]+([0-9,.]+)", ("rent_roll",), unit="sqft", reconciliation_use="occupancy"),
    _spec("rent_roll_total_area", "Rent-roll total area", "decimal", r"(?i)(?:rent[- ]roll )?(?:total|rentable) (?:area|square feet|rsf)\s*[: ]+([0-9,.]+)", ("rent_roll",), unit="sqft", reconciliation_use="area"),
    _spec("rent_roll_annualized_rent", "Rent-roll annualized rent", "decimal", r"(?i)(?:annualized|annual) (?:base )?rent\s*[:$ ]+([($0-9,.]+)", ("rent_roll",), currency="USD", reconciliation_use="rent_revenue"),
    _spec("operating_rental_revenue", "Operating rental revenue", "decimal", r"(?i)(?:rental|base rent) revenue\s*[:$ ]+([($0-9,.]+)", OPERATIONS, currency="USD", reconciliation_use="rent_revenue"),
    _spec("gross_revenue", "Gross revenue", "decimal", r"(?i)(?:gross (?:potential )?revenue|total revenue)\s*[:$ ]+([($0-9,.]+)", OPERATIONS, currency="USD", reconciliation_use="noi_composition"),
    _spec("operating_expenses", "Operating expenses", "decimal", r"(?i)(?:total )?operating expenses\s*[:$ ]+([($0-9,.]+)", OPERATIONS, currency="USD", reconciliation_use="noi_composition"),
    _spec("reported_noi", "Reported NOI", "decimal", r"(?i)(?:reported|actual|net operating income)\s*[:$ ]+([($0-9,.]+)", OPERATIONS, currency="USD", reconciliation_use="noi_composition"),
    _spec("calculated_noi", "Calculated NOI", "decimal", r"(?i)calculated noi\s*[:$ ]+([($0-9,.]+)", OPERATIONS, currency="USD", reconciliation_use="noi_composition"),
    _spec("historical_noi", "Historical NOI", "decimal", r"(?i)historical noi\s*[:$ ]+([($0-9,.]+)", ("historical_operating_statement", "offering_memorandum", "appraisal"), currency="USD", reconciliation_use="noi_trend"),
    _spec("pro_forma_noi", "Pro forma NOI", "decimal", r"(?i)pro[ -]?forma noi\s*[:$ ]+([($0-9,.]+)", ("offering_memorandum", "appraisal"), currency="USD", reconciliation_use="noi_trend"),
    _spec("tenant_name", "Tenant name", "text", r"(?im)^tenant(?: name)?\s*[:,-]\s*(.+)$", LEASE, reconciliation_use="tenant"),
    _spec("suite", "Suite", "text", r"(?im)^(?:suite|premises)\s*[:,-]\s*(.+)$", LEASE),
    _spec("lease_area", "Lease area", "decimal", r"(?i)(?:leased? (?:area|premises)|lease rsf)\s*[: ]+([0-9,.]+)", LEASE, unit="sqft", reconciliation_use="lease_area"),
    _spec("lease_commencement_date", "Lease commencement", "date", r"(?i)(?:lease )?(?:commencement|start) date\s*[: ]+([A-Za-z0-9, /.-]+)", LEASE, reconciliation_use="lease_dates"),
    _spec("lease_expiration_date", "Lease expiration", "date", r"(?i)(?:lease )?(?:expiration|expiry|end) date\s*[: ]+([A-Za-z0-9, /.-]+)", LEASE, reconciliation_use="lease_dates"),
    _spec("lease_current_rent", "Current rent", "decimal", r"(?i)(?:current|base) rent\s*[:$ ]+([($0-9,.]+)", LEASE, currency="USD", reconciliation_use="lease_rent"),
    _spec("rent_roll_expiration", "Rent-roll expiration", "date", r"(?i)rent[- ]roll expiration(?: date)?\s*[: ]+([A-Za-z0-9, /.-]+)", ("rent_roll",), reconciliation_use="lease_dates"),
    _spec("rent_roll_current_rent", "Rent-roll current rent", "decimal", r"(?i)rent[- ]roll current rent\s*[:$ ]+([($0-9,.]+)", ("rent_roll",), currency="USD", reconciliation_use="lease_rent"),
    _spec("rent_roll_lease_area", "Rent-roll lease area", "decimal", r"(?i)rent[- ]roll lease (?:area|rsf)\s*[: ]+([0-9,.]+)", ("rent_roll",), unit="sqft", reconciliation_use="lease_area"),
    _spec("rent_roll_unit_count", "Rent-roll unit count", "integer", r"(?i)rent[- ]roll (?:unit count|total units)\s*[: ]+([0-9,]+)", ("rent_roll",), unit="units", reconciliation_use="unit_count"),
    _spec("security_deposit", "Security deposit", "decimal", r"(?i)security deposit\s*[:$ ]+([($0-9,.]+)", LEASE, currency="USD"),
    _spec("loan_amount", "Loan amount", "decimal", r"(?i)loan amount\s*[:$ ]+([($0-9,.]+)", DEBT, currency="USD", reconciliation_use="leverage"),
    _spec("interest_rate", "Interest rate", "rate", r"(?i)(?:all-in )?interest rate\s*[: ]+([0-9.]+%?)", DEBT, unit="decimal_fraction", reconciliation_use="debt_rate"),
    _spec("loan_spread", "Loan spread", "rate", r"(?i)(?:credit )?spread\s*[: ]+([0-9.]+)\s*(?:bps|basis points)", DEBT, unit="basis_points", reconciliation_use="debt_rate"),
    _spec("loan_term_months", "Loan term", "integer", r"(?i)(?:loan )?term\s*[: ]+([0-9]+)\s*months?", DEBT, unit="months"),
    _spec("amortization_months", "Amortization", "integer", r"(?i)amortization\s*[: ]+([0-9]+)\s*months?", DEBT, unit="months"),
    _spec("interest_only_months", "Interest-only period", "integer", r"(?i)interest[- ]only(?: period)?\s*[: ]+([0-9]+)\s*months?", DEBT, unit="months"),
    _spec("stated_ltv", "Stated LTV", "rate", r"(?i)(?:maximum |stated )?ltv\s*[: ]+([0-9.]+%?)", DEBT, unit="decimal_fraction", reconciliation_use="leverage"),
    _spec("stated_ltc", "Stated LTC", "rate", r"(?i)(?:maximum |stated )?ltc\s*[: ]+([0-9.]+%?)", DEBT, unit="decimal_fraction", reconciliation_use="leverage"),
    _spec("calculated_ltv", "Calculated LTV", "rate", r"(?i)calculated ltv\s*[: ]+([0-9.]+%?)", DEBT, unit="decimal_fraction", reconciliation_use="leverage"),
    _spec("calculated_ltc", "Calculated LTC", "rate", r"(?i)calculated ltc\s*[: ]+([0-9.]+%?)", DEBT, unit="decimal_fraction", reconciliation_use="leverage"),
    _spec("calculated_all_in_rate", "Calculated all-in rate", "rate", r"(?i)calculated all[- ]in rate\s*[: ]+([0-9.]+%?)", DEBT, unit="decimal_fraction", reconciliation_use="debt_rate"),
    _spec("minimum_dscr", "Minimum DSCR", "decimal", r"(?i)(?:minimum )?dscr\s*[: ]+([0-9.]+)x?", DEBT),
    _spec("capex_stated_total", "Stated capital total", "decimal", r"(?i)(?:total |stated )?(?:capital expenditures|capex)\s*[:$ ]+([($0-9,.]+)", CAPITAL, currency="USD", reconciliation_use="capex_total"),
    _spec("capex_line_item_total", "Calculated capital line-item total", "decimal", r"(?i)(?:calculated |line[- ]item )capex total\s*[:$ ]+([($0-9,.]+)", CAPITAL, currency="USD", reconciliation_use="capex_total"),
    _spec("expected_row_count", "Expected source row count", "integer", r"(?i)expected row count\s*[: ]+([0-9,]+)", ("rent_roll", "t12_operating_statement", "historical_operating_statement", "capital_expenditure_budget"), unit="rows", reconciliation_use="row_completeness"),
    _spec("actual_row_count", "Parsed row count", "integer", r"(?i)(?:actual|parsed) row count\s*[: ]+([0-9,]+)", ("rent_roll", "t12_operating_statement", "historical_operating_statement", "capital_expenditure_budget"), unit="rows", reconciliation_use="row_completeness"),
    _spec("forecast_start_date", "Forecast start date", "date", r"(?i)forecast start(?: date)?\s*[: ]+([A-Za-z0-9, /.-]+)", ("offering_memorandum", "appraisal"), export_target="forecast.startDate"),
    _spec("forecast_months", "Forecast months", "integer", r"(?i)forecast (?:term|period|months)\s*[: ]+([0-9]+)\s*months?", ("offering_memorandum", "appraisal"), unit="months", export_target="forecast.months"),
    _spec("discount_rate", "Discount rate", "rate", r"(?i)discount rate\s*[: ]+([0-9.]+%?)", ("appraisal",), unit="decimal_fraction", export_target="valuation.discountRate"),
    _spec("market_rent_growth", "Market rent growth", "signed_rate", r"(?i)market rent growth\s*[: ]+([-0-9.]+%?)", ("offering_memorandum", "appraisal"), unit="decimal_fraction", export_target="growthCurves"),
)


FIELD_BY_NAME = {field.name: field for field in FIELD_REGISTRY}


def applicable_fields(category: str | None) -> tuple[FieldSpec, ...]:
    if not category or category == "unknown":
        return FIELD_REGISTRY
    return tuple(field for field in FIELD_REGISTRY if category in field.categories)
