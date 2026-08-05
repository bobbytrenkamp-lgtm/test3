# Implementation roadmap

Every phase begins and ends with the cost guard. Required confirmation: “ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.”

| Phase | Status | Exit evidence / remaining boundary |
|---|---|---|
| 0 — audit and documentation | Tested, active governance | Assessment/contracts plus institutional gap matrix; roadmap must track every merge |
| 1 — foundation | Tested locally | Fail-closed admin bootstrap, SQLite schema, organizations/roles, CI guards |
| 2 — ingestion | Tested locally | MIME/limits/hashes/duplicates/UUID storage, viewer, controlled purge and crash recovery |
| 3 — deterministic processing | Tested, bounded | PDFium/openpyxl/Pillow and optional local Tesseract with honest unavailable state |
| 4 — extraction review | Tested, bounded | Immutable semantic rows and first-worksheet exact logical source navigation are proven; broader header corpus and multi-sheet ingestion remain |
| 5 — reconciliation | Tested, bounded | 19 rules, immutable runs and combined live HTTP workflow are proven; broader semantic-list reconciliation remains |
| 6 — test2 export | Tested, bounded | Actual parser accepted minimal and expanded space/tenant/lease/expense/debt models; advanced test2 arrays remain unmapped |
| 7 — test1 adapter | Tested, optional | Actual local snapshot match/fallback, integrity, freshness and zero-network evidence |
| 8 — IC memo | Tested | All 18 required sections, approved-only source links, missing/unverified states and immutable artifact persistence |
| 9 — optional local model | Designed | Loopback validation and honest unavailable state; optional generation adapter not implemented |
| 10 — hardening | Tested, bounded; final audit active | Auth, retention, readiness, load/restore and browser audit complete within documented limits |

Next implementation slice: broaden fictional semantic header/category-negative coverage and multi-sheet ingestion only where direct source navigation can remain exact. See `docs/institutional-readiness-audit.md`.
