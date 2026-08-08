from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .schemas import sha256_value


def derive_annual_growth(rows, *, metric: str, output_metric: str, years: int = 1, transformation_version: str = "annual-growth/1.0.0"):
    """Yield growth rows without imputing gaps; input IDs are retained in methodology lineage."""
    groups = defaultdict(dict)
    for row in rows:
        if row["metric"] == metric and row["period_type"] == "annual":
            groups[(row["geography_type"], row["geography_id"])][int(str(row["observation_date"])[:4])] = row
    for values in groups.values():
        for year, current in sorted(values.items()):
            prior = values.get(year - years)
            if not prior or Decimal(str(prior["value"])) == 0:
                continue
            value = (Decimal(str(current["value"])) / Decimal(str(prior["value"]))) ** (Decimal(1) / years) - 1
            inputs = [prior["observation_id"], current["observation_id"]]
            yield {**current, "observation_id": None, "source_id": "test3_derived", "source_dataset": "derived_growth",
                   "source_series": f"{metric}:{years}y", "metric": output_metric, "value": format(value, "f"), "unit": "decimal_fraction",
                   "methodology": f"CAGR over {years} year(s); input_observation_ids={','.join(inputs)}; no missing-period imputation.",
                   "transformation_version": transformation_version, "raw_source_reference": "derived://" + sha256_value(inputs),
                   "raw_row_hash": "sha256:" + sha256_value(inputs), "normalized_row_hash": None}
