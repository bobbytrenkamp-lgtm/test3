# CRE target source registry

Test3 classifies every proposed source as `institutional_target`, `market_proxy`, `residential_proxy`, or `context_feature`. Only the first class can supply a CRE model target, and each observation must still pass analyst review, lineage, unit, methodology, geography, availability, and conflict checks.

The implemented registry is exposed with:

```powershell
test3-data cre-source-catalog
```

## Current governed sources

| Source | Classification | Access | Automation | Use |
|---|---|---|---|---|
| User-owned CRE history | Institutional target | Local CSV/XLSX/Parquet | Local only | Primary supported route for lawful brokerage/licensed history |
| Public brokerage reports | Institutional target candidates | Reviewed document | Manual only | Numeric candidates require page/table/cell evidence and analyst approval |
| Census HVS | Residential proxy | Official download | Permitted through existing adapter | Housing vacancy/rent context; never institutional apartment vacancy or asking rent |
| HUD FMR | Market proxy | Official download | Permitted through existing adapter | Regulatory gross-rent benchmark; never market asking/effective rent |
| FRED/IMF U.S. CRE price series | Context feature | Official download | Permitted through existing FRED adapter | National mixed-CRE price movement, not a market/property-type outcome |
| BIS Commercial Property Prices | Context feature | Manual download | Disabled pending series-level rights review | Definitions and underlying compiler rights vary |
| FHFA Multifamily PUDB | Context feature | Manual download | Disabled | Mortgage acquisition context, not rent/vacancy history |

Public visibility alone is not permission to automate or redistribute. Unknown rights default to manual review. Report prose, layouts, user-owned data, production Parquet, raw files, and model artifacts stay under ignored local `data/warehouse/` paths and are not committed.

## Current target-data conclusion

The installed warehouse contains strong public predictors and residential/context proxies, but no analyst-approved institutional CRE target history. Accordingly, no real rent-growth, vacancy, or cap-rate model is promoted. The Research Lab Target Data workbench reports actual market-period coverage, source conflicts, methodology changes, and model-specific readiness without filling gaps.
