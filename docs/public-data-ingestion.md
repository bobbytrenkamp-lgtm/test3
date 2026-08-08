# Public data ingestion

Test3 retrieves official public data through source-specific, HTTPS-only adapters. The client has explicit host allowlists, a 30-second timeout, a 256 MiB response ceiling, bounded redirects, a descriptive user agent, no cookies, no credentials and no unbounded retries. It is not an arbitrary URL downloader.

The publication path is: official response → immutable raw bytes and metadata → deterministic source normalizer → canonical validation → Zstandard Parquet → content-hashed immutable manifest → verified DuckDB read. A failed refresh is recorded in SQLite and cannot replace the prior active version.

| Source | Initial collection | Geography | Frequency | Important limitation |
|---|---|---|---|---|
| Census ACS 5-year | Population, households, income, housing occupancy, selected demographics | State, county, place | Annual | Estimates represent multi-year samples, not single-year point measurements. |
| BLS | National labor series through registration-free API v1; county LAUS through bounded state files | US and county | Monthly | A distribution endpoint may be temporarily unavailable; failures stay logged and prior data stays active. |
| BEA Regional | Personal income, per-capita income, population, GDP | State, county | Annual | Current-dollar scaling is retained; suppressed values are omitted, never zero-filled. |
| Federal Reserve public CSV | Fed funds, SOFR, 2/5/10/30-year Treasuries, mortgage rate, CPI | US | Original daily, weekly or monthly | No ingestion-time aggregation occurs. Series distribution terms can differ. |
| Census Building Permits | Permits and authorized units by structure size | County where reported | Annual | Permit-issuing areas are not treated as counties without an explicit crosswalk. |

No source requires an account, API key, payment method or billable plan. Source-specific distribution terms should still be reviewed before redistribution.

As of May 2026, Census requires a key for all Data API calls. Test3 does not request that credential; it uses official `www2.census.gov` table-based ACS summary files. BLS uses registration-free API v1 for the national baseline, and never requires v2 registration.

```text
test3-data refresh --source census --from-year 2019 --to-year 2024 --geography county
test3-data refresh --source bls --from-year 1990 --to-year 2025
test3-data refresh --source bea --table CAINC1 --from-year 1969
test3-data refresh --source fred --series DGS10
test3-data refresh --source building_permits --from-year 2019 --to-year 2024
```

Correctness tests use committed fictional response fixtures. Live downloads are operational validation, not a test-suite dependency.

`--state 37` selects a bounded BLS LAUS state file. If the BLS bulk host rejects automated retrieval, retain the failed run and use a legally downloaded copy with the deterministic parser rather than bypassing source access controls.
