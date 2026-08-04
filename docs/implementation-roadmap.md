# Implementation roadmap

Every phase begins and ends with the cost guard. Required confirmation: “ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.”

| Phase | Status | Exit evidence |
|---|---|---|
| 0 — audit and documentation | Functional | Assessment, contracts, architecture, threat and cost model reviewed |
| 1 — foundation | Functional, tested locally | Loopback app, SQLite schema, organizations/roles, fictional seed, CI guards |
| 2 — ingestion | Functional, tested locally | MIME verification, limits, hashes, duplicates, immutable names, viewer |
| 3 — deterministic processing | Functional, tested locally | Mature local PDF/XLSX/image path; optional Tesseract OCR and honest unavailable state |
| 4 — extraction review | Functional, tested locally | Provenance model and human approve/edit/reject workflow |
| 5 — reconciliation | Functional, tested locally | 19 deterministic rules; resolution notes |
| 6 — test2 export | In development | Local contract tests pass; actual test2 import validation remains |
| 7 — test1 adapter | Designed | Honest local snapshot match/fallback contract |
| 8 — IC memo | Functional | Draft uses approved facts and source appendix only |
| 9 — optional local model | Designed | Loopback-only provider validation and honest unavailable state |
| 10 — hardening | Not started | Load, restore, accessibility and security review required |

Next recommended slice: optional local Tesseract and a permissively licensed mature PDF parser, followed by test2 fixture execution. Neither may add hosted processing.

