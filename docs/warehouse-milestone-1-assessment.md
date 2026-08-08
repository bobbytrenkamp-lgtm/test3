# Warehouse milestone 1 implementation assessment

## Existing capabilities to preserve

Test3 already has a strong local-first application layer: SQLite migrations and immutable audit events; deals, documents, extraction candidates, citations, reconciliation and analyst approval; Test1 snapshot ingestion; governed Test2 exports; assumption observations, benchmarks, correlations, lags, regimes, walk-forward baselines, model artifacts and recommendation governance. These are retained.

## Reuse and refactoring boundary

SQLite remains the system of record for identity, workflow, approvals, audit history, source metadata and model governance. Existing assumption modules remain the governed application and recommendation layer. They should progressively consume analysis-ready warehouse views rather than being copied or replaced. Test1 remains the upstream geography and policy system; Test2 remains the downstream underwriting system.

The new boundary is analytical storage. High-volume observations do not belong in the application SQLite database or Python lists. They are persisted as immutable, versioned Parquet snapshots and queried through embedded DuckDB with projection and predicate pushdown.

## Genuine additions in this milestone

Milestone 1 adds the canonical lineage-rich observation schema, governed source catalog, full warehouse directory contract, batch Parquet ingestion, DuckDB queries, immutable content-hashed manifests, validation/profile controls, strict temporal and geography validation, a local `test3-data` CLI, synthetic fixtures and tests. No remote data downloader or paid service is activated.

Later milestones will add source-specific public-data normalizers, governed geographic crosswalk datasets, feature-table builders, research models and UI consumers on this foundation.
