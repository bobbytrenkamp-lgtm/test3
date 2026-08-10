# Historical CRE target data

## Implemented scope

Phase A supports long-form multifamily, industrial, office, and retail observations. Governed targets currently cover asking/effective rent where defined, YoY/QoQ rent growth, vacancy, occupancy, availability, office sublease availability, absorption, deliveries, construction, inventory, concessions, cap rates, transaction volume, and property-type-appropriate transaction pricing.

Metric definitions are property-type aware. Multifamily rent may use `USD_per_unit_month` or `USD_per_sf_month`; industrial, office, and retail rent uses `USD_per_sf_year`. Multifamily quantities use units while other property types commonly use square feet. Incompatible combinations fail instead of being coerced.

## Import contract

Canonical CSV, XLSX, and Parquet files are supported. Required canonical fields are:

`market, geography_type, geography_id, period, frequency, property_type, metric, value, unit, source_name, source_identifier, source_period, retrieved_at, methodology, vintage, licensing_notes, verification_status`

Recommended optional fields are:

`state_fips, county_fips, cbsa, submarket, property_subtype, release_date, redistribution_permitted, source_class, sample_count, notes`

Use local files that you are authorized to analyze. Numeric observations and citations may be retained, but report prose and copyrighted layouts should not be copied into the repository. Brokerage or academic material has no blanket permission: record the actual license/usage basis for each import.

```powershell
test3-data verify-cre --input market-history.csv --forecast-origin 2020-12-31
test3-data import-cre --input market-history.csv --dataset raleigh-mf-history --version 2026-08-09-v1 --analyst-reviewed
test3-data import-cre --input quarterly-export.xlsx --mapping data/warehouse/manifests/cre_import_mappings/vendor-a/1.0-<hash>.json --dataset vendor-a-mf --version 2026q2 --analyst-reviewed
test3-data cre-status
test3-data cre-source-catalog
test3-data cre-source-discovery
test3-data cre-target-audit
test3-data cre-target-funnel --property-type multifamily --metric rent_growth_yoy
test3-data cre-coverage-matrix --property-type multifamily --metric rent_growth_yoy
test3-data discover-cre-reports
test3-data import-cre-bulk --input-folder data/authorized_market_history --dataset-prefix authorized-history --version-prefix 2026q2 --mapping <mapping.json> --analyst-reviewed
test3-research target-readiness --data-root data
test3-research target-readiness --data-root data --model-specification mf_rent_growth_combined
test3-research build-target-panel --data-root data --property-type multifamily --target rent_growth_yoy --frequency quarterly
```

`verify-cre` does not publish. `import-cre` creates a new immutable version and refuses to overwrite an existing one. Missing observations remain missing. Rejected and duplicate observations are not published; unverified but structurally valid evidence may be retained, but is not model-eligible.

Target-panel publication additionally excludes unresolved source conflicts, methodology conflicts and multiple source candidates for the same market-period. An analyst must resolve the controlling source explicitly; Test3 never averages or silently chooses those records.

Saved import mappings require an exact input-column match before reuse. They are content-hashed and stored locally under `data/warehouse/manifests/cre_import_mappings/`. Market definitions are also content-hashed and versioned locally; weighted constituent counties must total one. If market definitions exist, an imported market that lacks a governed definition is not model-eligible.

Reviewed document candidates retain document SHA-256, page, table, row, column, original label, and original value. Candidate packages cannot approve themselves. An analyst must select observations and record a rationale before the canonical import/verification path can consider them.

The ignored `data/cre_reports/inbox/` is a local intake directory for lawfully obtained PDF/CSV/XLSX/Parquet reports. Discovery fingerprints files, counts PDF pages, infers candidate source/market/quarter/property type from filenames, groups likely quarterly series, and reports missing quarters. It does not parse rights, approve observations, or make them model eligible. Each discovery result is content-hashed under the ignored `data/cre_reports/manifests/` directory.

Recurring extracted tables support exact versioned label profiles. Schema drift returns `review_required` and zero candidates. Wide and label/value table candidates retain the original cell evidence. Exact YoY rent growth may be derived only from a same-source, same-geography, same-unit, same-methodology quarterly rent pair four quarters apart. Vacancy may be derived as `1 - occupancy` only for explicitly physical/economic occupancy—not availability. Derived rows remain unverified pending analyst review.

## Current data limitations

The repository contains no copyrighted brokerage history and no claimed validated CRE target dataset. Only fictional test fixtures exercise the pipeline. No forecasting model may be described as validated until legitimate historical targets are imported, verified, and tested out of sample.
