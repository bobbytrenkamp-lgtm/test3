# Public data ingestion

Test3 retrieves official public data through source-specific, HTTPS-only adapters. The client enforces official-host allowlists, bounded time and response size, restricted redirects, a descriptive user agent, process-wide per-host throttling, no cookies, no credentials, and no automatic retry storm. It is not an arbitrary URL downloader.

The publication path is: official response -> immutable raw bytes and metadata -> deterministic source normalizer -> canonical validation -> Zstandard Parquet -> content-hashed immutable manifest -> verified DuckDB read. A failed refresh is recorded in SQLite and cannot replace the prior active version. Version identity includes response bytes, the governed request, and the normalizer version; identical acquisitions remain `unchanged` across days.

| Source | Collection | Geography | Frequency | Important limitation |
|---|---|---|---|---|
| Census ACS 5-year | Population, households, income, housing occupancy, and selected demographics | State, county, place | Annual | Estimates represent multi-year samples. Credential-free table files are consistently available for the current table-based era; older releases may require an official local file. |
| BLS LAUS/QCEW | LAUS employment and unemployment; QCEW covered employment, establishments, wages, and pay | US, state, county | Monthly or annual | BLS may return 403/503 to automated clients. Test3 records the failure and supports an exact-URL, size-bounded local official file without bypassing BLS controls. |
| BEA Regional | Personal income, per-capita income, population, GDP | State, county | Annual | Current-dollar scaling is retained; suppressed values are omitted, never zero-filled. |
| Federal Reserve public CSV | Fed funds, SOFR, Treasury rates, mortgage rate, CPI | US | Original daily, weekly, or monthly | No ingestion-time aggregation occurs. Series distribution terms can differ. |
| Census Building Permits | Permits and authorized units by structure size | County where reported | Annual | Permit-issuing areas are not treated as counties without an explicit crosswalk. |
| Census/OMB delineations | County membership in CBSAs | County and CBSA | Irregular vintage | Membership is effective-date and vintage specific. Non-CBSA counties are not inferred. |
| HUD FMR history | Fiscal-year Fair Market Rents by bedroom count | County and county subdivision | Annual, 1983-present | New England county subdivisions remain distinct; FMR is a 40th-percentile program rent, not observed asking rent. |

No adapter requires an account, API key, payment method, cloud resource, or billable plan. As of May 2026, Census Data API calls require a key, so Test3 uses credential-free official table files instead.

```text
test3-data refresh --source census --from-year 2021 --to-year 2024 --geography county
test3-data refresh --source bls --to-year 2024
test3-data refresh --source bea
test3-data refresh --source fred --series DGS10
test3-data refresh --source building_permits --from-year 2000 --to-year 2024
test3-data refresh --source crosswalk --vintage 2023
test3-data refresh --source hud
```

If BLS blocks automation, download the linked official annual county workbook in a normal browser and preserve it with:

```text
test3-data refresh --source bls --annual-county --from-year 2025 --to-year 2025 \
  --local-file C:\Downloads\laucnty25.xlsx \
  --source-url https://www.bls.gov/lau/laucnty25.xlsx
```

The file is copied into immutable raw storage, hashed, schema validated, normalized, and source-linked. An arbitrary URL, wrong host, empty file, oversized file, or changed schema fails closed. Correctness tests use committed fictional fixtures; live probes remain separate operational evidence.
