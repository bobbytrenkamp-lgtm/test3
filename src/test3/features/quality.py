from __future__ import annotations

from pathlib import Path

import duckdb

from test3.warehouse.duckdb_engine import sql_literal


class FeatureQualityError(ValueError):
    """Raised when an analytical feature snapshot would be unsafe to publish."""


def profile_feature_files(panel_path: Path, lineage_path: Path, *, frequency: str) -> dict:
    with duckdb.connect(":memory:") as db:
        db.execute("SET enable_progress_bar=false")
        columns = [row[0] for row in db.execute(f"DESCRIBE SELECT * FROM read_parquet({sql_literal(str(panel_path))})").fetchall()]
        dimensions = {"geography_type", "geography_id", "state_fips", "county_fips", "cbsa", "period_start", "year", "quarter"}
        feature_columns = [name for name in columns if name not in dimensions and not name.endswith("__available_at")]
        counts_sql = ",".join(f'count("{name}")' for name in feature_columns)
        counts = db.execute(f"SELECT {counts_sql} FROM read_parquet({sql_literal(str(panel_path))})").fetchone() if feature_columns else ()
        panel = db.execute(f"""SELECT count(*), count(DISTINCT geography_id), min(period_start), max(period_start)
            FROM read_parquet({sql_literal(str(panel_path))})""").fetchone()
        lineage = db.execute(f"""SELECT count(*), count(DISTINCT lineage_id),
            count(*) - count(DISTINCT geography_type || '|' || geography_id || '|' || CAST(period_start AS VARCHAR) || '|' || feature_name),
            count(*) FILTER (WHERE NOT isfinite(value)),
            count(*) FILTER (WHERE input_observation_ids_json='[]' AND input_feature_lineage_ids_json='[]'),
            count(*) FILTER (WHERE transformation LIKE '%missing_to_zero%' OR transformation LIKE '%linear_interpolation%')
            FROM read_parquet({sql_literal(str(lineage_path))})""").fetchone()
        bad_periods = db.execute(f"""SELECT count(*) FROM read_parquet({sql_literal(str(panel_path))})
            WHERE CASE WHEN ?='annual' THEN month(period_start)<>1
                       ELSE month(period_start) NOT IN (1,4,7,10) END""", [frequency]).fetchone()[0]
    diagnostics = {
        "panel_rows": panel[0], "geographies": panel[1], "earliest": panel[2], "latest": panel[3],
        "feature_values": lineage[0], "unique_lineage_ids": lineage[1], "duplicate_feature_keys": lineage[2],
        "non_finite_values": lineage[3], "unlinked_values": lineage[4],
        "forbidden_imputation_labels": lineage[5], "invalid_period_starts": bad_periods,
        "feature_non_null_counts": dict(zip(feature_columns, counts, strict=True)),
    }
    failures = [name for name in ("duplicate_feature_keys", "non_finite_values", "unlinked_values",
                                   "forbidden_imputation_labels", "invalid_period_starts") if diagnostics[name]]
    if not panel[0] or not lineage[0]:
        failures.append("empty_feature_table")
    if lineage[0] != lineage[1]:
        failures.append("duplicate_lineage_ids")
    if failures:
        raise FeatureQualityError("feature quality validation failed: " + ", ".join(failures))
    return diagnostics
