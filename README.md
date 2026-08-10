# test3

Populate the local analytical warehouse with `test3-data refresh --source census --to-year 2024 --geography county`; inspect it with `test3-data status`, `test3-data coverage`, and `test3-data lineage OBSERVATION_ID`. Build immutable analysis-ready panels with `test3-data build-features --geography county --frequency annual` and inspect versions with `test3-data feature-status`. See `docs/public-data-ingestion.md` and `docs/feature-engineering.md`.

Run governed local panel research with `test3-research train --input panel.parquet --target rent_growth --features employment_growth,population_growth --property-type multifamily`. The research engine supports fixed effects, robust/market-clustered standard errors, exact-period lag research, leakage-safe walk-forward tests, market holdouts, diagnostics, and baseline competition. See `docs/panel-modeling.md` and `docs/model-validation.md`.

Measure institutional target readiness with `test3-research target-readiness --data-root data`, then create an immutable target/feature join with `test3-research build-target-panel --data-root data --property-type multifamily --target rent_growth_yoy --frequency quarterly`. See `docs/cre-target-panels.md` and `docs/model-cross-validation.md`.

Import legitimate, authorized historical CRE targets with `test3-data verify-cre --input market-history.csv` followed by `test3-data import-cre --input market-history.csv --dataset DATASET --version VERSION --analyst-reviewed`. The property-type-aware verification layer preserves source conflicts and revisions, enforces release-date availability, and never averages sources automatically. See `docs/historical-cre-data.md` and `docs/source-provenance.md`.

After signing in locally, open **Research lab** in the left navigation to inspect actual warehouse coverage, feature panels, verified CRE targets, model artifacts, validation status and readiness limitations. The view never creates model results or fills missing data. See `docs/research-lab.md`.

`test3` is an open-source, local-first Commercial Real Estate Deal Intake and Due Diligence Engine. It turns raw deal documents into source-linked, human-approved underwriting inputs and a versioned `test2` handoff package.

> ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.

## What works in this release

- Governed Assumption Intelligence across 15 assumption domains, with local market-panel evidence, benchmark matrices, correlations, time-series diagnostics, empirical stress bands, lead/lag exploration, derived change factors, cross-market scorecards, data-quality profiles and candidate ranges
- Audited offline catalog of 27 FRED, BLS and Census indicators with local FRED/BLS CSV normalization; no runtime download, key or hosted API
- Revision/conflict registers, cadence-gap diagnostics, source scorecards, and canonical research manifests for reproducibility
- Walk-forward baseline backtests and transparent rent/vacancy regime-transition analysis for model-risk governance
- Immutable source snapshots, observations, model artifacts, runs, evidence links, and analyst decision context
- Offline base-R reference pipeline with conspicuously fictional synthetic fixtures and outputs
- Approved-only Test2 growth-curve mapping plus a non-controlling evidence/recommendation sidecar
- Local fictional deal workspace and role-ready organization model
- PDF, CSV, XLSX, PNG and JPEG verification, SHA-256 hashing and duplicate prevention
- Mature local PDF/XLSX/image extraction with source-page bounding boxes and optional local Tesseract OCR
- Side-by-side source review with approve, edit and reject actions
- 19 deterministic reconciliation controls
- Approved-only, parser-validated bounded `test2` JSON adapter; local test1 snapshot adapter; immutable 18-section source-linked memo
- Immutable semantic rent-roll, operations, lease and debt rows with exact source-cell membership and analyst review navigation
- Optional, explicitly invoked loopback-only Ollama JSON provider whose output remains candidate-only
- Local, source-linked rent-comparable ranking and school/retail/downtown/amenity proximity context from reviewed CSV evidence and Test1/user coordinates
- SQLite audit history with a hash chain
- No required account, credentials, hosted API, telemetry or document transmission
- Immutable county/CBSA annual and quarterly feature panels with governed frequency conversions, exact-period growth/lags, separate lineage Parquet and source-backed CBSA aggregation
- Local Research Lab dashboard backed by verified Parquet manifests and immutable SQLite model artifacts
- Machine-readable CRE target audit, readiness funnel, market-period coverage, lawful source ranking, ignored local report inbox and bulk authorized-history import
- Census HVS quarterly U.S. residential rental-vacancy and vacant-unit asking-rent histories, plus governed Federal Reserve CRE credit-series definitions

This is an institutionally controlled **local first-usable release**, not a network-production deployment. Its documented deterministic workflow, governance, recovery, bounded load and accessibility scope are tested; advanced extraction/mapping breadth and external production certification remain explicit limitations. Scanned files use optional locally installed Tesseract; without it they remain visibly queued for manual review. Lease outputs are diligence support, not legal conclusions.

Optional jurisdiction context can read a local test1 clone/export. Set `TEST3_TEST1_DATA_DIR` to its `data` directory and approve a five-digit `county_fips` assumption. The adapter never geocodes, fetches citations, or makes a network request.

## Run locally

Requires Python 3.11+. Installation downloads only audited, pinned, open-source local-processing packages; no package needs an account or paid service.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\test3-init-admin.exe --email you@example.test
.\.venv\Scripts\test3.exe
```

The initialization command prompts twice without echo and never accepts a password argument. Open `http://127.0.0.1:8765`. Stop with Ctrl+C. To rotate an unambiguous local user's password and revoke all sessions, rerun the initializer with `--reset-password`.

For a fictional demonstration only, set `TEST3_DEMO_MODE=1` before first startup; this explicitly creates `analyst@example.test` / `fictional-demo` and a fictional deal. Never use demo mode or that known credential with real documents. Non-loopback/network operation remains blocked.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/cost_guard.py
.\.venv\Scripts\python.exe scripts/license_guard.py
.\.venv\Scripts\python.exe scripts/accessibility_guard.py
.\.venv\Scripts\python.exe -m test3.load_probe --operations 100 --workers 8
```

Only fictional synthetic data may be committed. Uploaded documents stay under ignored `data/uploads/`.

Administrator original-byte purge is password-reauthenticated, integrity-checked and tombstoned. It does not erase extracted governance history or existing backups; review the [retention and deletion policy](docs/data-retention-and-deletion.md) before use.

## Architecture and status

Start with the [institutional readiness audit](docs/institutional-readiness-audit.md), [repository assessment](docs/repository-assessment.md), [architecture](docs/architecture.md), [feature status](docs/feature-status.md), [resilience evidence](docs/resilience-evidence.md), [browser accessibility/security evidence](docs/browser-accessibility-security-evidence.md), and the [cost and billing audit](docs/cost-and-billing-audit.md).

## Related repositories

- `test1`: optional read-only jurisdiction enrichment
- `test2`: downstream underwriting and valuation platform

`test3` never writes into either repository and does not share their databases.

## License

MIT. See `LICENSE`.
