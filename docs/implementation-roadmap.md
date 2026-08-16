# Implementation roadmap

Every phase begins and ends with the cost guard. Required confirmation: “ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.”

| Phase | Status | Exit evidence / remaining boundary |
|---|---|---|
| 0 — audit and documentation | Tested, active governance | Assessment/contracts plus institutional gap matrix; roadmap must track every merge |
| 1 — foundation | Tested locally | Fail-closed admin bootstrap, SQLite schema, organizations/roles, CI guards |
| 2 — ingestion | Tested locally | MIME/limits/hashes/duplicates/UUID storage, viewer, controlled purge and crash recovery |
| 3 — deterministic processing | Tested, bounded | PDFium/openpyxl/Pillow and optional local Tesseract with honest unavailable state |
| 4 — extraction review | Tested, bounded | Immutable worksheet/row-provenance semantic rows and bounded multi-sheet logical source navigation are proven; broader fictional header corpus remains |
| 5 — reconciliation | Tested, bounded | 19 rules, immutable runs and combined live HTTP workflow are proven; broader semantic-list reconciliation remains |
| 6 — test2 export | Tested, bounded | Actual parser accepted minimal and expanded space/tenant/lease/expense/debt models; advanced test2 arrays remain unmapped |
| 7 — test1 adapter | Tested, optional | Actual local snapshot match/fallback, integrity, freshness and zero-network evidence |
| 8 — IC memo | Tested | All 18 required sections, approved-only source links, missing/unverified states and immutable artifact persistence |
| 9 — optional local model | Tested, opt-in | Explicit loopback probe/generation, structured JSON validation and required metadata; no automatic invocation or approval authority |
| 10 — hardening | Tested, bounded; final audit active | Auth, retention, readiness, load/restore and browser audit complete within documented limits |

Next implementation slice: broaden fictional semantic header/category-negative coverage and add advanced test2 mappings only where approved source semantics remain complete. See `docs/institutional-readiness-audit.md`.

## Property Opportunity Engine program

The governed implementation program for local property opportunity screening is tracked in `docs/property-opportunity-engine.md`. Its sequence is:

1. governed property intake and comparable evidence;
2. neighborhood/accessibility evidence and Test1 reuse;
3. renovation, operating, financing, and downside evidence;
4. backtested opportunity scoring and ranking;
5. analyst workbench and approval;
6. Test2 evidence handoff and institutional release audit.

Milestone 1 was merged in PR #60, Milestone 2 in PR #61, and Milestone 3 in PR #62. Milestone 4's scoring governance and honest no-score state are implemented on a bounded feature branch; an actual backtest remains blocked by zero eligible realized property-level acquisition outcomes. Later milestones must not bypass the evidence, approval, model-promotion, Test2, fair-housing-sensitive-field, or zero-cost boundaries.
