# Implementation handoff

Date: 2026-08-04

## Authoritative institutional gap audit

`docs/institutional-readiness-audit.md` is now the authoritative completion matrix. Infrastructure, zero-cost controls, test1, minimal test2, readiness, retention, load/restore and bounded browser accessibility are evidenced. The full objective is not complete: reconciliation inputs are not consistently reachable from runtime fields, semantic tabular extraction/spreadsheet source viewing is partial, exports are not persisted/versioned artifacts, and the memo/test2 mappings are minimal. P0 begins with a canonical reconciliation field contract and one automated OM + rent-roll + T-12 first-release workflow.

## Purge crash-recovery update

Original-byte purge now writes a durable bounded sidecar before same-volume staging. On startup, exact database/path/size/hash checks restore uncommitted bytes or finish deletion after a committed tombstone; uncertain artifacts remain untouched and fail readiness. Both crash boundaries are simulated in the 62-test suite and produce hash-chained recovery events. Next: formal full-spec gap matrix and implementation of the highest remaining product-coverage gaps.

## Browser accessibility/security update

A real Chromium audit at desktop and 390×844 fixed signed-out control reachability, mobile sign-out, keyboard upload, low-contrast text and cache coherence. Synthetic markup rendered only as text, mobile overflow was zero, session revocation restored isolated/focused sign-in state and browser warning/error logs were empty. CI now runs a dependency-free accessibility contract guard. Exact evidence and limitations are in `docs/browser-accessibility-security-evidence.md`. Next: requirement-by-requirement institutional gap audit and interrupted-operation recovery.

## Resilience-evidence update

The local bounded harness concurrently creates and ingests fictional deals, asserts exact database/audit counts and readiness, creates backup format 3.0, opens a disposable restore through current code and reruns operational integrity. Two 100-operation/8-worker runs completed with zero failures and exact counts; results and limits are recorded in `docs/resilience-evidence.md`. Next: automated browser accessibility/XSS/security evidence and operational interrupted-transaction recovery procedures.

## Readiness-integrity update

SQLite now has an explicit governed schema version and rejects future databases. Audit events are preventively append-only. The authenticated administrator operations probe validates database/FK/schema health, both hash chains, every active original hash, purged tombstones and interrupted purge staging with no network requests. The suite is 60 tests. Next: deterministic local load/concurrency harness, repeat restore evidence, and automated browser accessibility/security review.

## Retention-control update

A reauthenticated administrator can now purge only the integrity-verified uploaded original while preserving a document tombstone and immutable purge event. Wrong credentials, repeat operations, unsafe/missing paths and content-integrity mismatches fail closed. Retrieval returns 410. The new retention policy explicitly distinguishes this from full-case or backup/media erasure. Next: database schema/version health, integrity readiness probes and load/concurrency evidence.

## Administrator-bootstrap update

Normal runtime no longer creates or recreates a known credential. A first-run operator initializes an application-local administrator through `test3-init-admin`; password input is non-echoing and absent from arguments/environment/logs. Explicit demo mode is now the only path to the fictional seed identity. Rotation revokes every session. Next: controlled document/deal retention and deletion without compromising immutable governance history.

## Authentication/session hardening update

Local sign-in now applies account- and address-scoped lockouts, performs full PBKDF2 work for unknown accounts and rejects ambiguous duplicate emails. Sign-out deletes the hashed server-side session and clears the browser cookie; a live HTTP test proves replay fails. Security headers now apply to every response. The next control is an explicit institutional first-run administrator bootstrap so the fictional demonstration credential is never the operational default.

## Reconciliation-integrity update

Reconciliation reruns no longer delete discrepancies. Every run is immutable and records the rule-engine version and SHA-256 of its normalized inputs; prior open findings are retained as superseded. The suite is now 55 tests. Next: local authentication abuse controls, session revocation and operational health/integrity probes.

## Completed

- Read-only repository assessment for test1/test2 and isolated adapter design.
- Dependency-free loopback Python/SQLite service and responsive analyst UI.
- Fictional local sign-in, organization-ready schema, deal creation and audit chain.
- Upload type verification, limits, SHA-256, duplicates, UUID storage and explicit no-malware-scan state.
- Conservative CSV/XLSX/PDF processing, provenance records and human review.
- Nineteen deterministic reconciliation controls and recorded resolutions.
- Approved-only test2 package, honest test1 fallback and draft source-linked memo.
- Cost/billing and license guards plus public-repository CI.

## Current failures and limitations

No automated gate is failing. The remaining blockers are product-coverage gaps, not the previously listed test1/test2/load/browser work: canonical runtime reconciliation inputs, semantic table models and spreadsheet source viewing, persisted export versions, complete memo sections and a single three-document first-release E2E. Network binding remains intentionally refused; optional local Tesseract/model capabilities are not required for deterministic core use. The project is not production-ready.

## Verification performed

- 26 unit/integration tests: pass.
- Cost guard over source/config/environment/docs: pass.
- Dependency/license guard: pass.
- Live local HTTP sign-in and authenticated bootstrap: HTTP 200; one fictional deal; local-only and zero-cost flags true.

## Next recommended task

Add optional local Tesseract and a mature permissively licensed local PDF parser only after a version-specific license audit. Then run the generated fictional package through a real test2 import fixture and add browser accessibility/e2e coverage.

## Security tranche update

PR #1 established the foundation. The next tranche adds role/CSRF enforcement, hashed sessions, audit verification, archive-bomb limits and backup/restore drills. The suite is now 30 tests; live HTTP checks return 401 without authentication, 401 without CSRF and 201 with the valid local session/CSRF pair.

## Document-processing tranche update

The exact dependency set (pypdfium2 5.12.1, Pillow 12.3.0, openpyxl 3.1.5, defusedxml 0.7.1 and et_xmlfile 2.0.0) was installed in an ignored local environment. All 34 tests pass under those versions. A packaged-entry-point HTTP smoke test uploaded a fictional PDF, extracted two candidates, stored a normalized bounding box and rendered the linked source page as a 22,402-byte PNG with HTTP 200. Scanned OCR remains optional on a separately installed local Tesseract executable; no document is transmitted.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.

## 2026-08-04 canonical reconciliation contract

All scalar reconciliation keys now belong to the 57-field governed registry. `RECONCILIATION_SCALAR_FIELDS` is checked against `FIELD_BY_NAME`, and the service regression approves 31 assumptions through append-only decisions before asserting sixteen persisted findings. Lease dates are normalized ISO strings and no longer pass through decimal parsing. Structured row/list rules and the combined three-document HTTP release workflow remain open work; do not describe the entire reconciliation requirement as complete yet.
