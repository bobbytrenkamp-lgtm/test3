# Model validation

## Promotion policy

A model is not eligible to control an assumption unless all configured gates pass:

1. minimum sample, market, and period coverage;
2. complete source-manifest lineage for real data;
3. explicit confirmation that walk-forward training precedes testing;
4. non-empty out-of-sample predictions;
5. improvement over the best of the last-observation, entity-mean, historical-median, recent-three-year, peer-median and simple autoregressive baselines; and
6. leave-one-market-out evidence when required.

Real-data promotion also requires target-dataset hashes, an immutable feature-table hash, complete source-manifest lineage, a passing independent Python reference check, no severe coefficient instability, and a passing R check when R is available. Exact tolerances and optional-runtime behavior are documented in `docs/model-cross-validation.md`.

Training targets are filtered by release date at every historical forecast origin. When a target release date is unknown, the import-time retrieval date is used conservatively and the limitation remains disclosed.

Synthetic fixtures can test code but can never become controlling forecasts. Failed models remain visible as rejected research evidence. A passing model remains an analyst-reviewed forecast candidate; it does not automatically overwrite an underwriting assumption.

## Interpretation boundaries

- Association is not causation.
- Forecast error ranges are not statistical confidence intervals.
- A small p-value is not proof of economic importance or stability.
- Fixed effects do not remove time-varying omitted-variable bias.
- Good historical performance does not ensure future performance.
- HUD Fair Market Rent remains distinct from institutional asking rent.

Time-series validation uses expanding windows. Geographic validation leaves one market out and does not use the held-out market's fixed effect. Validation outputs retain individual predictions so metrics can be independently reproduced.
