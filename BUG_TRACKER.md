# Bug tracker
| ID | Status | Severity | Summary | Resolution / next action |
|---|---|---:|---|---|
| T3-001 | Fixed 2026-08-04 | Medium | Initial PDF extraction handled only simple selectable-text operators. | Replaced with audited local PDFium processing, page rendering, normalized source boxes and tests. |
| T3-002 | Fixed 2026-08-04 | Medium | Image/scanned-PDF OCR was not available. | Added an optional loopback-only local Tesseract adapter with confidence and source boxes; absence remains explicit. |
| T3-003 | Reduced; loopback constraint remains | High | Seed identity was an unhashed development sign-in. | Added PBKDF2 credentials, opaque hashed sessions, CSRF and roles. Keep the server loopback-only until TLS and an institutional identity design exist. |
| T3-004 | Fixed 2026-08-04 | High | Seed user insert supplied seven placeholders for a six-column table. | Corrected placeholder count; service suite rerun. |
| T3-005 | Fixed 2026-08-04 | Low | Initial fictional SHA-256 test vector was incorrect. | Replaced with independently published digest for the literal test bytes. |
| T3-006 | Fixed 2026-08-04 | High | Document/extracted-value inserts used ambiguous placeholder counts. | Added explicit column lists and exact placeholder counts. |
| T3-007 | Fixed 2026-08-04 | Medium | SQLite backup connections remained open on Windows because connection context managers do not close handles. | Wrapped backup and drill connections in `contextlib.closing`; Windows cleanup test added. |
| T3-008 | Fixed 2026-08-04 | Low | Cost guard scanned ignored virtual-environment vendor files and reported irrelevant provider documentation. | Excluded `.venv`; repository-owned source/config/docs remain scanned. |
| T3-009 | Fixed 2026-08-04 | High | Rerunning reconciliation deleted prior open findings and erased conflict history. | Added immutable input-hashed reconciliation runs, retained findings, explicit supersession and database deletion guards. |
