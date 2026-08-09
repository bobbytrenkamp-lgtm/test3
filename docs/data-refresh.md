# Warehouse refresh operations

`test3-data refresh` performs a governed local refresh. `--dry-run` reports the official URLs and request contract without downloading. `--source all` covers Census, BLS, BEA, Federal Reserve macro data, Building Permits, the Census/OMB crosswalk, and HUD FMR history.

Multi-partition refreshes continue after an isolated partition error, emit a structured error for that request, and exit nonzero if any partition failed. Successful partitions remain validated and restart idempotently. The client never loops or retries automatically. Census and Building Permits partition by year; macro series and Census variables have separate dataset identities.

`test3-data status` verifies manifests and Parquet hashes and includes refresh history and quality. `test3-data coverage` aggregates actual rows, distinct geographies, datasets, frequency, and dates by source and metric. `test3-data lineage OBSERVATION_ID` returns the canonical row, raw metadata, source reference, manifest, and transformation version.

Workflow state is local SQLite in `warehouse_refresh_runs`; analytical values remain in Parquet. States are `running`, `succeeded`, `unchanged`, `failed`, and `cancelled`. Failed history is retained. Identical bytes under the same request and normalizer contract are `unchanged`; changed content or transformations create a new recoverable version. There is no overwrite-oriented `--force` option.

Downloaded data remains under Git-ignored `data/warehouse/`.
