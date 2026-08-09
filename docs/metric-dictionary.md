# Metric dictionary

The machine-readable dictionary is `src/test3/warehouse/metrics.py`. Each governed metric defines its label, meaning, unit, level/flow/rate type, permitted aggregation, geographic compatibility, frequency compatibility and plausible range where appropriate.

Population is a level, not an interest rate. Rates retain percentage units. BEA scaling is not discarded. Derived growth is a separate Test3 dataset with input observation IDs and a transformation version; missing comparison periods produce no derived observation.

HUD Fair Market Rent is monthly USD and uses `property_subtype` for studio through four-bedroom units. QCEW employment, establishments, weekly wage, annual pay and total wage metrics remain distinct from LAUS labor-force measures. County-to-CBSA membership is categorical, non-additive and effective-date specific.
