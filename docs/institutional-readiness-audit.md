# Institutional readiness audit

Audit date: 2026-08-04. This matrix evaluates the original application specification and absolute zero-cost override against current code, tests, CI, real-browser evidence and external adapter evidence. “Proven” means direct evidence covers the stated scope; “Partial” is not completion.

## Executive result

The project has a strong zero-cost local foundation and meaningful controls, but the full product specification is **not yet institutionally complete**. The largest remaining gaps are semantic tabular extraction/source navigation, expanded test2 entity mappings and a single automated first-usable-release workflow using three document types.

## Requirement matrix

| Requirement area | Status | Current evidence | Gap / acceptance evidence still required |
|---|---|---|---|
| Absolute zero-cost/no billable component | Proven | CI cost guard, dependency/license allowlist, cost audit, local-only adapters/probes; repeated exact pass statement | Re-audit every new dependency/service and before release |
| Repository assessment and phased plan | Proven, documentation refresh required | Required assessment/architecture/contracts exist; read-only test1/test2 evidence recorded | Keep roadmap/current handoff synchronized with merged evidence |
| Fifteen required document categories plus unknown | Proven for classification architecture | `classification.CATEGORIES` contains all named non-unknown categories; unknown fallback tested | Broader fictional classification corpus per category would strengthen confidence |
| PDF/XLSX/CSV/PNG/JPEG support | Proven, bounded | MIME/signature checks, PDFium/openpyxl/Pillow, optional local Tesseract, corrupt/unsafe tests | No extraction-accuracy benchmark; OCR requires separately installed local executable |
| Secure ingestion and original preservation | Proven | Independent MIME, size/archive limits, SHA-256, duplicate constraint, UUID paths, processing versions, no macro execution, purge/recovery, explicit malware-unavailable state | No actual malware engine by design; full-media erasure remains operator duty |
| Complete extraction provenance model | Mostly proven | Deal/document/version/category/raw/normalized/unit/currency/page/bbox/excerpt/hash/method/version/confidence/validation/review/reviewer/comment/supersession columns | Spreadsheet coordinates are logical cells, not a rendered exact-source viewer; dynamic row fields lack governed semantic types |
| Required OM/rent-roll/operations/lease/debt extractions | Mostly proven | 57 governed scalars plus immutable source-cell-backed rent-roll, operating account/period, lease schedule/options/rights and debt-term rows; derived approval and integrity tests | Broader header corpus and multi-sheet ingestion remain bounded; semantic entities are not yet mapped into test2 arrays |
| Exact click-through source review | Proven for supported source semantics | PDF/image page rendering and normalized bounding-box evidence; bounded non-executing CSV/XLSX table endpoint and highlighted logical cell navigation; excerpt fallback | Tabular view is intentionally logical rather than pixel-identical and covers the first XLSX worksheet |
| Human approval and controlling-source governance | Proven | Typed approvals, rejection rationale, append-only decision chain, explicit supersession, approved-only export | Dynamic unregistered table cells can be reviewed but lack downstream semantic governance |
| Nineteen deterministic reconciliation rules | Mostly proven | All scalar inputs are registry-governed; a real approval/service workflow persists sixteen named findings; date comparison is type-correct; immutable input-hashed runs retain supersession/resolution | Structured list inputs still await semantic row/entity ingestion, and the combined HTTP three-document release workflow remains pending |
| Professional 12-area analyst UX | Partial | All named navigation areas represented; real desktop/mobile/security/accessibility evidence | Deal overview/processing are folded into other views; spreadsheet source review and some screens remain minimal |
| test2 approved-only package | Partial, honestly bounded | Minimal property model passed actual test2 `parseModelInput`; approved-only provenance tested; every generation is an immutable versioned/hash-verified artifact with approval snapshot and history | Buildings/spaces/tenants/leases/rent steps/recoveries/expenses/capital/debt/scenarios are not mapped |
| test1 optional read-only enrichment | Proven, optional | Actual seven-file local snapshot parsed by hash with approved FIPS, dates/citations/coverage and zero requests | Upstream test1 has no license, so no code/data redistribution; user supplies local files |
| Full reviewable IC memo | Proven, deterministic | Stable 18-section schema; approved facts link to local sources; missing/unverified states, operations/rollover/debt areas, deterministic risks/questions, cautiously labeled review steps and deduplicated appendix; immutable versioned artifact tests | Narrative quality is intentionally bounded without a local model; absent information remains explicit rather than invented |
| Optional local-model provider | Designed only | Loopback URL validation and honest unavailable state | No probe/generation/metadata persistence or structured-output validation; optional core workflows do not depend on it |
| Security/privacy threat coverage | Strong but bounded | Loopback refusal, auth/CSRF/roles/lockouts/revocation, CSP/escaping, archive limits, audit integrity, retention, backup/restore, browser injection test | No federated identity/TLS network mode (network binding intentionally refused), malware scan, built-in backup encryption or formal external penetration test |
| Audit integrity and operational readiness | Proven, local | Preventive triggers, independent audit/review verifiers, schema/FK/DB/file/tombstone checks, crash recovery | Hash chains are local, not externally anchored; this is explicitly not claimed otherwise |
| Backup, restore and bounded load | Proven for recorded scope | Format 3 app-open restore; two 100-operation/8-worker exact-count runs | Not large-document/OCR/soak/hardware-failure capacity evidence |
| Accessibility | Proven for bounded browser scope | CI static guard; real Chromium auth/keyboard/mobile/contrast/injection/log audit | No assistive-technology, forced-colors or full WCAG certification |
| Complete first-usable-release E2E | Proven for specified release workflow | One real authenticated loopback HTTP test creates a deal, uploads committed fictional OM/rent-roll/T-12 fixtures, verifies classification/exact source bytes, reviews extracted cells, approves governed inputs, produces 10+ findings, resolves one, persists test2/memo artifacts and verifies history/audit/integrity | Semantic row/entity coverage and expanded test2 mapping remain P1 product-depth gaps, not hidden acceptance claims |
| Production/institutional release claim | Not achieved | README/status correctly disclaim production readiness | Close P0/P1 product gaps below and rerun this matrix |

## Ranked implementation backlog

### P0 — correctness and release workflow

1. Promote the P1 semantic row/entity and spreadsheet-source work needed for deeper diligence coverage; the bounded first-release HTTP workflow is now proven.

### P1 — semantic diligence coverage

1. Expand fictional header/category-negative coverage for the governed semantic entities and map approved entities to validated test2 arrays.
2. Extend current first-worksheet XLSX navigation only if multi-sheet semantic ingestion is added; do not claim pixel-identical rendering.
3. Expand scalar registry coverage across every explicitly required named extraction, with positive/category-negative fixtures.
4. Map supported semantic entities into the corresponding test2 arrays and execute each expanded shape through the real parser fixture.

### P2 — bounded optional/operational maturity

1. Implement the optional local-model interface only with loopback probing, opt-in invocation, structured validation and complete model/prompt/input-hash metadata; deterministic operation must remain sufficient.
2. Add assistive-technology/forced-colors/zoom evidence and larger/longer target-hardware probes without broadening network deployment.
3. Add an optional audited local backup-encryption approach only if its dependency/license/secret-handling model remains charge-impossible; otherwise retain OS-encryption guidance.

## Release rule

Do not change “not production-ready” or mark this audit complete until every P0 item has direct end-to-end evidence, every original mandatory product area is either proven or accurately scoped as a non-core optional limitation, and the final cost/license/accessibility/security/restore/load gates all pass from clean `main`.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.
