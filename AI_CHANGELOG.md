# AI changelog

## 2026-08-04 — local authentication and session hardening

- Added deterministic process-local sign-in lockouts at account and loopback-address scopes and equal-cost unknown-account password checks.
- Added CSRF-protected server-side session revocation and a visible sign-out action.
- Centralized restrictive security headers across static, JSON, rendered-page and original-document responses; encoded response filenames safely.
- Added optional local-TLS secure-cookie mode and live HTTP replay regression coverage.
- Added no service or dependency; all controls remain local and non-billable.

## 2026-08-04 — reconciliation history integrity

- Replaced destructive reconciliation refreshes with immutable runs and retained finding supersession.
- Added exact input hashes, database immutability triggers, stale-resolution rejection, migration support and regression coverage.
- Updated the analyst UI to distinguish open, resolved and superseded findings.
- Confirmed the zero-cost and permissive-license guards; no service, account or dependency was added.

## 2026-08-04

- Audited empty `test3` and read-only shallow snapshots of `test1` and `test2`.
- Selected isolated local SQLite plus versioned adapters as the safest integration.
- Added local service, analyst UI, ingestion controls, deterministic processing, review states, reconciliation, exports and audit history.
- Added documentation, zero-cost and license guards, CI and fictional-data tests.
- Added PBKDF2 local fictional sign-in and opaque HttpOnly/SameSite sessions.
- Declined hosted deployment and hosted AI paths because they cannot satisfy the absolute zero-cost rule.

## 2026-08-04 — Security and operability tranche

- Enforced role permissions and CSRF tokens on every authenticated mutation.
- Replaced plaintext session identifiers in SQLite with SHA-256 token digests; added expiry cleanup and legacy-session invalidation.
- Serialized audit writes and added full hash-chain verification/tamper detection.
- Added XLSX expanded-size, entry, compression-ratio, row and cell safety limits.
- Added non-overwriting local backups with file manifests, hashes and temporary restore/integrity drills.
- Expanded the suite to 30 tests and validated 401/CSRF/authorized-create behavior over live HTTP.

## 2026-08-04 — Document processing tranche

- Audited and exact-pinned pypdfium2/PDFium, Pillow, openpyxl, defusedxml and transitive et_xmlfile; all are local and permissively licensed.
- Added PDFium page-aware text extraction and normalized source bounding boxes.
- Added local rendered-PDF page endpoint and analyst source-area highlighting.
- Added Pillow decode/pixel safety checks and optional local Tesseract image/scanned-PDF OCR with confidence/bounding provenance.
- Replaced direct XLSX XML parsing with guarded openpyxl read-only parsing; formulas remain unexecuted candidates and macro-enabled files are rejected.

## 2026-08-04 — test2 contract tranche

- Replaced the nominal test3-shaped handoff with a real nested test2 `cre-platform-model` document.
- Made import readiness fail closed when approved forecast, valuation or property inputs are missing or invalid.
- Kept rejected and pending values out of both the model and supporting-source manifest.
- Executed the fictional minimal model through test2's own `parseModelInput` implementation without adding a runtime dependency.
- Honored test2's supply-chain policy when its disposable dependency install rejected newly published lockfile entries; no policy was relaxed.

## 2026-08-04 — extraction governance tranche

- Replaced the ten-field global pattern map with a typed, category-scoped institutional field registry.
- Added deterministic rate, basis-point, integer and date normalization plus registry-derived units and currencies.
- Added category-negative tests so unrelated document types do not emit misleading candidates.
- Preserved tabular row identity and the mandatory human-review boundary.

## 2026-08-04 — approval governance tranche

- Preserved extracted normalization as immutable source evidence and moved reviewer edits into append-only decisions.
- Added database immutability triggers, serialized decision hashes and an independent tamper verifier.
- Added registered, rationale-required manual assumptions that begin pending and retain user-entered provenance.
- Added typed approval validation and explicit supersession of the prior controlling value.
- Included assumption and decision counts in backup restore verification.
- Replaced native prompt interactions with labeled review/resolution forms and completed a clean-console browser workflow.

## 2026-08-04 — test1 local snapshot tranche

- Implemented a strict reader for test1's actual static metadata, policy, political-risk, water, incentive, facility and state-regulation files.
- Added per-file hashes/byte counts, duplicate-key rejection, source/dataset freshness and bounded facility summaries.
- Required an approved typed county FIPS and kept all unavailable/unresearched states explicit.
- Proved compatibility against test1 commit `aa8ab706…` with zero network requests and conservative verification semantics.
- Redistributed no test1 code or data because the source repository has no license file.
- Completed the configured browser path with six context cards, visible freshness/limitations/citations and a clean console.
