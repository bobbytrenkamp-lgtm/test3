# CRE research data architecture

Test3 uses two storage planes.

SQLite remains the application and governance store for users, deals, review decisions, audit events, assumption runs, and compact workflow metadata. It is not the analytical warehouse.

DuckDB and immutable Parquet snapshots hold historical analytical observations. Original local CRE files are preserved under `data/warehouse/raw/user_imports/`; normalized observations are stored under `data/warehouse/normalized/cre_market/`; content-addressed source manifests remain under `data/warehouse/manifests/`; and companion verification reports are stored under `data/warehouse/verification/cre/`.

The publication sequence is:

```text
authorized local CSV
  -> structural and semantic validation
  -> cross-row verification
  -> immutable raw snapshot
  -> canonical observations
  -> immutable Parquet + manifest
  -> companion verification report
  -> later panel assembly
```

No report downloader, web scraper, hosted database, cloud storage, or paid API is part of this path.
