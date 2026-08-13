# Historical CRE target data

## Implemented scope

Phase A supports long-form multifamily, industrial, office, and retail observations. Governed targets currently cover asking/effective rent where defined, YoY/QoQ rent growth, vacancy, occupancy, availability, office sublease availability, absorption, deliveries, construction, inventory, concessions, cap rates, transaction volume, and property-type-appropriate transaction pricing.

Metric definitions are property-type aware. Multifamily rent may use `USD_per_unit_month` or `USD_per_sf_month`; industrial, office, and retail rent uses `USD_per_sf_year`. Multifamily quantities use units while other property types commonly use square feet. Incompatible combinations fail instead of being coerced.

## Import contract

Canonical CSV, XLSX, and Parquet files are supported. Required canonical fields are:

`market, geography_type, geography_id, period, frequency, property_type, metric, value, unit, source_name, source_identifier, source_period, retrieved_at, methodology, vintage, licensing_notes, verification_status`

Recommended optional fields are:

`state_fips, county_fips, cbsa, submarket, property_subtype, release_date, redistribution_permitted, source_class, sample_count, notes`

Use local files that you are authorized to analyze. Numeric observations and citations may be retained, but report prose and copyrighted layouts should not be copied into the repository. Brokerage or academic material has no blanket permission: record the actual license/usage basis for each import.

```powershell
test3-data verify-cre --input market-history.csv --forecast-origin 2020-12-31
test3-data import-cre --input market-history.csv --dataset raleigh-mf-history --version 2026-08-09-v1 --analyst-reviewed
test3-data import-cre --input quarterly-export.xlsx --mapping data/warehouse/manifests/cre_import_mappings/vendor-a/1.0-<hash>.json --dataset vendor-a-mf --version 2026q2 --analyst-reviewed
test3-data cre-status
test3-data cre-source-catalog
test3-data cre-source-discovery
test3-data cre-target-audit
test3-data cre-target-funnel --property-type multifamily --metric rent_growth_yoy
test3-data cre-coverage-matrix --property-type multifamily --metric rent_growth_yoy
test3-data cre-series-quality --property-type multifamily --metric rent_growth_yoy
test3-data discover-cre-reports
test3-data parse-maa-sec-snapshots --input-folder data/cre_reports/sec/maa/browser_snapshots --output data/cre_reports/maa_sec_review.csv
test3-data publish-maa-sec-candidates --input data/cre_reports/maa_sec_review.csv --version <immutable-version>
test3-data prepare-cre-review --input data/cre_reports/maa_sec_review.csv --output data/cre_reports/maa_sec_review_packet.json
test3-data approve-cre-review --input data/cre_reports/maa_sec_review.csv --attestation data/cre_reports/maa_attestation.json --output data/cre_reports/maa_sec_approved.csv
test3-data import-cre-bulk --input-folder data/authorized_market_history --dataset-prefix authorized-history --version-prefix 2026q2 --mapping <mapping.json> --analyst-reviewed
test3-research target-readiness --data-root data
test3-research target-readiness --data-root data --model-specification mf_rent_growth_combined
test3-research build-target-panel --data-root data --property-type multifamily --target rent_growth_yoy --frequency quarterly
```

`verify-cre` does not publish. `import-cre` creates a new immutable version and refuses to overwrite an existing one. Missing observations remain missing. Rejected and duplicate observations are not published; unverified but structurally valid evidence may be retained, but is not model-eligible.

Target-panel publication additionally excludes unresolved source conflicts, methodology conflicts and multiple source candidates for the same market-period. An analyst must resolve the controlling source explicitly; Test3 never averages or silently chooses those records.

Saved import mappings require an exact input-column match before reuse. They are content-hashed and stored locally under `data/warehouse/manifests/cre_import_mappings/`. Market definitions are also content-hashed and versioned locally; weighted constituent counties must total one. If market definitions exist, an imported market that lacks a governed definition is not model-eligible. Target-panel construction selects the one property-type-specific definition effective at the target period end and aggregates the latest immutable county feature panel with those exact weights. A missing constituent county makes the feature period unavailable; Test3 never reweights the surviving counties or fills the gap with zero. The selected definition hash is embedded in every joined row and the target-panel identity.

