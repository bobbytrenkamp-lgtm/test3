from __future__ import annotations

from pathlib import Path

import duckdb

from .duckdb_engine import sql_literal


def profile_parquet(path: str | Path) -> dict:
    resolved = Path(path).resolve()
    with duckdb.connect(":memory:") as connection:
        row = connection.execute(
            f"""SELECT count(*) AS row_count, count(DISTINCT observation_id) AS unique_rows,
            count(*) FILTER (WHERE value IS NULL) AS null_values,
            min(observation_date), max(observation_date), count(DISTINCT geography_id), count(DISTINCT metric)
            FROM read_parquet({sql_literal(str(resolved))})"""
        ).fetchone()
    return {"rows": row[0], "unique_observation_ids": row[1], "null_values": row[2], "earliest": row[3],
            "latest": row[4], "geographies": row[5], "metrics": row[6]}
