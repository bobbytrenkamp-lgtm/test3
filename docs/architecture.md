# Architecture

```text
Browser (static HTML/CSS/JS)
        │ loopback HTTP only
Python standard-library service
  ├─ upload verification + immutable storage
  ├─ deterministic classification/extraction
  ├─ review + reconciliation services
  ├─ test1/test2/memo adapters
  └─ SQLite metadata + hash-chained audit
```

The runtime binds only to `127.0.0.1` by default. Exact-pinned permissively licensed packages perform PDF rendering/text extraction, image validation and XLSX parsing entirely locally. Original bytes are stored under generated UUID names and never interpreted as code. Spreadsheet formulas are retained for review but never executed. Browser text is escaped and the server applies a restrictive content-security policy.

The sign-in boundary uses both visual state and `inert`/`aria-hidden` state so hidden workspace controls are not keyboard-reachable. Core CSS/JS references carry the application version; release changes affecting those assets must bump that version to prevent mixed cached UI revisions.

SQLite `PRAGMA user_version` is the compatibility boundary. Version `1` is the governed baseline, including additive migration of legacy session, finding and document-retention columns. Runtime initialization rejects a database whose version is newer than the installed code instead of attempting an unsafe downgrade.

An authenticated administrator may call `GET /api/operations/integrity`. The local-only probe runs SQLite quick/foreign-key/schema checks, verifies the independent audit and review hash chains, streams SHA-256 over each retained original, validates purged tombstones and reports interrupted purge-staging files. It makes zero network requests and returns `ok: false` for any discrepancy.

Backup format `test3-backup/3.0` binds the governed schema version and modern governance-table contract into the manifest. Restore verification checks paths, lengths and hashes, SQLite integrity/table counts, then opens the disposable restore through current application code and runs operational integrity for every organization.

Production/network use is intentionally blocked pending hardened authentication, CSRF controls and a security review. Static GitHub Pages may host documentation/UI demonstrations, but cannot provide private persistence or document processing; the full application remains local.

