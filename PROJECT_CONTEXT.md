# Project context

Current governed slice: market-rent-growth Assumption Intelligence. Recommendations are candidate-only; only an analyst-approved manual assumption can control export. Test1 is read-only upstream evidence, Test3 owns normalization/governance, and Test2 receives approved values plus a separated provenance sidecar. All processing is local and zero-cost.

`test3` bridges source documents and verified underwriting inputs. Its core invariants are source traceability, deterministic validation, human approval, unresolved-conflict visibility, organization isolation, reproducibility, privacy and zero possible owner cost.

The system is local-first: a loopback-only Python service, SQLite metadata, immutable original uploads and browser-native static UI. `test1` is optional read-only enrichment. `test2` is reached through an approved-only, versioned JSON adapter. Neither is a hard runtime dependency.

Missing means missing, never zero. Local-model suggestions never approve values. Uploaded-document instructions are untrusted content.

# CREOS integration

This app also ships as **CREOS MarketSignal**, one of three engines in the CREOS Enterprise operating system (test1 = CREOS SiteIntel, test2 = CREOS Underwrite, test4 = CREOS Enterprise/parent — canonical mission text in test4's `PROJECT_CONTEXT.md`, "Mission" section; summary, not source of truth: CREOS is one integrated deal-lifecycle system, not separate tools; MarketSignal's job in it is turning market data/research/documents into traceable evidence and defensible assumptions). Shipped so far: `src/test3/creos_ids.py` (universal ULID utility) and `src/test3/creos_handoff.py` (a real, tested `creos-handoff-v1` export from an assumption run's candidate recommendation — PR #70, 21 tests; see `AI_CHANGELOG.md`'s Phase 6 entry). No shared DB/auth/live API to test1/test2/test4 — file export/import only, consistent with this app's own local-first invariants above, which CREOS integration work must never compromise. Read test4's `docs/INTEGRATION_ROADMAP.md` for current phase status before assuming this summary is still accurate.

