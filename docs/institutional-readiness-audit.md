# Institutional readiness audit

Audit date: 2026-08-04. This matrix evaluates the original application specification and absolute zero-cost override against current code, tests, CI, real-browser evidence and external adapter evidence. “Proven” means direct evidence covers the stated scope; “Partial” is not completion.

## Executive result

The project has a strong zero-cost local foundation and meaningful controls, but the full product specification is **not yet institutionally complete**. The largest remaining gaps are product coverage rather than infrastructure: semantic tabular extraction, runtime-reachable reconciliation inputs, persisted/versioned exports, the complete IC memo, and a single automated first-usable-release workflow using three document types.

## Requirement matrix

| Requirement area | Status | Current evidence | Gap / acceptance evidence still required |
|---|---|---|---|
| Absolute zero-cost/no billable component | Proven | CI cost guard, dependency/license allowlist, cost audit, local-only adapters/probes; repeated exact pass statement | Re-audit every new dependency/service and before release |
| Repository assessment and phased plan | Proven, documentation refresh required | Required assessment/architecture/contracts exist; read-only test1/test2 evidence recorded | Keep roadmap/current handoff synchronized with merged evidence |
| Fifteen required document categories plus unknown | Proven for classification architecture | `classification.CATEGORIES` contains all named non-unknown categories; unknown fallback tested | Broader fictional classification corpus per category would strengthen confidence |
| PDF/XLSX/CSV/PNG/JPEG support | Proven, bounded | MIME/signature checks, PDFium/openpyxl/Pillow, optional local Tesseract, corrupt/unsafe tests | No extraction-accuracy benchmark; OCR requires separately installed local executable |
| Secure ingestion and original preservation | Proven | Independent MIME, size/archive limits, SHA-256, duplicate constraint, UUID paths, processing versions, no macro execution, purge/recovery, explicit malware-unavailable state | No actual malware engine by design; full-media erasure remains operator duty |
| Complete extraction provenance model | Mostly proven | Deal/document/version/category/raw/normalized/unit/currency/page/bbox/excerpt/hash/method/version/confidence/validation/review/reviewer/comment/supersession columns | Spreadsheet coordinates are logical cells, not a rendered exact-source viewer; dynamic row fields lack governed semantic types |
| Required OM/rent-roll/operations/lease/debt extractions | Partial | 40 governed scalar fields plus generic CSV/XLSX cells | Many named fields/schedules/options/accounts are absent; repeated rows are not converted to semantic tenant/lease/period records |
| Exact click-through source review | Partial | PDF/image page rendering and normalized bounding-box browser evidence; excerpt fallback | CSV/XLSX exact cell/sheet rendering and source-area navigation are missing |
| Human approval and controlling-source governance | Proven | Typed approvals, rejection rationale, append-only decision chain, explicit supersession, approved-only export | Dynamic unregistered table cells can be reviewed but lack downstream semantic governance |
| Nineteen deterministic reconciliation rules | Partial | Decimal rule unit tests, immutable input-hashed runs, retained supersession/resolution | Several rule input names are absent from the registry/runtime pipeline; a direct 10+ finding function test does not prove end-to-end reachability |
| Professional 12-area analyst UX | Partial | All named navigation areas represented; real desktop/mobile/security/accessibility evidence | Deal overview/processing are folded into other views; spreadsheet source review and some screens remain minimal |
| test2 approved-only package | Partial, honestly bounded | Minimal property model passed actual test2 `parseModelInput`; blockers and provenance tested | Buildings/spaces/tenants/leases/rent steps/recoveries/expenses/capital/debt/scenarios are not mapped; exports are generated responses, not persisted versions |
| test1 optional read-only enrichment | Proven, optional | Actual seven-file local snapshot parsed by hash with approved FIPS, dates/citations/coverage and zero requests | Upstream test1 has no license, so no code/data redistribution; user supplies local files |
| Full reviewable IC memo | Partial | Draft flag, approved facts, discrepancies and source appendix | Most required sections (sources missing, operations, rollover, debt, risks/mitigants, unverified statements) are absent |
| Optional local-model provider | Designed only | Loopback URL validation and honest unavailable state | No probe/generation/metadata persistence or structured-output validation; optional core workflows do not depend on it |
| Security/privacy threat coverage | Strong but bounded | Loopback refusal, auth/CSRF/roles/lockouts/revocation, CSP/escaping, archive limits, audit integrity, retention, backup/restore, browser injection test | No federated identity/TLS network mode (network binding intentionally refused), malware scan, built-in backup encryption or formal external penetration test |
| Audit integrity and operational readiness | Proven, local | Preventive triggers, independent audit/review verifiers, schema/FK/DB/file/tombstone checks, crash recovery | Hash chains are local, not externally anchored; this is explicitly not claimed otherwise |
| Backup, restore and bounded load | Proven for recorded scope | Format 3 app-open restore; two 100-operation/8-worker exact-count runs | Not large-document/OCR/soak/hardware-failure capacity evidence |
| Accessibility | Proven for bounded browser scope | CI static guard; real Chromium auth/keyboard/mobile/contrast/injection/log audit | No assistive-technology, forced-colors or full WCAG certification |
| Complete first-usable-release E2E | Partial | Service workflow and live HTTP/browser tests cover major slices | No single automated workflow signs in, uploads fictional OM + rent roll + T-12, reviews source links, produces 10+ reachable findings, resolves and persists versioned export/memo/audit |
| Production/institutional release claim | Not achieved | README/status correctly disclaim production readiness | Close P0/P1 product gaps below and rerun this matrix |

## Ranked implementation backlog

### P0 — correctness and release workflow

1. Define one canonical governed field contract for every reconciliation input; make at least ten rules reachable from actual approved extracted/manual data and add a full service/HTTP E2E.
2. Persist immutable export artifacts with version, hash, schema, actor and approval snapshot; support retrieval/history.
3. Build complete required IC memo sections with explicit missing/unverified states and source links.
4. Add fictional OM, rent-roll and T-12 fixtures that exercise classification, semantic extraction, source review, approvals, reconciliation, resolution, export, memo and audit.

### P1 — semantic diligence coverage

1. Add governed row/entity models for rent-roll tenants/units, operating periods/accounts, lease schedules/options and debt terms rather than relying only on `row.<n>.<header>` fields.
2. Add CSV/XLSX sheet/cell source rendering/navigation.
3. Expand scalar registry coverage across every explicitly required named extraction, with positive/category-negative fixtures.
4. Map supported semantic entities into the corresponding test2 arrays and execute each expanded shape through the real parser fixture.

### P2 — bounded optional/operational maturity

1. Implement the optional local-model interface only with loopback probing, opt-in invocation, structured validation and complete model/prompt/input-hash metadata; deterministic operation must remain sufficient.
2. Add assistive-technology/forced-colors/zoom evidence and larger/longer target-hardware probes without broadening network deployment.
3. Add an optional audited local backup-encryption approach only if its dependency/license/secret-handling model remains charge-impossible; otherwise retain OS-encryption guidance.

## Release rule

Do not change “not production-ready” or mark this audit complete until every P0 item has direct end-to-end evidence, every original mandatory product area is either proven or accurately scoped as a non-core optional limitation, and the final cost/license/accessibility/security/restore/load gates all pass from clean `main`.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.