Reviewed document candidates retain document SHA-256, page, table, row, column, original label, and original value. Candidate packages cannot approve themselves. An analyst must select observations and record a rationale before the canonical import/verification path can consider them.

The ignored `data/cre_reports/inbox/` is a local intake directory for lawfully obtained PDF/CSV/XLSX/Parquet reports. Discovery fingerprints files, counts PDF pages, infers candidate source/market/quarter/property type from filenames, groups likely quarterly series, and reports missing quarters. It does not parse rights, approve observations, or make them model eligible. Each discovery result is content-hashed under the ignored `data/cre_reports/manifests/` directory.

Recurring extracted tables support exact versioned label profiles. Schema drift returns `review_required` and zero candidates. Wide and label/value table candidates retain the original cell evidence. Exact YoY rent growth may be derived only from a same-source, same-geography, same-unit, same-methodology quarterly rent pair four quarters apart. Vacancy may be derived as `1 - occupancy` only for explicitly physical/economic occupancy—not availability. Derived rows remain unverified pending analyst review.

## Current data limitations

Analyst approval is a separate, hash-bound operation. `prepare-cre-review` creates an immutable, explicitly non-authoritative inventory plus a blank attestation template; it never approves a row. The analyst must complete the template with their identity, approved scope, rationale, timezone-aware signature time, and four acknowledgements covering source evidence, methodology, market definitions, and rights. `approve-cre-review` creates a new file and attestation sidecar; neither may overwrite an existing artifact. This prevents a changed review file from inheriting an earlier approval.

Immutable dataset vintages remain available for revision analysis, but readiness, coverage, the Research Lab, and target-panel construction use only the newest verification report for each dataset. Older and corrected vintages are never summed together. `cre-series-quality` exposes coverage, missing/duplicate periods, methodology and unit consistency, release-date coverage, analyst-verification rate, model-eligibility rate, and underlying findings for every active source-market series.

The repository contains no copyrighted brokerage history and no production target bytes. The ignored local warehouse can contain public SEC-filed numeric observations and authorized analyst files.

The first installed local series is MAA's quarterly SEC supplemental schedule. The source-specific deterministic parser reads browser-visible same-store market rows, retains exact exhibit URLs and filing dates, and extracts source-reported effective rent; rent, revenue, operating-expense, and NOI growth; quarterly revenue, operating expense, and NOI levels; and same-store apartment units. Monetary levels are accepted only when the filing discloses dollars in thousands. Every reported growth percentage is independently reconciled to the source's current/prior values within a rounding tolerance, while the parser separately enforces revenue less operating expense equals NOI for both periods. NOI margin is derived exactly from the normalized revenue and NOI observations and retains both input observation IDs. The unit count is governed as `same_store_inventory`; it is not mislabeled as total metro inventory. Test3 independently compares unit counts in the rent and occupancy tables and rejects the filing if they disagree. Physical occupancy is extracted across both the 2019–2021 `NOI CONTRIBUTION PERCENTAGE BY MARKET` layout and the later portfolio heading, and vacancy is derived exactly as `1 - occupancy`. For multi-period Q2–Q4 tables, the parser selects the disclosed current-quarter occupancy—not the separate YTD column. A 2026-Q2 rent-table heading change is supported as explicit schema drift. Source markets remain MAA-defined portfolios rather than inferred CBSAs.

The central CRE verifier independently repeats the operating-statement checks for every import path, including user-owned CSV, XLSX, and Parquet histories. Revenue, operating expense, and NOI must share a unit and reconcile within one disclosed unit; NOI margin must reconcile to `NOI / revenue` within one basis point. Failures are preserved as findings and block model eligibility rather than being silently corrected.

Analyst review packets include aggregate quality-finding counts, a bounded finding list with affected market/period/metric/value/evidence rows, a truncation indicator, and explicit model-blocking codes. An attestation cannot create an approved output when its selected observations still fail a central blocking rule; the analyst must correct, reject, or narrow the selection while the original evidence remains immutable.

Parsing and publication never approve rows. `publish-maa-sec-candidates` intentionally publishes unverified evidence with `source_id=sec_maa`; an analyst must review the local CSV and source snapshots before a separate immutable approved version can become model-eligible. No forecasting model may be described as validated until legitimate historical targets are approved, feature-compatible, and tested out of sample.
