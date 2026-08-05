# Testing strategy

Tests use fictional bytes and temporary directories. Expected hashes, decimals, dates, ratios and envelopes are independently specified. Coverage includes verification, duplicates, simple PDF/CSV/XLSX, normalization, classification, provenance, confidence/review states, typed manual assumptions, immutable source normalization, explicit supersession, append-only decision enforcement, independent audit/decision-chain tamper detection, reconciliation, exports/fallback, organization predicates/roles, archive bombs, backup/restore integrity, injection escaping, unsupported/corrupt files and local-model endpoint rejection. A live HTTP smoke probe verifies unauthenticated denial, CSRF denial and an authorized mutation. The minimal generated test2 model has also been executed through test2's own public `parseModelInput` implementation in a disposable clone; see the integration contract for bounded evidence and limitations.

Readiness tests also assert the governed SQLite schema version, fail-closed rejection of future schemas, database/foreign-key health, preventive audit-event triggers, hash-chain detection after deliberate trigger bypass, streamed upload integrity and an authenticated zero-network operations probe.

The bounded concurrency probe uses 1..32 workers and 1..1000 operations, always against a newly created temporary directory. A CI-sized 8-operation regression checks exact deal/document/audit counts, chain/storage health and a real application-open restore. The recorded 100-operation/8-worker runs and limitations are in `docs/resilience-evidence.md`.

The dependency-free accessibility guard runs in CI over static semantics and CSS contracts. Real Chromium evidence covers authentication isolation/transitions, keyboard upload, responsive navigation/overflow, computed contrast, stored-markup escaping, session revocation and browser logs; see `docs/browser-accessibility-security-evidence.md` for exact results and limitations.

Not yet sufficient for production: browser accessibility/e2e automation, complex PDF corpus benchmarks, OCR failure matrix, load tests, restore drill and independent penetration review.

