# Opportunity score governance

Test3 does not currently have an approved, realized property-level acquisition outcome dataset. Consequently, it does not produce a property opportunity score. The correct current product state is:

`NO_VALIDATED_OPPORTUNITY_SCORE`

This is a governed rejection, not a missing UI feature.

## Outcome contract

Before a candidate score can be backtested, every outcome must preserve property, market, period, property type, forecast origin, feature availability, outcome realization and release dates, outcome definition/value, analyst verification, rights status, and source/feature hashes.

The first governed policy is multifamily-specific and requires, at minimum:

- 200 eligible real observations;
- 10 markets;
- 12 distinct periods;
- 8 periods in each of at least 10 markets;
- exact forward outcomes and feature availability no later than the forecast origin.

These are minimum governance gates, not a claim that the resulting sample is statistically sufficient for every model.

Synthetic, candidate-only, unverified, rights-undocumented, duplicated, mixed-property, mismatched-outcome, invalid-lineage, future-feature, non-forward-outcome, and extreme-review observations do not count toward readiness.

## Promotion gates

A future candidate must also provide:

- non-empty out-of-sample predictions;
- a passed time holdout;
- a passed geography holdout;
- improvement over the best governed naïve baseline;
- passed stability diagnostics;
- a passed independent Python result check;
- a passed local R check or an explicit policy-permitted unavailable state;
- an immutable model-result hash and valid source hashes.

The policy is versioned and content-hashed. A failed gate yields explicit reasons and cannot be bypassed by high in-sample R², plausible narrative, or visual fit. Even a validated score would remain advisory and require analyst approval before any underwriting use.

## Current limitation and next lawful data step

The current repository contains market outcomes and property screening evidence, but no approved realized property-level acquisition performance dataset linking forecast-origin evidence to later investment outcomes. Test3 must ingest such legitimately owned, rights-documented local history before it can backtest or promote a score. It will not label brokerage comparables, synthetic fixtures, asking rents, or forecasted returns as realized acquisition outcomes.

