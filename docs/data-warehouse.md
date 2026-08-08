# Local analytical warehouse

Test3 separates application state from analytical data:

- SQLite owns workflow, approvals, provenance metadata, audit history and model governance.
- Apache Parquet owns immutable analytical dataset snapshots.
- embedded DuckDB reads Parquet directly and applies column projection and filter pushdown without loading an entire dataset into Python memory.

Run `test3-data --data-root data init` to create the local structure. `test3-data catalog`, `status` and `summary` return machine-readable JSON. No account, key, network service or payment method is involved.

## Snapshot publication

Ingestion validates and batches canonical observations into a temporary DuckDB table, rejects duplicate identifiers, writes Zstandard-compressed Parquet, verifies its row count, atomically publishes it, then publishes an immutable manifest containing content hashes. A failed version never receives a manifest. An existing version is never overwritten or deleted.

Every analytical query verifies manifest integrity, the governed source-definition fingerprint, file size and Parquet SHA-256 first. Queries select only the newest validated version of each source/dataset pair, preventing revisions from being double-counted. `test3-data status` performs the same verification and fails closed on tampering or orphaned metadata.

Large runtime datasets under `data/warehouse/` are ignored by Git. Only schemas, catalog definitions, documentation and explicitly fictional fixtures are committed.

## Canonical lineage

Every observation carries source, dataset, series and version identifiers; retrieval and as-of dates; stable geography fields; original frequency; metric, unit and value; quality/methodology metadata; a raw source reference; and raw and normalized row hashes. Annual data remains annual. Missing data remains null; it is never changed to zero or silently forward-filled.

The implemented scope and reuse decisions are recorded in [warehouse-milestone-1-assessment.md](warehouse-milestone-1-assessment.md).
