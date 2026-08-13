# Milestone 7 governed multifamily forecast

Test3 treats a failed prerequisite or rejected model as a valid research result. It does not substitute demo data when real evidence is unavailable.

## Current local MAA gate

Run:

```text
test3-research milestone7-status --data-root data
```

The command reports the analyst-attestation gate, every source-defined MAA market, governed definition coverage, feature-frequency compatibility, model-specific readiness, and the decision for every governed rent-growth specification. It prints `No validated forecast is currently available.` unless a real model has passed the production registry gates.

At implementation time the local MAA candidate version contains 8,316 candidate observations across 27 source-defined markets and 30 quarters. None is analyst approved. No MAA market has an analyst-approved county-weight definition. Therefore the reproducible state is `AWAITING_ANALYST_ATTESTATION`; models, baselines, walk-forward validation, holdouts, and forecasts are not run against those candidates.

## Human approval boundary

The immutable review packet contains a blank attestation template and all warning-level findings. A valid attestation must identify the analyst and timestamp, select market/metric/period scopes, acknowledge source evidence, methodology, rights, and market definitions, and provide a rationale. Test3 never supplies the human identity or signature. Approval creates a new hash-bound dataset and never changes the candidate version.

## Market definitions

Run:

```text
test3-research market-definition-coverage --data-root data
```

Only `analyst_approved` definitions are feature eligible. Approved definitions require a source market name, effective dates, definition version, county FIPS components, weights totaling exactly 1.0, weighting methodology, analyst rationale, source evidence, and an immutable definition hash. Missing counties are neither zero-filled nor removed and reweighted.

## Inference and forecasting

Inference specifications may use entity and time fixed effects and are labeled `inference_only`. They cannot become controlling forward forecasts. Forecast specifications are separately governed and cannot require an unknown future time effect. Annual public values used in quarterly panels remain annual evidence carried forward only under the feature registry's documented transformation and original availability date.

Feature compatibility is inspectable with:

```text
test3-research feature-compatibility --model-specification mf_rent_growth_demand_forecast
```

## Lineage

An approved target-feature panel stores the target observation and dataset hashes, target source manifest, effective market-definition hash, feature-table hashes, feature lineage IDs, underlying source observation IDs, and target/feature availability dates. This allows historical forecast-origin checks without silently treating retrieval-late values as known earlier.

## Valid rejection

When prerequisites are absent, each governed model is recorded as `NOT_EVALUATED_PREREQUISITE_GATE` and `not_promoted`, with its exact blockers. Empty validation metrics are shown as not run—not as zero and not as a successful test. Test2 receives no forecast evidence package until a model has reached `validated_production`.
