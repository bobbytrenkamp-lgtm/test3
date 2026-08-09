from __future__ import annotations

from dataclasses import dataclass


CORE_PROPERTY_TYPES = ("multifamily", "industrial", "office", "retail")


@dataclass(frozen=True)
class CREMetricSpec:
    metric: str
    property_types: tuple[str, ...]
    units_by_property_type: dict[str, tuple[str, ...]]
    measure_type: str
    minimum: float | None
    maximum: float | None
    jump_review_threshold: float | None
    methodologies: tuple[str, ...]
    description: str

    def units_for(self, property_type: str) -> tuple[str, ...]:
        return self.units_by_property_type.get(property_type, self.units_by_property_type.get("*", ()))


def _rate(metric, property_types=CORE_PROPERTY_TYPES, *, jump=.10, methodologies=("market_rate",)):
    return CREMetricSpec(metric, tuple(property_types), {"*": ("decimal_fraction",)}, "rate", 0, 1, jump,
                         methodologies, f"Governed {metric.replace('_', ' ')} rate; definition is source-specific and retained.")


def _level(metric, property_types=CORE_PROPERTY_TYPES, *, units=("units",), methodologies=("market_total",), jump=.50):
    return CREMetricSpec(metric, tuple(property_types), {"*": tuple(units)}, "level", 0, None, jump,
                         methodologies, f"Governed {metric.replace('_', ' ')} level.")


_RENT_UNITS = {
    "multifamily": ("USD_per_unit_month", "USD_per_sf_month"),
    "industrial": ("USD_per_sf_year",), "office": ("USD_per_sf_year",), "retail": ("USD_per_sf_year",),
}

CRE_METRICS = {item.metric: item for item in (
    CREMetricSpec("asking_rent", CORE_PROPERTY_TYPES, _RENT_UNITS, "level", 0, None, .35,
                  ("asking_rent", "gross_asking_rent", "net_asking_rent"), "Quoted asking rent; rent basis must be retained."),
    CREMetricSpec("effective_rent", ("multifamily", "industrial", "office"), _RENT_UNITS, "level", 0, None, .35,
                  ("effective_rent",), "Effective rent after the source's disclosed concession methodology."),
    CREMetricSpec("rent_growth_yoy", CORE_PROPERTY_TYPES, {"*": ("decimal_fraction",)}, "signed_rate", -1, 3, .25,
                  ("same_store_yoy", "market_yoy", "asking_rent_yoy", "effective_rent_yoy"), "Year-over-year rent growth."),
    CREMetricSpec("rent_growth_qoq", CORE_PROPERTY_TYPES, {"*": ("decimal_fraction",)}, "signed_rate", -1, 3, .15,
                  ("market_qoq", "asking_rent_qoq", "effective_rent_qoq"), "Quarter-over-quarter rent growth; not annualized."),
    _rate("vacancy_rate", methodologies=("market_vacancy", "physical_vacancy", "economic_vacancy")),
    _rate("occupancy_rate", ("multifamily",), methodologies=("physical_occupancy", "economic_occupancy")),
    _rate("availability_rate", ("industrial", "office", "retail"), methodologies=("market_availability",)),
    _rate("sublease_availability_rate", ("office",), methodologies=("sublease_availability",)),
    _rate("transaction_cap_rate", methodologies=("mean_transaction_cap_rate", "median_transaction_cap_rate", "market_cap_rate")),
    _rate("concession_rate", ("multifamily",), methodologies=("units_offering_concessions", "concession_value_pct_rent")),
    CREMetricSpec("net_absorption", CORE_PROPERTY_TYPES,
                  {"multifamily": ("units",), "industrial": ("sf",), "office": ("sf",), "retail": ("sf",)},
                  "flow", None, None, None, ("net_absorption",), "Period net absorption; negative values are permitted."),
    CREMetricSpec("deliveries", CORE_PROPERTY_TYPES,
                  {"multifamily": ("units",), "industrial": ("sf",), "office": ("sf",), "retail": ("sf",)},
                  "flow", 0, None, .50, ("completed_new_supply",), "Completed new supply during the period."),
    CREMetricSpec("under_construction", CORE_PROPERTY_TYPES,
                  {"multifamily": ("units",), "industrial": ("sf",), "office": ("sf",), "retail": ("sf",)},
                  "level", 0, None, .50, ("under_construction",), "Construction pipeline at period end."),
    CREMetricSpec("inventory", CORE_PROPERTY_TYPES,
                  {"multifamily": ("units",), "industrial": ("sf",), "office": ("sf",), "retail": ("sf",)},
                  "level", 0, None, .50, ("market_inventory",), "Market inventory at period end."),
    _level("transaction_volume", units=("USD", "transactions"), methodologies=("transaction_volume",)),
    CREMetricSpec("sale_price_per_unit", ("multifamily",), {"*": ("USD_per_unit",)}, "level", 0, None, .50,
                  ("mean_sale_price", "median_sale_price"), "Transaction price per multifamily unit."),
    CREMetricSpec("sale_price_per_sf", ("industrial", "office", "retail"), {"*": ("USD_per_sf",)}, "level", 0, None, .50,
                  ("mean_sale_price", "median_sale_price"), "Transaction price per square foot."),
)}


def get_cre_metric(metric: str, property_type: str) -> CREMetricSpec:
    try:
        spec = CRE_METRICS[metric]
    except KeyError as exc:
        raise ValueError(f"unsupported CRE metric: {metric}") from exc
    if property_type not in spec.property_types:
        raise ValueError(f"{metric} is not governed for property type {property_type}")
    return spec
