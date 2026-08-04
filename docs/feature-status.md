# Feature status

“Functional” means working locally; it does not mean production-ready.

| Feature | Status | Evidence / limitation |
|---|---|---|
| Deal pipeline and fictional seed | Tested | Local service tests |
| Local sign-in and organization/role schema | Tested | PBKDF2 + opaque local session; network/multi-user hardening deferred |
| Secure upload metadata/hash/duplicates | Tested | Synthetic tests |
| PDF/CSV/XLSX/image support | In development | Verification works; complex PDF/OCR limited |
| Source-linked review | Functional | UI and service tests; browser e2e pending |
| Reconciliation center | Tested | 19 deterministic rules |
| Approved assumptions | Functional | Approved-only query/UI |
| test2 export | In development | Contract tests pass; actual test2 import pending |
| test1 enrichment | Designed | Local fallback tested; snapshot mapping pending |
| Draft IC memo | Functional | Approved facts and source appendix |
| Optional local model | Designed | Loopback restriction; no generation adapter yet |
| Audit history | Tested | Hash-chain checks |
| Accessibility | In development | Semantic/responsive UI; automated review pending |
| Security/performance/restore hardening | Not started | Required before production claim |
