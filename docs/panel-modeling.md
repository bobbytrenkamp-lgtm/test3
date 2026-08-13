# Panel modeling

Test3's research engine turns a governed market-by-period table into transparent statistical candidates. It does not infer causality and it does not promote a forecast merely because a regression can be fitted.

## Implemented methods

- OLS with an intercept
- entity (market) fixed effects
- time fixed effects for retrospective association research
- classical, HC1 heteroskedasticity-robust, and entity-clustered covariance estimates
- coefficient, asymptotic p-value, R-squared, adjusted R-squared, MAE, RMSE, bias, and residual diagnostics
- feature correlation matrices and variance-inflation factors
- exact annual or quarterly lag construction
- expanding-window validation in which every training period precedes its test period
- leave-one-market-out validation without market fixed effects
- last-observation, entity-mean, and historical-median baselines

The implementation uses the Python standard library and existing DuckDB dependency. It introduces no hosted service, credential, telemetry, paid API, or usage billing.

## Required input contract

Each record must have a unique entity/period pair, a numeric target, and every requested numeric feature. Missing values are excluded and counted; they are never converted to zero. Multiple property types require an explicit property-type filter. A target cannot also be a feature.

If a feature has a companion `<feature>__available_at` field, that date must not be later than the modeled period. This makes publication-lag leakage fail loudly. Annual evidence carried into quarterly panels may therefore be used only after its recorded availability date.

## Fixed effects

Entity fixed effects absorb stable differences between observed markets. Time fixed effects absorb common period differences in retrospective estimation. Neither makes a result causal. Future time effects are unknowable, so Test3 deliberately disables them during walk-forward forecasting. Market holdout validation also excludes entity and time effects so an unseen market is not assigned an effect learned from its own outcomes.

## Inference

For panels, entity-clustered standard errors are the preferred first-pass inference method when enough markets exist. Reported p-values use an asymptotic normal approximation. Small cluster counts, serial dependence, cross-market dependence, structural breaks, revisions, and measurement error remain limitations and must be disclosed.

## Local commands

```powershell
test3-research train --input panel.parquet --target rent_growth --features employment_growth,population_growth,vacancy_rate --property-type multifamily --data-status research
test3-research lags --input panel.parquet --target rent_growth --feature employment_growth --lags 0,1,2,4,6,8 --property-type multifamily
```

Both commands emit machine-readable JSON. A `real` status alone does not validate a model: source manifest hashes, minimum coverage, leakage-free walk-forward results, market holdouts, and improvement over the best governed baseline are all required.

Readiness and promotion require longitudinal depth, not merely a large sparse matrix. If a governed specification requires five markets and twenty periods, at least five individual markets must each contain twenty eligible periods. Twenty aggregate periods scattered across shallow market histories cannot pass. Readiness output exposes `periods_by_market` and `markets_meeting_period_minimum` so the gate is auditable.

Model-specific readiness also filters to the specification's declared frequency. Quarterly observations cannot satisfy an annual specification, and annual observations cannot inflate quarterly readiness.
