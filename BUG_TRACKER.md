# Bug tracker

| ID | Status | Severity | Summary | Resolution / next action |
|---|---|---:|---|---|
| T3-001 | Known limitation | Medium | Conservative standard-library PDF extraction handles only simple selectable-text operators. | Keep visible `needs_review`; evaluate permissive local PDF parser in Phase 3 after license/cost audit. |
| T3-002 | Known limitation | Medium | Image/scanned-PDF OCR is not bundled. | Add optional local Tesseract subprocess adapter; never pretend scanning/OCR occurred. |
| T3-003 | Known limitation | High | Seed identity is a local development sign-in, not hardened multi-user authentication. | Implement password hashing/session controls and permission matrix before network exposure. |
| T3-004 | Fixed 2026-08-04 | High | Seed user insert supplied seven placeholders for a six-column table. | Corrected placeholder count; service suite rerun. |
| T3-005 | Fixed 2026-08-04 | Low | Initial fictional SHA-256 test vector was incorrect. | Replaced with independently published digest for the literal test bytes. |
| T3-006 | Fixed 2026-08-04 | High | Document/extracted-value inserts used ambiguous placeholder counts. | Added explicit column lists and exact placeholder counts. |
| T3-007 | Fixed 2026-08-04 | Medium | SQLite backup connections remained open on Windows because connection context managers do not close handles. | Wrapped backup and drill connections in `contextlib.closing`; Windows cleanup test added. |
