from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class PublicSeries:
    provider: str
    series_id: str
    metric: str
    label: str
    frequency: str
    unit: str


PUBLIC_SERIES = (
    PublicSeries("FRED", "DGS10", "treasury_rate", "10-Year Treasury Constant Maturity Rate", "daily", "decimal_fraction"),
    PublicSeries("FRED", "DGS2", "treasury_rate_2y", "2-Year Treasury Constant Maturity Rate", "daily", "decimal_fraction"),
    PublicSeries("FRED", "SOFR", "sofr_rate", "Secured Overnight Financing Rate", "daily", "decimal_fraction"),
    PublicSeries("FRED", "BAMLH0A0HYM2", "high_yield_spread", "US High Yield Option-Adjusted Spread", "daily", "decimal_fraction"),
    PublicSeries("FRED", "MORTGAGE30US", "mortgage_rate_30y", "30-Year Fixed Mortgage Average", "weekly", "decimal_fraction"),
    PublicSeries("FRED", "CPATAX", "corporate_profit_after_tax", "Corporate Profits After Tax", "quarterly", "USD_billions"),
    PublicSeries("FRED", "HOUST", "housing_starts", "Housing Starts", "monthly", "thousands_units"),
    PublicSeries("FRED", "PERMIT", "building_permits", "New Private Housing Units Authorized", "monthly", "thousands_units"),
    PublicSeries("FRED", "MSACSR", "housing_supply_months", "Monthly Supply of New Houses", "monthly", "months"),
    PublicSeries("FRED", "RSAFS", "retail_sales", "Advance Retail Sales", "monthly", "USD_millions"),
    PublicSeries("FRED", "TOTALSA", "vehicle_sales", "Total Vehicle Sales", "monthly", "millions_units"),
    PublicSeries("FRED", "INDPRO", "industrial_production_index", "Industrial Production Index", "monthly", "index"),
    PublicSeries("FRED", "BUSLOANS", "commercial_industrial_loans", "Commercial and Industrial Loans", "weekly", "USD_billions"),
    PublicSeries("FRED", "DRCRELEXFACBS", "cre_delinquency_rate", "CRE Loan Delinquency Rate", "quarterly", "decimal_fraction"),
    PublicSeries("FRED", "WILL5000IND", "equity_market_index", "Wilshire 5000 Total Market Index", "daily", "index"),
    PublicSeries("BLS", "CUUR0000SA0", "inflation_index", "Consumer Price Index, All Urban Consumers", "monthly", "index"),
    PublicSeries("BLS", "CUUR0000SEHA", "rent_primary_residence_index", "Rent of Primary Residence CPI", "monthly", "index"),
    PublicSeries("BLS", "CUUR0000SEHC", "owners_equivalent_rent_index", "Owners' Equivalent Rent CPI", "monthly", "index"),
    PublicSeries("BLS", "WPUIP2310001", "construction_input_price_index", "Inputs to Construction Industries PPI", "monthly", "index"),
    PublicSeries("BLS", "CES5500000001", "financial_activities_employment", "Financial Activities Employment", "monthly", "thousands_jobs"),
    PublicSeries("BLS", "CES6000000001", "professional_services_employment", "Professional and Business Services Employment", "monthly", "thousands_jobs"),
    PublicSeries("BLS", "CES7000000001", "leisure_hospitality_employment", "Leisure and Hospitality Employment", "monthly", "thousands_jobs"),
    PublicSeries("CENSUS", "B01003_001E", "population", "ACS Total Population", "annual", "people"),
    PublicSeries("CENSUS", "B19013_001E", "median_household_income", "ACS Median Household Income", "annual", "USD"),
    PublicSeries("CENSUS", "B25003_003E", "renter_households", "ACS Renter-Occupied Housing Units", "annual", "households"),
    PublicSeries("CENSUS", "B25004_001E", "vacant_housing_units", "ACS Vacant Housing Units", "annual", "units"),
    PublicSeries("CENSUS", "B25064_001E", "median_gross_rent", "ACS Median Gross Rent", "annual", "USD_per_month"),
)


def public_series_catalog() -> list[dict]:
    return [item.__dict__.copy() for item in PUBLIC_SERIES]


def _number(value: str, percentage: bool) -> str | None:
    value = value.strip()
    if not value or value in {".", "NA", "null", "-"}:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid public-series value: {value}") from error
    if not number.is_finite():
        raise ValueError("Public-series values must be finite")
    if percentage:
        number /= Decimal("100")
    return format(number, "f")


def parse_fred_csv(content: bytes, series_id: str, metric: str, unit: str, geography_id: str = "US") -> list[dict]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "DATE" not in reader.fieldnames or series_id not in reader.fieldnames:
        raise ValueError("FRED CSV must contain DATE and the requested series column")
    percentage = unit == "decimal_fraction"
    rows = []
    for source_row, item in enumerate(reader, start=2):
        observed = date.fromisoformat(item["DATE"]).isoformat()
        value = _number(item[series_id], percentage)
        if value is not None:
            rows.append({"period": observed, "metric": metric, "value": value, "unit": unit, "geography_type": "country", "geography_id": geography_id, "source_row": source_row})
    return rows


def parse_bls_csv(content: bytes, series_id: str, metric: str, unit: str, geography_id: str = "US") -> list[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    required = {"series_id", "year", "period", "value"}
    if not reader.fieldnames or not required.issubset({name.strip() for name in reader.fieldnames}):
        raise ValueError("BLS CSV must contain series_id, year, period and value")
    rows = []
    for source_row, raw in enumerate(reader, start=2):
        item = {key.strip(): value.strip() for key, value in raw.items() if key is not None}
        if item["series_id"] != series_id or item["period"] == "M13":
            continue
        month = int(item["period"].removeprefix("M"))
        if not 1 <= month <= 12:
            raise ValueError("BLS monthly period must be M01 through M12")
        value = _number(item["value"], unit == "decimal_fraction")
        if value is not None:
            rows.append({"period": f'{int(item["year"]):04d}-{month:02d}-01', "metric": metric, "value": value, "unit": unit, "geography_type": "country", "geography_id": geography_id, "source_row": source_row})
    return rows


def build_market_panel_csv(rows: list[dict], *, source: str, source_date: str, source_reference: str, usage_rights: str, property_type: str) -> bytes:
    """Convert one normalized public series into the audited market-panel interchange format."""
    if not rows:
        raise ValueError("Public series contains no usable observations")
    metric = rows[0]["metric"]
    if any(row["metric"] != metric for row in rows):
        raise ValueError("A portable public-series panel must contain exactly one metric")
    fields = ["period", "market_id", "market_name", "property_type", "source", "source_date", "source_reference", "usage_rights", "geography_type", "geography_id", metric]
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({"period": row["period"], "market_id": row["geography_id"], "market_name": row["geography_id"], "property_type": property_type, "source": source, "source_date": date.fromisoformat(source_date).isoformat(), "source_reference": source_reference, "usage_rights": usage_rights, "geography_type": row["geography_type"], "geography_id": row["geography_id"], metric: row["value"]})
    return target.getvalue().encode("utf-8")
