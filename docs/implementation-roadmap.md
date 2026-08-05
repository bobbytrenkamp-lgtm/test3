# Implementation roadmap

Every phase begins and ends with the cost guard. Required confirmation: “ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.”

| Phase | Status | Exit evidence / remaining boundary |
|---|---|---|
| 0 — audit and documentation | Tested, active governance | Assessment/contracts plus institutional gap matrix; roadmap must track every merge |
| 1 — foundation | Tested locally | Fail-closed admin bootstrap, SQLite schema, organizations/roles, CI guards |
| 2 — ingestion | Tested locally | MIME/limits/hashes/duplicates/UUID storage, viewer, controlled purge and crash recovery |
| 3 — deterministic processing | Tested, bounded | PDFium/openpyxl/Pillow and optional local Tesseract with honest unavailable state |
| 4 — extraction review | Partial | Provenance and approval are tested; full semantic fields/rows and spreadsheet source navigation remain |
| 5 — reconciliation | Partial | 19 rules and immutable runs tested; runtime-reachable canonical input contract/E2E remains |
| 6 — test2 export | Tested, minimal | Actual parser accepted minimal property model; expanded entities and persisted versions remain |
| 7 — test1 adapter | Tested, optional | Actual local snapshot match/fallback, integrity, freshness and zero-network evidence |
| 8 — IC memo | Tested | All 18 required sections, approved-only source links, missing/unverified states and immutable artifact persistence |
| 9 — optional local model | Designed | Loopback validation and honest unavailable state; optional generation adapter not implemented |
| 10 — hardening | Tested, bounded; final audit active | Auth, retention, readiness, load/restore and browser audit complete within documented limits |

Next implementation slice: the combined three-document first-release E2E and its prerequisite semantic tabular entities/source navigation. See `docs/institutional-readiness-audit.md`.
