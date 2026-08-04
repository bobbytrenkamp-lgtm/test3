# Testing strategy

Tests use fictional bytes and temporary directories. Expected hashes, decimals, dates, ratios and envelopes are independently specified. Coverage includes verification, duplicates, simple PDF/CSV/XLSX, normalization, classification, provenance, confidence/review states, reconciliation, exports/fallback, organization predicates/roles, audit chain and tamper detection, archive bombs, backup/restore integrity, injection escaping, unsupported/corrupt files and local-model endpoint rejection. A live HTTP smoke probe verifies unauthenticated denial, CSRF denial and an authorized mutation.

Not yet sufficient for production: browser accessibility/e2e automation, complex PDF corpus benchmarks, OCR failure matrix, load tests, restore drill and independent penetration review.

