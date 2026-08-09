# Historical CRE target data

## Implemented scope

Phase A supports long-form multifamily, industrial, office, and retail observations. Governed targets currently cover asking/effective rent where defined, YoY/QoQ rent growth, vacancy, occupancy, availability, office sublease availability, absorption, deliveries, construction, inventory, concessions, cap rates, transaction volume, and property-type-appropriate transaction pricing.

Metric definitions are property-type aware. Multifamily rent may use `USD_per_unit_month` or `USD_per_sf_month`; industrial, office, and retail rent uses `USD_per_sf_year`. Multifamily quantities use units while other property types commonly use square feet. Incompatible combinations fail instead of being coerced.

## Import contract

Required CSV fields are:

`market, geography_type, geography_id, period, frequency, property_type, metric, value, unit, source_name, source_identifier, source_period, retrieved_at, methodology, vintage, licensing_notes, verification_status`

Recommended optional fields are:

`state_fips, county_fips, cbsa, submarket, property_subtype, release_date, redistribution_permitted, source_class, sample_count, notes`

Use local files that you are authorized to analyze. Numeric observations and citations may be retained, but report prose and copyrighted layouts should not be copied into the repository. Brokerage or academic material has no blanket permission: record the actual license/usage basis for each import.

```powershell
test3-data verify-cre --input market-history.csv --forecast-origin 2020-12-31
test3-data import-cre --input market-history.csv --dataset raleigh-mf-history --version 2026-08-09-v1 --analyst-reviewed
test3-data cre-status
test3-research target-readiness --data-root data
test3-research build-target-panel --data-root data --property-type multifamily --target rent_growth_yoy --frequency quarterly
```

`verify-cre` does not publish. `import-cre` creates a new immutable version and refuses to overwrite an existing one. Missing observations remain missing. Rejected and duplicate observations are not published; unverified but structurally valid evidence may be retained, but is not model-eligible.

Target-panel publication additionally excludes unresolved source conflicts, methodology conflicts and multiple source candidates for the same market-period. An analyst must resolve the controlling source explicitly; Test3 never averages or silently chooses those records.

## Current data limitations

The repository contains no copyrighted brokerage history and no claimed validated CRE target dataset. Only fictional test fixtures exercise the pipeline. No forecasting model may be described as validated until legitimate historical targets are imported, verified, and tested out of sample.
