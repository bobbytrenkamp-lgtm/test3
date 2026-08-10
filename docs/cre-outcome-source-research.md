# CRE outcome source research

Audit date: 2026-08-09. This is an acquisition decision record, not permission to scrape. Public visibility does not establish automation or redistribution rights. Test3 defaults uncertain sources to manual download, local analysis, analyst review, and no redistribution.

The score is a weighted 1–5 assessment of target relevance, market breadth, history, quarterly and methodological consistency, quality, accessibility, legal clarity, and automation suitability. Target relevance receives the greatest weight. Run `test3-data cre-source-discovery` for the machine-readable record.

| Rank | Source | Score | Property type / metrics | Coverage | Access and rights decision | Classification | Next action |
|---:|---|---:|---|---|---|---|---|
| 1 | Authorized user-owned history | 4.88 | All core types; rent, growth, vacancy, inventory, deliveries, absorption, construction | Source-dependent | Local only; analyst documents rights; never committed or redistributed | Institutional target | Bulk local import |
| 2 | MAA SEC quarterly supplements | 4.82 | Multifamily same-store effective rent, reported YoY rent growth, physical occupancy and derived vacancy | 27 source-defined markets; 30 consecutive quarters acquired for rent, 18 for occupancy | SEC-hosted public filings; automated access is permitted only under SEC fair-access controls; numeric facts stay local | Institutional target | Acquired and published as unverified candidates; analyst series review required |
| 3 | Freddie Mac AIMI | 4.35 | Multifamily NOI and property-price indexes, mortgage rate | Selected metros and U.S.; quarterly from 2000 | Official XLS export; review current terms and component sources | Market proxy | Governed official-file adapter after terms review |
| 4 | Cushman & Wakefield MarketBeat | 4.12 | Core sectors; rent, growth, vacancy, inventory, deliveries, absorption, construction | National and 70+ local markets; quarterly | Public reports; bulk automation/redistribution not assumed | Institutional-target candidate | Manual report inbox and review |
| 5 | Zillow ZORI | 3.94 | Multifamily repeat-listing asking-rent index/growth | Published geographies; monthly | Public CSV; terms review required before automation or redistribution | Market proxy | Manual/governed download after terms review |
| 6 | Berkadia Apartment Update reports | 3.88 | Multifamily rent, occupancy, supply, demand | National plus many markets; quarterly reports | Public reports; bulk automation/redistribution not assumed | Institutional-target candidate | Manual report inbox and review |
| 7 | Colliers reports | 3.88 | Rent, vacancy, inventory, delivery, absorption and construction fields vary | Market/submarket; history varies | Public report pages/PDFs; manual only until rights are explicit | Institutional-target candidate | Manual report inbox and review |
| 8 | SEC EDGAR REIT filings | 3.82 | Same-store rent, occupancy and NOI where issuers disclose it | Issuer portfolio/selected market; quarterly/annual | Public filing/API access subject to SEC fair-access policy | Institutional target with issuer-specific methodology | Build only issuer-specific governed adapters |
| 9 | CBRE Multifamily Figures | 3.76 | Rent, growth, vacancy, absorption, completions, investment volume | U.S. and selected markets; quarterly | Public figures/PDFs; third-party inputs and reuse rights require review | Institutional-target candidate | Manual report inbox and review |
| 10 | HUD CHMA | 3.06 | Apartment rent/vacancy spot observations | Selected housing market areas; irregular | Official PDFs, but many figures cite commercial sources | Market proxy | Candidate-only manual extraction |

## Evidence supporting the classifications

