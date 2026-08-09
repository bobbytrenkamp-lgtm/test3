# CRE target panels

`test3-research target-readiness --data-root data` reads immutable CRE verification reports and reports actual coverage by property type and target. The default starting gates are five markets, twenty periods and one hundred model-eligible observations. These are governance minimums, not universal statistical claims.

`test3-research build-target-panel --data-root data --property-type multifamily --target rent_growth_yoy --frequency quarterly` joins analyst-approved targets to the latest verified county or CBSA feature panel. The output is immutable Parquet under `data/warehouse/research/target_panels/` with a content-hashed manifest.

Rows are excluded when they are unreviewed, rejected, duplicated, affected by an unresolved source or methodology conflict, lack a supported feature geography, use an unsupported frequency, or have no matching feature period. Multiple sources for one market-period are never averaged or selected implicitly. Target availability uses the disclosed release date; when it is absent, the recorded retrieval date is the conservative fallback.

Census HVS rental vacancy and HUD Fair Market Rent never enter this path because the target builder reads only analyst-reviewed CRE import verification records. HVS remains residential context, and FMR remains an affordability measure.

The manifest retains target-file hashes, target warehouse-manifest hashes, feature-manifest hashes, upstream source-manifest hashes, exclusions and the exact joined-row hash. Missing feature values remain null. Model preparation performs complete-case exclusion and never substitutes zero.
