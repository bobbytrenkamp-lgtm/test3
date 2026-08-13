from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    description: str
    input_metrics: tuple[str, ...] = ()
    input_features: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    transformation: str = "source_last_observation"
    frequencies: tuple[str, ...] = ("annual",)
    geography_types: tuple[str, ...] = ("county", "cbsa")
    unit: str = ""
    aggregation: str = "last_observation"
    cbsa_aggregation: str = "none"
    lag_periods: int = 0
    property_subtype: str | None = None
    winsorization: str | None = None
    missing_value_rule: str = "omit; never zero-fill or interpolate"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValueError(f"feature name must be a safe identifier: {self.name}")
        if self.transformation == "source_last_observation" and len(self.input_metrics) != 1:
            raise ValueError(f"source feature {self.name} requires exactly one input metric")
        if self.name == "market_rent" and "fair_market_rent" in self.input_metrics:
            raise ValueError("HUD Fair Market Rent cannot be registered as market_rent")
        if self.lag_periods < 0:
            raise ValueError("lag periods cannot be negative")
        if self.winsorization is not None:
            raise ValueError("Milestone 3A does not silently winsorize source evidence")


def _source(name, description, metric, unit, *, source_ids, cbsa="sum", frequencies=("annual", "quarterly"), subtype=None):
    return FeatureSpec(name, description, (metric,), source_ids=source_ids, unit=unit,
                       frequencies=frequencies, geography_types=("county",) if cbsa == "none" else ("county", "cbsa"),
                       cbsa_aggregation=cbsa, property_subtype=subtype)


