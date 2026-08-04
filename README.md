# test3

`test3` is an open-source, local-first Commercial Real Estate Deal Intake and Due Diligence Engine. It turns raw deal documents into source-linked, human-approved underwriting inputs and a versioned `test2` handoff package.

> ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.

## What works in this release

- Local fictional deal workspace and role-ready organization model
- PDF, CSV, XLSX, PNG and JPEG verification, SHA-256 hashing and duplicate prevention
- Mature local PDF/XLSX/image extraction with source-page bounding boxes and optional local Tesseract OCR
- Side-by-side source review with approve, edit and reject actions
- 19 deterministic reconciliation controls
- Approved-only `test2` JSON adapter, test1 unavailable-state adapter and draft source-linked memo
- SQLite audit history with a hash chain
- No required account, credentials, hosted API, telemetry or document transmission

This is an early functional release, not production-ready. Scanned files use optional locally installed Tesseract; without it they remain visibly queued for manual review. Lease outputs are diligence support, not legal conclusions.

## Run locally

Requires Python 3.11+. Installation downloads only audited, pinned, open-source local-processing packages; no package needs an account or paid service.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\test3.exe
```

Open `http://127.0.0.1:8765`. Stop with Ctrl+C.

The fictional development sign-in is `analyst@example.test` / `fictional-demo`. Do not use this credential pattern with real documents; hardened network/multi-user operation is deferred.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/cost_guard.py
.\.venv\Scripts\python.exe scripts/license_guard.py
```

Only fictional synthetic data may be committed. Uploaded documents stay under ignored `data/uploads/`.

## Architecture and status

Start with [repository assessment](docs/repository-assessment.md), [architecture](docs/architecture.md), [feature status](docs/feature-status.md), and the [cost and billing audit](docs/cost-and-billing-audit.md).

## Related repositories

- `test1`: optional read-only jurisdiction enrichment
- `test2`: downstream underwriting and valuation platform

`test3` never writes into either repository and does not share their databases.

## License

MIT. See `LICENSE`.
