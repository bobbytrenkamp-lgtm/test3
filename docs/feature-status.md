# Feature status

“Functional” means working locally; it does not mean production-ready.

| Feature | Status | Evidence / limitation |
|---|---|---|
| Deal pipeline and fictional seed | Tested | Local service tests |
| Local sign-in, sessions, CSRF and roles | Tested | PBKDF2, hashed opaque sessions, CSRF and role matrix; rate limiting/TLS deferred |
| Secure upload metadata/hash/duplicates | Tested | Synthetic tests |
| PDF/CSV/XLSX/image support | Tested | Local mature parsers; Tesseract optional and unavailable state tested |
| Governed field registry | Tested | 40 typed/category-scoped fields with unit, currency and downstream semantics |
| Source-linked review | Functional | Rendered page and normalized source-area highlight; browser e2e pending |
| Reconciliation center | Tested | 19 deterministic rules; immutable input-hashed runs and retained supersession history |
| Approval governance and manual assumptions | Tested | Immutable source values, typed approvals, append-only/hash-chained decisions and explicit supersession |
| test2 export | Tested, minimal | Real `cre-platform-model` shape passed test2's own `parseModelInput`; non-ready packages are explicitly blocked |
| test1 enrichment | Tested, optional | Actual seven-file test1 data directory loaded by hash with freshness/citations; approved FIPS required; no networking |
| Draft IC memo | Functional | Approved facts and source appendix |
| Optional local model | Designed | Loopback restriction; no generation adapter yet |
| Audit history | Tested | Independent serialized audit and review-decision hash chains with tamper verifiers |
| Backup/restore drill | Tested | Manifest hashes and SQLite integrity in temporary restore |
| Accessibility | In development | Semantic/responsive UI; automated review pending |
| Security/performance/restore hardening | Not started | Required before production claim |
