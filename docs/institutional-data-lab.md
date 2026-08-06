# Institutional data lab

test3 provides a local, reproducible research layer for CRE underwriting. It does not claim parity with proprietary quantitative firms or commercial data vendors: those organizations possess licensed observations, dedicated research teams and infrastructure that cannot be redistributed in this zero-cost repository.

## Data universe

The bootstrap catalog identifies 27 audited series from FRED, BLS and Census covering rates and credit, construction and housing supply, inflation and rent, labor-market demand, consumer activity, population, income and housing tenure. The catalog records provider series identifiers rather than silently substituting similarly named series.

Raw observations are never fetched at runtime. Analysts manually download official files and retain the official source URL, download date, usage rights and source version. `scripts/prepare_public_series.py` converts supported FRED and BLS CSV files into the same immutable local market-panel format used by analyst-owned data.

Example:

```powershell
$env:PYTHONPATH='src'
python scripts/prepare_public_series.py FRED DGS10 downloads/DGS10.csv data/DGS10-panel.csv --source-date 2026-08-05 --source-reference https://fred.stlouisfed.org/series/DGS10
```

No network request is made by the script. Census series are cataloged for controlled manual normalization because ACS exports vary by product, vintage and geography.

## Analytics

Each deal response includes:

- source, metric, geography, property-type and date coverage;
- cross-sectional and time-window benchmark summaries;
- exact-key descriptive Pearson correlations;
- linear trend, observed-period change, volatility, maximum drawdown and latest z-score;
- empirical 10th/50th/90th-percentile change scenarios and historical extremes;
- strongest small-lag associations for exact geography/property scopes.
- reusable observed-period level-change, percentage-change and configurable lag factors;
- like-for-like cross-market percentile scorecards for level, momentum, mean change, volatility and downside deviation.
- revision/conflict registers for identical logical observations across snapshots and sources;
- cadence and large-gap findings, per-source coverage/quality scorecards, and a canonical SHA-256 research manifest.

All outputs are descriptive. Correlation, lead/lag results and empirical scenarios are explicitly labeled non-causal and non-forecasting. Irregularly spaced observations are not presented as equally spaced calendar forecasts.

## Professional operating controls

1. Archive each original source file and its checksum.
2. Preserve the official source URL, series identifier, vintage and download date.
3. Do not pool incompatible definitions, frequencies or geographies.
4. Inspect stale, sparse and outlier flags before approving an assumption.
5. Treat candidate ranges as analyst decision support, never automatic underwriting truth.
6. Obtain separately licensed proprietary observations locally when public data cannot support a market-level conclusion.
7. Review every cross-vintage conflict and archive the research-manifest hash with investment-committee materials.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.
