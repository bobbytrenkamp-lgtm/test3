from __future__ import annotations

from .frequency import lagged_period


def add_lagged_values(rows: list[dict], *, feature: str, lag_periods: int, frequency: str, output_feature: str) -> list[dict]:
    """Small deterministic utility for tests/research; production panels use equivalent DuckDB SQL."""
    keyed = {(row["geography_id"], row["period_start"]): row for row in rows if row["feature_name"] == feature}
    output = []
    for geography_id, current_period in sorted({(row["geography_id"], row["period_start"]) for row in rows}):
        prior = keyed.get((geography_id, lagged_period(current_period, frequency, lag_periods)))
        if prior is not None:
            output.append({**prior, "feature_name": output_feature, "period_start": current_period,
                           "input_feature_lineage_ids": [prior["lineage_id"]]})
    return output
