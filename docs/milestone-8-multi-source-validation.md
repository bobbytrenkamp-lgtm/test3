# Milestone 8 — multi-source institutional validation

Test3 now recognizes MAA and AvalonBay (AVB) as separate institutional source domains. It does not treat a company portfolio as a metro market, and it does not pool observations because two source labels contain the word “rent.”

## AVB evidence contract

`test3-data parse-avb-sec-exhibit` reads a locally supplied, official SEC exhibit using the source-specific Attachment 4 layout. The parser allowlists the SEC issuer path, identifies the current/prior-year quarter pair, rejects ambiguous tables, preserves source-market names, and independently reconciles revenue-per-home growth, economic-occupancy change, and residential-revenue growth. Ambiguity fails with `REVIEW_REQUIRED_SCHEMA_DRIFT`.

The parser emits unverified candidates only. `test3-data publish-avb-sec-candidates` stores an immutable raw snapshot, Parquet version, manifest, and verification report. Existing hash-bound analyst review and market-definition approval remain mandatory before model eligibility.

## Methodology boundary

AVB Average Monthly Revenue per Occupied Home includes concessions amortized over the lease term and uncollectible lease revenue. It is retained as `average_monthly_revenue_per_occupied_home`, not relabeled MAA `effective_rent`. AVB economic occupancy and its exact complement, economic vacancy, remain distinct from MAA physical occupancy/vacancy. The versioned compatibility artifact classifies every current mapping as `comparable_with_limitation` or `not_comparable`; none is currently `directly_comparable` for pooled target modeling.

## Cross-source validation

`cross_source_generalization` performs hard train-one-source/test-the-other experiments and retains each prediction. It reports MAE, RMSE, bias, directional accuracy, and a deterministic artifact hash. Company residual summaries flag possible portfolio/operator effects. The cross-source gate rejects a broad-market claim unless at least two independently approved sources have actual predictions and satisfy the governed error rule.

`test3-research milestone8-status --data-root data` reports actual MAA/AVB candidates, approvals, markets, periods, geography approvals, methodology compatibility, blocked experiments, and promotion status. The Research Lab exposes the same source comparison and hard-gate state. No assumption evidence package or Test2 parser validation is claimed without a `validated_production` model.

## Current honest limitation

The installed MAA history and AVB candidates are not human-approved, and neither source has approved portfolio-to-county market definitions. AVB currently has only one locally installed quarter. Therefore MAA-only, AVB-only, pooled, bidirectional source transfer, horizon validation, forecast scenarios, and Test2 evidence remain prerequisite-blocked. This is a valid rejection state, not a forecast.
