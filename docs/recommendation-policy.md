# Governed recommendation policy

Forecasts and underwriting recommendations remain separate. A validated model is evidence; it does not automatically become the base assumption.

Policies are versioned by property type, assumption type, and model-quality tier. Model quality is calculated deterministically from walk-forward improvement versus the best baseline, market-holdout reliability, stability, and Python/R cross-check status. The selected policy controls the model, historical median, and recent-observation weights. Identical evidence and policy versions produce identical recommendations.

Every model-informed recommendation stores:

- recommendation policy ID and version;
- model-quality tier and evidence;
- selected weights;
- historical benchmark;
- model forecast and empirical error range; and
- downside/base/upside recommendation.

Analyst approval, modification, or rejection remains mandatory before Test2 export.
