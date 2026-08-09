# Research lab

The authenticated **Research lab** navigation item is a read-only local view over actual Test3 evidence. `GET /api/research-lab` reads validated warehouse manifests, bounded DuckDB coverage aggregates, CRE verification reports, immutable feature manifests, and the local SQLite model registry. It makes no network request and does not train or promote a model.

The page reports warehouse rows and periods, source/metric/geography coverage, feature-panel versions, property-type CRE target coverage, installed model artifacts, and the number of validated real-data models. Empty states are deliberate. If no legitimate CRE targets exist, the page says so instead of displaying synthetic research as production evidence.

Public Census HVS rental vacancy and vacant-unit asking rent appear as residential context. They are not labeled as institutional multifamily vacancy, effective rent, or brokerage asking rent. Likewise, Federal Reserve SLOOS results measure bank survey responses and CRE bank-loan series measure credit conditions; neither is a property-market outcome.

The response is bounded to 500 warehouse coverage rows, 500 CRE target groups, 100 CRE import versions, and 100 model artifacts. Integrity errors degrade the report and remain visible rather than being silently omitted.

To populate the two implemented Census HVS series:

```text
test3-data refresh --source hvs
```

To add authorized institutional outcomes, follow `docs/historical-cre-data.md`. A real forecast still requires property-type-specific targets, complete lineage, leakage-safe validation, baseline improvement, and model promotion.
