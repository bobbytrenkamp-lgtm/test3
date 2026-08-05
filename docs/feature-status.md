# Feature status

“Functional” means working locally; it does not mean production-ready.

| Feature | Status | Evidence / limitation |
|---|---|---|
| Deal pipeline and fictional seed | Tested | Local service tests |
| Local sign-in, sessions, CSRF and roles | Tested | Fail-closed non-echoing admin bootstrap, explicit demo mode, PBKDF2, uniform-cost checks, lockouts, hashed sessions, rotation/revocation, CSRF and roles; TLS/federation deferred |
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
| Operational integrity/readiness | Tested | Admin-only DB/schema/FK, chain, streamed-original and purge-staging probe; zero network requests |
| Backup/restore drill | Tested | Format 3 schema/table contract, manifest hashes, SQLite integrity and application-open readiness in disposable restore |
| Bounded concurrency/load | Tested | Two 100-operation/8-worker exact-count runs, zero failures; see resilience evidence |
| Original-document retention/purge | Tested | Admin reauthentication, durable staging, startup rollback/finish recovery, integrity verification, HTTP 410 and immutable tombstone; backups/history unaffected |
| Accessibility | Tested, bounded | CI static guard plus real Chromium auth/keyboard/mobile/contrast audit; assistive-tech/zoom/forced-colors certification remains |
| Security/performance/restore hardening | In development | Auth/retention/schema/readiness, purge crash recovery, measured bounded load, application-open restore and browser security/accessibility tested; final gap audit remains |
