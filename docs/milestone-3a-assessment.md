# Milestone 3A implementation assessment

## Existing capabilities reused

The canonical observation schema, active immutable manifests, Parquet integrity verification, DuckDB file projection, metric catalog, exact annual-growth convention, official county-to-CBSA membership observations, and warehouse path containment remain authoritative. The existing assumptions package already provides descriptive benchmarks, correlation and exploratory lead/lag analysis, walk-forward naive baselines, model-artifact validation, analyst decision records, and approved-only Test2 export. Those components are not duplicated or replaced.

## Refactoring boundary

Observation storage remains in `test3.warehouse`. Feature construction is a distinct `test3.features` package because wide model panels have a different schema and lifecycle from canonical long-form observations. Feature manifests live beside feature Parquet versions, outside the canonical observation-manifest directory, so the two integrity contracts cannot be confused.

## Added in 3A

Milestone 3A adds a governed feature registry; exact annual and quarterly alignment; explicitly labeled annual carry-forward; period mean/end macro transformations; exact-period growth, CAGR, ratio and lag features; source-backed county-to-CBSA aggregation; immutable wide panels; a normalized feature-lineage DAG; feature quality gates; bounded panel/lineage access; and CLI build/status commands.

## Deliberately deferred

CRE target imports, market/submarket crosswalks, regression, fixed effects, predictive validation, model promotion, and recommendation changes belong to Milestones 3B–3F. HUD Fair Market Rent remains `fair_market_rent_2br`; it is never renamed to market asking rent.
