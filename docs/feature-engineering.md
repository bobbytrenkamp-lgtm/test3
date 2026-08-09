# Governed feature engineering

Test3 converts active, integrity-verified canonical observations into immutable DuckDB-built Parquet panels. It does not load the analytical warehouse into Python memory.

## Tables

Milestone 3A supports `county_year`, `county_quarter`, `cbsa_year`, and `cbsa_quarter`. A table is published only when its evidence produces at least one valid geography-period row. Empty or invalid builds fail before publication. Market and property-type panels require governed CRE target data and are deferred to Milestone 3B.

Each version contains:

- `panel.parquet`: one wide row per geography and period;
- `lineage.parquet`: one row per non-null feature value;
- `feature_manifest.json`: input manifest hashes, registry hash, builder version, output hashes, coverage, quality diagnostics and limitations.

Every feature column has a companion `<feature>__available_at` date and every lineage node carries the same availability boundary. Later walk-forward code must exclude values whose availability date is after the forecast origin. Historical public snapshots acquired today do not prove that a value was available in the same form at an earlier vintage; the preserved date makes that limitation testable rather than hidden.

The version identifier hashes the complete active input-manifest set, registry, builder, geography and frequency. Every manifest freezes each feature definition together with its exact contributing source, dataset, source-version and manifest hashes. Rebuilding identical inputs returns `unchanged`; it never overwrites the prior version.

## Frequency rules

Annual source levels can enter annual panels directly. Selected annual level estimates may enter quarterly panels only through the labeled `annual_carry_forward` transformation. This is a modeling alignment convenience, not a claim that Census, BEA, BLS or HUD published quarterly observations. No interpolation occurs.

Original-frequency Treasury observations produce separate period-mean and period-end features. Growth and difference features require an exact comparison period. If either period is absent, the derived value is absent. Missing values remain Parquet nulls and are never replaced with zero.

Annual permit flows remain annual and are not copied into quarterly panels. HUD two-bedroom Fair Market Rent is named `fair_market_rent_2br` and its growth is `fmr_2br_growth_yoy`; neither is institutional asking rent or asking-rent growth.

## Geography

County values retain five-digit FIPS identifiers. CBSA additive levels are sums of counties connected by an official active Census/OMB membership observation. The lineage records both county feature nodes and crosswalk observation IDs. The current implementation applies the latest active source-backed OMB vintage to the table and discloses that historical CBSA boundaries are not reconstructed. Non-additive county values such as median household income and HUD FMR are not summed into CBSAs.

## Lineage

Direct and frequency-aligned values record canonical observation IDs and source manifest hashes. Aggregations and derived features record parent feature-lineage IDs. `FeaturePanel.trace_lineage()` resolves the bounded DAG back to all original observation and manifest identifiers. This avoids duplicating large evidence arrays while preserving complete reproducibility.

## Commands

```powershell
test3-data build-features --geography county --frequency annual
test3-data build-features --geography county --frequency quarterly
test3-data build-features --geography cbsa --frequency annual
test3-data build-features --geography cbsa --frequency quarterly
test3-data feature-status
```

All output is local and machine-readable. Feature construction uses only the existing MIT-licensed embedded DuckDB dependency and local Parquet files.

## Measured local build evidence

On 2026-08-09, builder 1.4.0 produced the following from the active 2.1-million-observation development warehouse. These are local measurements, not general performance guarantees. CBSA lineage counts include the retained county evidence nodes needed to resolve every aggregate recursively.

| Table | Panel rows | Lineage nodes | Geographies | Observed periods | Build time |
|---|---:|---:|---:|---|---:|
| county_year | 186,094 | 1,580,656 | 3,293 | 1969–2026 | 27.7 s |
| county_quarter | 743,916 | 7,780,534 | 3,287 | 1969 Q1–2026 Q4 | 170.3 s |
| cbsa_year | 51,294 | 851,090 | 935 | 1969–2024 | 22.6 s |
| cbsa_quarter | 204,756 | 3,162,804 | 935 | 1969 Q1–2024 Q4 | 67.5 s |

All four final manifests reported zero duplicate feature keys, non-finite values, unlinked lineage nodes, forbidden imputation labels, and invalid period starts. A real 40-county CBSA population aggregate resolved through 41 feature nodes to 80 source/crosswalk observations in 0.269 seconds. The 2026 Q4 county period reflects explicitly carried annual fiscal-year evidence, not a claim that Q4 was observed; its feature-specific availability date remains attached so forecast-origin filters can prevent look-ahead.
