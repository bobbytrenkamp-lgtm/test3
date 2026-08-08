# Feature status

“Functional” means working locally; it does not mean production-ready.

| Feature | Status | Evidence / limitation |
|---|---|---|
| Deal pipeline and fictional seed | Tested | Local service tests |
| Local sign-in, sessions, CSRF and roles | Tested | Fail-closed non-echoing admin bootstrap, explicit demo mode, PBKDF2, uniform-cost checks, lockouts, hashed sessions, rotation/revocation, CSRF and roles; TLS/federation deferred |
| Secure upload metadata/hash/duplicates | Tested | Synthetic tests |
| PDF/CSV/XLSX/image support | Tested | Local mature parsers; Tesseract optional and unavailable state tested |
| Governed field registry | Tested | 57 typed/category-scoped fields with unit, currency and downstream semantics; every scalar reconciliation input is covered |
| Source-linked review | Tested, bounded | PDF/image rendered-page evidence plus CSV and bounded multi-sheet XLSX logical cell navigation; tabular view is not pixel-identical |
| Reconciliation center | Tested | 19 deterministic rules; immutable input-hashed runs and retained supersession history |
| Approval governance and manual assumptions | Tested | Immutable source values, typed approvals, append-only/hash-chained decisions and explicit supersession |
| test2 export | Tested, bounded | Minimal and expanded `cre-platform-model` shapes passed test2's own `parseModelInput`; fully approved rows map to spaces/tenants/leases/expenses/debt with fail-closed row diagnostics; advanced arrays remain intentionally unmapped |
| test1 enrichment | Tested, optional | Actual seven-file test1 data directory loaded by hash with freshness/citations; approved FIPS required; no networking |
| Draft IC memo | Tested | Stable 18-section schema; approved-only source-linked facts, missing/unverified states, deterministic risks/questions, qualified-review labels, source appendix and immutable artifact history |
| Optional local model | Tested, opt-in | Loopback-only Ollama probe/generation interface, bounded prompts, JSON-object validation and full model/prompt/input-hash/time metadata; outputs are candidate-only and no core workflow depends on it |
| Audit history | Tested | Independent serialized audit and review-decision hash chains with tamper verifiers |
| Operational integrity/readiness | Tested | Admin-only DB/schema/FK, chain, streamed-original and purge-staging probe; zero network requests |
| Backup/restore drill | Tested | Format 3 schema/table contract, manifest hashes, SQLite integrity and application-open readiness in disposable restore |
| Bounded concurrency/load | Tested | Two 100-operation/8-worker exact-count runs, zero failures; see resilience evidence |
| Original-document retention/purge | Tested | Admin reauthentication, durable staging, startup rollback/finish recovery, integrity verification, HTTP 410 and immutable tombstone; backups/history unaffected |
| Accessibility | Tested, bounded | CI static guard plus real Chromium auth/keyboard/mobile/contrast audit; assistive-tech/zoom/forced-colors certification remains |
| Security/performance/restore hardening | In development | Auth/retention/schema/readiness, purge crash recovery, measured bounded load, application-open restore and browser security/accessibility tested; final gap audit remains |
| Immutable export artifacts | Tested | Per-kind versions, canonical content/approval hashes, actor/schema metadata, append-only database guards, scoped retrieval/history, readiness and backup coverage |
| First usable release E2E | Tested | Live authenticated HTTP workflow with committed fictional OM/rent-roll/T-12 fixtures, exact source retrieval/review, 10+ findings, resolution, immutable exports/memo, audit and integrity |
| CSV/XLSX exact logical source view | Tested | Authenticated bounded table endpoint, escaped cell rendering, selected-coordinate highlight and explicit no-formula execution across up to 64 worksheets |
| Governed semantic table entities | Tested | Immutable rent-roll, operating account/period, lease schedule/options and debt-term rows with worksheet/row provenance, hashes, exact source-cell membership, derived approval, analyst row/source UI, bounded test2 mappings and readiness/backup coverage |
