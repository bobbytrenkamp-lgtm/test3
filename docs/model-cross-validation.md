# Python and R model cross-validation

The native Test3 linear estimator remains the controlling implementation. When locally installed, `statsmodels` independently recomputes OLS coefficients, R², adjusted R², HC1 standard errors and market-clustered standard errors. The governed default tolerances are:

- coefficient absolute difference: `1e-7`
- standard-error absolute difference: `1e-6`
- R² absolute difference: `1e-9`

A material mismatch returns `failed`; Test3 does not silently select one implementation. `statsmodels` and NumPy are optional and are not installed or downloaded by Test3. A real-data model cannot validate unless the independent Python check passes.

`research/R/validate_python_model.R` provides the optional R reference. It uses `lm`, `sandwich` and `jsonlite`, runs with `Rscript --vanilla`, and writes a bounded machine-readable result. R and its packages are optional local open-source tools. If R is absent, status is `not_available`; a numerical mismatch is `failed` and blocks promotion.

Model validation also records expanding-window forecasts, leave-one-market-out performance, the best of governed naïve baselines, coefficient sign stability, per-market error, configurable time-window error and feature-availability rates. Default diagnostic windows around 2020 are diagnostic labels only, not permanent economic regimes.

The governed baselines are last observation, entity mean, historical median, recent three-year mean, peer-market median and a pooled simple autoregressive baseline. Complexity earns no promotion unless it beats the best applicable baseline out of sample.

`test3-research train ... --output local-model.json` writes a new local JSON result with a deterministic model-result hash. `test3-research reproduce --artifact local-model.json --input target-panel.parquet --property-type multifamily` reruns the recorded estimator, validation, cross-check and governance configuration and fails when the result hash differs. Generated production artifacts remain under ignored local data paths and are not committed.