FEATURES = (
    _source("population", "ACS five-year population estimate.", "population", "persons", source_ids=("census_acs",)),
    _source("households", "ACS five-year household estimate.", "households", "households", source_ids=("census_acs",)),
    _source("median_household_income", "ACS median household income; not aggregated from counties to CBSAs.", "median_household_income", "USD_current", source_ids=("census_acs",), cbsa="none"),
    _source("per_capita_income", "ACS per-capita income; not aggregated from counties to CBSAs.", "per_capita_income", "USD_current", source_ids=("census_acs",), cbsa="none"),
    _source("housing_units", "ACS housing-unit estimate.", "housing_units", "units", source_ids=("census_acs",)),
    _source("occupied_housing_units", "ACS occupied housing-unit estimate.", "occupied_housing_units", "units", source_ids=("census_acs",)),
    _source("vacant_housing_units", "ACS vacant housing-unit estimate.", "vacant_housing_units", "units", source_ids=("census_acs",)),
    _source("civilian_population_16_plus", "ACS civilian population age 16 and over.", "civilian_population_16_plus", "persons", source_ids=("census_acs",)),
    _source("personal_income", "BEA county personal income with source scaling retained.", "personal_income", "thousands_USD_current", source_ids=("bea_regional",)),
    _source("gdp", "BEA county gross domestic product with source scaling retained.", "gdp", "thousands_USD_current", source_ids=("bea_regional",)),
    _source("covered_employment", "BLS QCEW annual covered employment.", "covered_employment", "persons", source_ids=("bls_laus_ces",)),
    _source("housing_units_authorized", "Census annual housing units authorized.", "units_authorized_total", "units", source_ids=("census_bps",), frequencies=("annual",)),
    _source("multifamily_5plus_units_authorized", "Census annual five-plus-unit housing authorized.", "multifamily_5_plus_units_authorized", "units", source_ids=("census_bps",), frequencies=("annual",)),
    _source("fair_market_rent_2br", "HUD two-bedroom Fair Market Rent; never institutional asking rent.", "fair_market_rent", "USD_per_month", source_ids=("hud_public",), cbsa="none", subtype="two_bedroom"),
    FeatureSpec("population_growth_yoy", "Exact-period one-year population growth.", input_features=("population",), transformation="growth", frequencies=("annual", "quarterly"), unit="decimal_fraction"),
    FeatureSpec("population_growth_3y_cagr", "Exact-period three-year population CAGR.", input_features=("population",), transformation="cagr", frequencies=("annual", "quarterly"), unit="decimal_fraction", lag_periods=3),
    FeatureSpec("household_growth_yoy", "Exact-period one-year household growth.", input_features=("households",), transformation="growth", frequencies=("annual", "quarterly"), unit="decimal_fraction"),
    FeatureSpec("covered_employment_growth_yoy", "Exact-period one-year QCEW covered-employment growth.", input_features=("covered_employment",), transformation="growth", frequencies=("annual", "quarterly"), unit="decimal_fraction"),
    FeatureSpec("personal_income_growth_yoy", "Exact-period one-year personal-income growth.", input_features=("personal_income",), transformation="growth", frequencies=("annual", "quarterly"), unit="decimal_fraction"),
    FeatureSpec("housing_unit_growth_yoy", "Exact-period one-year housing-unit growth.", input_features=("housing_units",), transformation="growth", frequencies=("annual", "quarterly"), unit="decimal_fraction"),
    FeatureSpec("multifamily_5plus_units_growth_yoy", "Exact-period one-year growth in five-plus-unit authorizations.", input_features=("multifamily_5plus_units_authorized",), transformation="growth", frequencies=("annual",), unit="decimal_fraction"),
    FeatureSpec("fmr_2br_growth_yoy", "Exact-period growth in HUD two-bedroom FMR; not asking-rent growth.", input_features=("fair_market_rent_2br",), transformation="growth", frequencies=("annual", "quarterly"), geography_types=("county",), unit="decimal_fraction", cbsa_aggregation="none"),
    FeatureSpec("multifamily_permits_per_1000_population", "Five-plus-unit authorizations per 1,000 population.", input_features=("multifamily_5plus_units_authorized", "population"), transformation="ratio_per_1000", frequencies=("annual",), unit="units_per_1000_persons"),
    FeatureSpec("treasury_10y_mean", "Period mean of original-frequency 10-year Treasury observations.", input_metrics=("treasury_10y",), source_ids=("fred_public",), transformation="period_mean_broadcast", frequencies=("annual", "quarterly"), unit="percent", aggregation="mean", cbsa_aggregation="broadcast"),
    FeatureSpec("treasury_10y_period_end", "Last observed 10-year Treasury rate in the period.", input_metrics=("treasury_10y",), source_ids=("fred_public",), transformation="period_end_broadcast", frequencies=("annual", "quarterly"), unit="percent", aggregation="last_observation", cbsa_aggregation="broadcast"),
    FeatureSpec("treasury_10y_change_1y", "Exact one-year change in period-end 10-year Treasury rate.", input_features=("treasury_10y_period_end",), transformation="difference", frequencies=("annual", "quarterly"), unit="percentage_points"),
    FeatureSpec("treasury_10y_change_2q", "Exact two-quarter change in period-end 10-year Treasury rate.", input_features=("treasury_10y_period_end",), transformation="difference", frequencies=("quarterly",), unit="percentage_points", lag_periods=2),
    FeatureSpec("cpi_period_end", "Last observed CPI index level in the period.", input_metrics=("cpi",),
                source_ids=("fred_public",), transformation="period_end_broadcast",
                frequencies=("annual", "quarterly"), unit="index_1982_1984_100",
                aggregation="last_observation", cbsa_aggregation="broadcast"),
    FeatureSpec("cpi_growth_yoy", "Exact one-year growth in period-end CPI; no interpolation.",
                input_features=("cpi_period_end",), transformation="growth",
                frequencies=("annual", "quarterly"), unit="decimal_fraction"),
    FeatureSpec("population_growth_yoy_lag_1y", "Population growth lagged one year.", input_features=("population_growth_yoy",), transformation="lag", frequencies=("annual",), unit="decimal_fraction", lag_periods=1),
    FeatureSpec("multifamily_permits_per_1000_population_lag_1y", "Multifamily permitting intensity lagged one year.", input_features=("multifamily_permits_per_1000_population",), transformation="lag", frequencies=("annual",), unit="units_per_1000_persons", lag_periods=1),
    FeatureSpec("population_growth_yoy_lag_1q", "Population growth carried from annual evidence, then lagged one quarter.", input_features=("population_growth_yoy",), transformation="lag", frequencies=("quarterly",), unit="decimal_fraction", lag_periods=1),
    FeatureSpec("population_growth_yoy_lag_2q", "Population growth carried from annual evidence, then lagged two quarters.", input_features=("population_growth_yoy",), transformation="lag", frequencies=("quarterly",), unit="decimal_fraction", lag_periods=2),
    FeatureSpec("population_growth_yoy_lag_4q", "Population growth carried from annual evidence, then lagged four quarters.", input_features=("population_growth_yoy",), transformation="lag", frequencies=("quarterly",), unit="decimal_fraction", lag_periods=4),
    FeatureSpec("treasury_10y_change_2q_lag_1q", "Two-quarter Treasury change lagged one quarter.", input_features=("treasury_10y_change_2q",), transformation="lag", frequencies=("quarterly",), unit="percentage_points", lag_periods=1),
    FeatureSpec("treasury_10y_change_2q_lag_2q", "Two-quarter Treasury change lagged two quarters.", input_features=("treasury_10y_change_2q",), transformation="lag", frequencies=("quarterly",), unit="percentage_points", lag_periods=2),
)

FEATURE_REGISTRY = {item.name: item for item in FEATURES}


def registry_fingerprint() -> str:
    payload = [asdict(FEATURE_REGISTRY[name]) for name in sorted(FEATURE_REGISTRY)]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def specs_for(frequency: str, geography: str | None = None) -> tuple[FeatureSpec, ...]:
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("Milestone 3A supports annual and quarterly feature tables")
    if geography is not None and geography not in {"county", "cbsa"}:
        raise ValueError("feature geography must be county or cbsa")
    return tuple(spec for spec in FEATURES if frequency in spec.frequencies and (geography is None or geography in spec.geography_types))
