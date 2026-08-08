from __future__ import annotations

from pathlib import Path
from typing import Iterable

import duckdb

from .schemas import CANONICAL_COLUMNS
from .storage import WarehousePaths


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class WarehouseEngine:
    def __init__(self, paths: WarehousePaths):
        self.paths = paths

    def parquet_files(self) -> list[Path]:
        normalized = self.paths.contained("normalized")
        return sorted(normalized.rglob("*.parquet")) if normalized.exists() else []

    def query_observations(self, *, metrics: Iterable[str] | None = None, geography_id: str | None = None,
                           columns: Iterable[str] = CANONICAL_COLUMNS, limit: int = 1000) -> list[dict]:
        selected = tuple(columns)
        if not selected or set(selected) - set(CANONICAL_COLUMNS):
            raise ValueError("columns must be canonical observation columns")
        if limit < 1 or limit > 100_000:
            raise ValueError("limit must be between 1 and 100000")
        files = [str(path) for path in self.parquet_files()]
        if not files:
            return []
        clauses, params = [], []
        if metrics:
            values = tuple(metrics)
            if not values:
                return []
            clauses.append("metric IN (" + ",".join("?" for _ in values) + ")")
            params.extend(values)
        if geography_id is not None:
            clauses.append("geography_id = ?")
            params.append(geography_id)
        source = "read_parquet([" + ",".join(sql_literal(item) for item in files) + "])"
        sql = f"SELECT {','.join(selected)} FROM {source}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY observation_date, observation_id LIMIT ?"
        params.append(limit)
        with duckdb.connect(":memory:") as connection:
            result = connection.execute(sql, params)
            names = [item[0] for item in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

    def summary(self) -> dict:
        files = self.parquet_files()
        if not files:
            return {"files": 0, "rows": 0, "metrics": 0, "earliest": None, "latest": None}
        source = "read_parquet([" + ",".join(sql_literal(str(item)) for item in files) + "])"
        with duckdb.connect(":memory:") as connection:
            row = connection.execute(f"SELECT count(*), count(DISTINCT metric), min(observation_date), max(observation_date) FROM {source}").fetchone()
        return {"files": len(files), "rows": row[0], "metrics": row[1], "earliest": row[2], "latest": row[3]}
