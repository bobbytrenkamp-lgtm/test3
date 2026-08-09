from __future__ import annotations

import duckdb

from .duckdb_engine import WarehouseEngine, sql_literal


def coverage_report(paths) -> list[dict]:
    files = WarehouseEngine(paths).parquet_files()
    if not files:
        return []
    source = "read_parquet([" + ",".join(sql_literal(str(path)) for path in files) + "])"
    with duckdb.connect(":memory:") as db:
        result = db.execute(f"""SELECT source_id,metric,geography_type,period_type,
            min(observation_date) earliest,max(observation_date) latest,count(*) observations,
            count(DISTINCT geography_id) geographies,count(DISTINCT source_dataset) datasets FROM {source}
            GROUP BY ALL ORDER BY source_id,metric,geography_type,period_type""")
        names = [item[0] for item in result.description]
        return [dict(zip(names, row, strict=True)) for row in result.fetchall()]
