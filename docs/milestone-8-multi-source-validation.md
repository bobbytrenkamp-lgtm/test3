# Milestone 8 — multi-source institutional validation

Test3 now recognizes MAA and AvalonBay (AVB) as separate institutional source domains. It does not treat a company portfolio as a metro market, and it does not pool observations because two source labels contain the word “rent.”

## AVB evidence contract

`test3-data parse-avb-sec-exhibit` reads a locally supplied, official SEC exhibit using the source-specific Attachment 4 layout. The parser allowlists the SEC issuer path, identifies the current/prior-year quarter pair, rejects ambiguous tables, preserves source-market names, and independently reconciles revenue-per-home growth, economic-occupancy change, and residential-revenue growth. Ambiguity fails with `REVIEW_REQUIRED_SCHEMA_DRIFT`.

The parser emits unverified candidates only. `test3-data publish-avb-sec-candidates` stores an immutable raw snapshot, Parquet version, manifest, and verification report. Existing hash-bound analyst review and market-definition approval remain mandatory before model eligibility.

## Methodology boundary

AVB Average Monthly Revenue per Occupied Home includes concessions amortized over the lease term and uncollectible lease revenue. It is retained as `average_monthly_revenue_per_occupied_home`, not relabeled MAA `effective_rent`. AVB economic occupancy and its exact complement, economic vacancy, remain distinct from MAA physical occupancy/vacancy. The versioned compatibility artifact classifies every current mapping as `comparable_with_limitation` or `not_comparable`; none is currently `directly_comparable` for pooled target modeling.

Historical AVB disclosures are also versioned within the AVB source domain. The 2021 through
2022-Q2 schedule labels the measure `Average Rental Rates` and reports a separate cash-basis
revenue change. From 2022-Q3 the disclosure uses revenue per occupied home, and later filings
add a distinct rent-relief adjustment. Test3 retains `average_rental_rate_growth_yoy`,
`average_monthly_revenue_growth_yoy`, `revenue_growth_yoy_cash_basis`, and
`revenue_growth_yoy_excluding_rent_relief` as separate governed metrics. The series manifest
now reports quarter gaps, market-label additions/removals, and schema transitions, with
automatic harmonization disabled whenever a methodology transition exists.

## Cross-source validation

`cross_source_generalization` performs hard train-one-source/test-the-other experiments and retains each prediction. It reports MAE, RMSE, bias, directional accuracy, and a deterministic artifact hash. Company residual summaries flag possible portfolio/operator effects. The cross-source gate rejects a broad-market claim unless at least two independently approved sources have actual predictions and satisfy the governed error rule.

Cross-source target semantics have a separate human gate. Run:

```text
test3-research prepare-target-harmonization --output data/cre_reports/maa_avb_target_harmonization_review_v1.json
test3-research approve-target-harmonization --data-root data --packet <review.json> --attestation <completed-attestation.json>
test3-research target-harmonization-status --data-root data
```

The generated packet is blank, immutable, and hash-bound. Software does not fill the analyst identity, signature, rationale, decision, source-level decisions, or acknowledgements. Approval permits controlled external-validity research using a source effect or separate source models; it does not declare MAA effective-rent growth identical to AVB revenue-per-occupied-home growth, convert either issuer portfolio into a metro market, or authorize automatic averaging. A changed review packet invalidates the attestation.

`test3-research milestone8-status --data-root data` reports actual MAA/AVB candidates, approvals, markets, periods, geography approvals, methodology compatibility, blocked experiments, and promotion status. The Research Lab exposes the same source comparison and hard-gate state. No assumption evidence package or Test2 parser validation is claimed without a `validated_production` model.

## Current honest limitation

The installed MAA history and AVB candidates are not human-approved, neither source has approved portfolio-to-county market definitions, and the cross-source target harmonization has not been human-approved. Therefore MAA-only, AVB-only, pooled, bidirectional source transfer, forecast scenarios, and Test2 evidence remain prerequisite-blocked. This is a valid rejection state, not a forecast.

The current ignored local AVB candidate snapshot contains 2,291 observations across 25 stable canonical source-market identities and 16 available quarters from 2022-Q1 through 2026-Q1. The missing 2022-Q4 period and disclosed methodology transitions remain explicit. These are candidate facts, not approved/model-eligible observations.

## Depth hardening

`test3-data parse-avb-sec-series` accepts an explicitly enumerated manifest of official, locally
preserved SEC exhibits. The adapter versions the 2023–2024 rent-relief-adjusted disclosure separately;
it never silently pools that adjusted series with reported revenue growth. Missing numeric facts fail
closed rather than becoming zero.

Cross-source research supports exact 1-, 2-, and 4-quarter target horizons. A future target must exist
at the exact calendar quarter; a later non-null row is never treated as the requested horizon merely
because it is next in row order.

The Test2 evidence builder is advisory-only. It rejects non-production forecasts, incomplete validation,
or missing immutable lineage hashes, and never applies an assumption without a separate analyst decision.

Active readiness queries select the newest immutable verification version using bounded report metadata reads and deserialize only active reports. Full-history audit mode still parses every retained vintage and fails on historical corruption. An unreadable active report always fails closed.