- Freddie Mac describes AIMI as a quarterly index for the U.S. and selected metros, with an XLS export and components based on rental income, property prices, and mortgage rates. Rental income combines rent and vacancy, so it is not silently relabeled as asking rent: https://mf.freddiemac.com/aimi and https://mf.freddiemac.com/aimi/about
- Zillow describes ZORI as a repeat-rent asking-rent index weighted to rental stock and publishes downloadable rental series. It is a strong market proxy, not a brokerage institutional-market series: https://www.zillow.com/research/data/ and https://www.zillow.com/research/methodology-zori-repeat-rent-27092/
- Berkadia publicly lists quarterly national and individual-market multifamily reports covering supply, demand, rent, and occupancy. Test3 does not infer bulk collection rights from that access: https://www.berkadia.com/multifamily-reports/
- CBRE publishes quarterly national and selected-market Multifamily Figures with rent, vacancy, absorption, completions, and investment-volume observations: https://www.cbre.com/insights/figures/q1-2026-us-multifamily-figures
- Cushman & Wakefield publishes quarterly MarketBeat reports across the core sectors and 70+ U.S. locations. Multifamily reports expose asking rent, vacancy, absorption, deliveries, and construction statistics: https://www.cushmanwakefield.com/en/united-states/insights/us-marketbeats and https://www.cushmanwakefield.com/en/united-states/insights/us-marketbeats/us-multifamily-marketbeat
- Colliers has public historical reports with explicit market definitions and rent/vacancy methodology. One Raleigh-Durham report states its property universe and separately defines asking rent, effective rent, and physical vacancy: https://www.colliers.com/-/media/Files/UnitedStates/Markets/Raleigh/Research/2017-Reports/2017-Q3-Multifamily-Raleigh-Durham-Report-Colliers.ashx
- SEC provides public filing APIs and nightly bulk files, with automation subject to its published fair-access requirements: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- MAA quarterly Exhibit 99.2 schedules publish market rows for same-store average effective rent and reported year-over-year change. Test3 acquired 29 exhibits covering 2019-Q1 through 2026-Q2. The issuer-defined same-store population is retained as the property universe and is not mislabeled as a full-market asking-rent index: https://www.sec.gov/Archives/edgar/data/912595/000119312526191620/maa-ex99_2.htm
- HUD CHMA reports can contain apartment rent/vacancy observations but often cite commercial underlying sources and are irregular, so Test3 treats them conservatively: https://www.huduser.gov/portal/ushmc/regional.html

## Best immediate sources

1. Analyst review of the locally acquired MAA SEC series, followed by explicit approval of compatible source-defined markets.
2. Authorized user-owned CSV/XLSX/Parquet exports with consistent market definitions and at least 20 quarters.
3. Lawfully downloaded, repeated Cushman & Wakefield/Berkadia/Colliers/CBRE report series placed in `data/cre_reports/inbox/`.

## Best manual-import sources

Public brokerage reports are the strongest no-fee institutional-target candidates found. They remain `manual_download_required`: Test3 fingerprints and groups local files, but does not crawl report archives, bypass controls, or approve extracted observations.

## Best user-owned import paths

Use `test3-data import-cre-bulk` for authorized structured exports. Use `test3-data discover-cre-reports` for lawfully obtained reports. Saved exact-schema mappings prevent accidental reuse after a vendor format change.

## Not suitable as institutional targets

- HUD Fair Market Rent is a regulatory gross-rent benchmark.
- Census HVS is a residential survey, not institutional brokerage vacancy/rent.
- Zillow ZORI and Freddie Mac AIMI are separately labeled market proxies.
- Treasury rates and public macro series are context features.
- HUD/USPS tract vacancy requires restricted eligibility/sublicensing and is not automatically acquired.

## Current installed outcome data

As of the audit date, the ignored local warehouse contains 693 institutional multifamily rent-growth candidates across 27 source-defined markets and 30 consecutive quarters (2019-Q1 through 2026-Q2), plus 693 effective-rent rows and 449 physical-occupancy / 449 derived-vacancy rows for 2022-Q1 through 2026-Q2. The files have complete source URLs, filing dates, units, sample counts, local snapshot hashes, and no structural verification errors.

Model-eligible remains 0 because AI-assisted acquisition cannot certify the mandatory analyst review. The next controlling action is review/approval of the 20 markets with complete 30-quarter rent histories. No real forecast is produced before that approval and feature-geography compatibility review.
