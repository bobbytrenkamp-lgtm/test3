# AI changelog

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
