#!/usr/bin/env python3
"""Opt-in local warehouse load benchmark; no network and no committed output."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import tempfile
import time

from test3.warehouse.ingestion import ingest_observations
from test3.warehouse.schemas import sha256_value
from test3.warehouse.storage import WarehousePaths


def rows(count):
    for index in range(count):
        raw = {"index": index}
        yield {"observation_id": None, "source_id": "user_import", "source_dataset": "synthetic_load_benchmark",
               "source_series": "fixture", "source_version": "benchmark-v1", "retrieved_at": datetime.now(timezone.utc).isoformat(),
               "as_of_date": None, "geography_type": "county", "geography_id": f"{index % 99999:05d}", "state_fips": None,
               "county_fips": None, "cbsa": None, "city": None, "submarket": None, "property_type": None,
               "property_subtype": None, "observation_date": f"{2000 + index % 25}", "period_type": "annual",
               "metric": "synthetic_value", "value": str(index), "unit": "index", "currency": None, "sample_count": None,
               "quality_level": "unknown", "methodology": "Synthetic performance fixture.", "transformation_version": "benchmark/1.0",
               "raw_source_reference": f"fixture://benchmark/{index}", "raw_row_hash": "sha256:" + sha256_value(raw), "normalized_row_hash": None}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--rows", type=int, default=100_000); args = parser.parse_args()
    if not 1 <= args.rows <= 1_000_000: raise SystemExit("--rows must be between 1 and 1000000")
    with tempfile.TemporaryDirectory() as root:
        started = time.perf_counter(); result = ingest_observations(WarehousePaths.from_data_root(root), source_id="user_import",
            dataset_id="synthetic_load_benchmark", source_version="benchmark-v1", domain="demographics", rows=rows(args.rows))
        elapsed = time.perf_counter() - started
        print({"rows": result.row_count, "seconds": round(elapsed, 3), "rows_per_second": round(result.row_count / elapsed, 1), "claim": "measured local run only"})


if __name__ == "__main__": main()
