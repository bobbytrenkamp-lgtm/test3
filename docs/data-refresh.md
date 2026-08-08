# Warehouse refresh operations

`test3-data refresh` performs a governed local refresh. `--dry-run` reports the official URLs and request contract without downloading. `--source all` processes the five Tier 1 adapters. Census and Building Permits are partitioned by year; each macro series has its own dataset partition.

`test3-data status` verifies manifests and Parquet hashes and includes refresh history and quality. `test3-data coverage` reports actual rows, distinct geographies, frequency and dates. `test3-data lineage OBSERVATION_ID` returns the canonical row, raw metadata, source reference, manifest and transformation.

Workflow state is local SQLite in `warehouse_refresh_runs`; analytical values remain in Parquet. States are `running`, `succeeded`, `unchanged`, `failed` and `cancelled`. Failed history is retained. Identical content is `unchanged`. There is no overwrite-oriented `--force` option.

Downloaded data remains under Git-ignored `data/warehouse/`.
