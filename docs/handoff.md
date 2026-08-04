# Implementation handoff

Date: 2026-08-04

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

No automated test or smoke-test failure is open. Complex/scanned PDF extraction, optional local Tesseract, test1 snapshot mapping, actual test2 import execution, hardened multi-user/network authentication, browser e2e/accessibility automation, load testing and restore testing remain incomplete. Therefore the project is not production-ready and direct test2 compatibility is not claimed.

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

