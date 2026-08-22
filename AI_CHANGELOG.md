# AI changelog

## 2026-08-22 — Human-governance approval workspace

- Added a read-only Research Lab action queue for local MAA/AVB analyst-review packets and candidate market-definition artifacts.
- Re-hashes every displayed review artifact, reports tampering separately, and exposes candidate scope, warnings, blockers, spot checks, unresolved geography evidence, and exact weight integrity.
- Keeps approval strictly human: the workspace cannot populate identity/signature fields, approve targets, or make candidate geographies feature-eligible.
- Added focused integrity, tampering, and no-auto-approval tests; the complete suite passes with all zero-cost, license, accessibility, dependency, compile, and JavaScript checks.

## 2026-08-19 — Phase 6: MarketSignal → Underwrite handoff export

- New `src/test3/creos_handoff.py`: builds a real `creos-handoff-v1` payload from one assumption run (candidate recommendation + confidence + rationale), mirroring test1 (SiteIntel)'s Phase 5 `js/parcel/handoff.js` for the same cross-repo contract.
- Real, documented translation-layer findings, not assumptions: (1) this app has no stable per-market identity a `Market` record could safely reuse across exports — a deal isn't linked to a `MarketDefinition` record — so `market` is never populated, deliberately, rather than minting a fresh random ID that would misrepresent identity continuity; (2) `property` IS populated (a deal's own name is real, stable context, and minting a fresh `propertyId` the first time a deal crosses this boundary is the same thing test1's SiteIntel handoff already does); (3) every assumption is `sourceType: 'modeled'`/`status: 'proposed'`, regardless of whether this app's own analyst has already decided the run for test3's own purposes — that decision doesn't carry to a different deal's model in Underwrite.
- Wired into `service.py` (`create_assumption_run_handoff`, read-only — an assumption run is an immutable candidate) and a new route, `POST /api/assumption-runs/{id}/handoff` (`export.generate` capability, already granted to analyst/reviewer — no new permission needed).
- Added this app's first client-side file download (`downloadJson()` in `web/app.js` — Blob + `<a download>`, same idiom test1 already uses) and a "→ Underwrite" button alongside the existing Approve low/base/high actions on each assumption-run card in the Assumption Intelligence view.
- 21 new tests (`tests/test_creos_handoff.py`): the pure builder (property/market decisions above, confidence mapping, methodology preservation, every one of the 15 catalog assumption types), plus a real end-to-end pass through `Service` reusing the market-panel fixture from `tests/test_assumption_intelligence.py` — confirms the handoff is genuinely read-only (an immutable `assumption_runs` row, regenerating the handoff twice produces the same value/status) and that an unknown run id raises cleanly. Full suite: 295/295 passing. `docs/creos-ids.md` corrected — it previously (wrongly) claimed a real handoff needed Phase 7/8 (shared auth/data layer); it doesn't, and this is the proof.

## 2026-08-07 — multi-sheet XLSX provenance tranche

- Expanded guarded XLSX extraction to as many as 64 bounded worksheets while retaining the 2,000,000-cell workbook ceiling.
- Preserved worksheet index/title and cell coordinates; formulas remain non-evaluated review evidence.
- Added worksheet-selectable authenticated table views and exact analyst source routing.
- Added schema version 5 with worksheet-aware semantic-row uniqueness and a worksheet-one migration for legacy rows.
- Added parser, HTTP, provenance, and cross-sheet collision regressions without adding a dependency or service.

## 2026-08-06 — Model-risk baselines

- Added no-look-ahead walk-forward persistence and historical-mean-change benchmarks.
- Added transparent rent-growth/vacancy market regimes and observed transition counts.

## 2026-08-06 — Institutional data governance

- Added cross-vintage revision/conflict registers, cadence-gap diagnostics and per-source scorecards.
- Added canonical research manifests linking every observation to its source snapshot and original row hash.

## 2026-08-06 — Panel factor engine

- Added reusable observed-period change factors and like-for-like market percentile scorecards.
- Added momentum, volatility and downside-deviation comparison without pooling incompatible metrics or property types.

## 2026-08-05 — Institutional data lab

- Added an audited 27-series public macro/CRE catalog and offline FRED/BLS normalization workflow.
- Added local trend, volatility, drawdown, outlier, empirical stress and exploratory lead/lag analytics.
- Preserved analyst-controlled provenance and the absolute zero-cost runtime boundary.

## 2026-08-05 — Multi-domain assumption data platform

- Generalized the first rent-growth slice into 15 governed assumption domains and expanded the import metric dictionary.
- Added local data coverage/quality profiles, segmented benchmark matrices, exact-match descriptive correlations, scalable SQLite indexes, broader Test2 growth-curve mappings, and market-original integrity checks.
- Added a zero-cost source-acquisition catalog and comprehensive assumption data dictionary.

## 2026-08-05 — Assumption Intelligence Engine

- Added additive schema version 4 for immutable market evidence, model artifacts, candidate runs, evidence links, and analyst decision context.
- Added bounded local market CSV import, Test1 economic normalization, rent-growth fallback/confidence logic, analyst approval integration, Test2 sidecar/mapping, backup format 6, UI, offline base-R pipeline, tests, and governance documentation.
- Preserved the absolute zero-cost constraint; no external runtime, account, credential, or billable service was added.

## 2026-08-04 — institutional requirement gap audit

- Re-evaluated every original product/security/testing/release area against current code, tests, CI, adapter and browser evidence.
- Identified that isolated reconciliation-rule tests do not prove runtime reachability and that semantic tables, persisted exports, expanded test2 entities and the full IC memo remain incomplete.
- Replaced stale roadmap statuses with evidence-bounded current states and added a ranked P0/P1/P2 backlog.
- Kept the project explicitly not production-ready; no code path, dependency or external service was added.

## 2026-08-04 — destructive purge crash recovery

- Added a durable bounded sidecar before original-byte staging, without copying document content or the purge reason into metadata.
- Added startup reconciliation that validates database identity, safe paths, size and SHA-256 before restoring uncommitted purges or finishing committed cleanup.
- Leaves malformed/mismatched/ambiguous artifacts untouched so readiness continues to fail visibly instead of guessing.
- Added clean-restart simulations for both crash boundaries and hash-chained automatic recovery actions.
- Added no service or dependency; recovery is local filesystem/SQLite processing only.

## 2026-08-04 — real-browser accessibility and client-security hardening

- Used the in-app browser skill against the exact loopback app at desktop and 390×844 mobile sizes with fictional data only.
- Fixed signed-out workspace reachability, missing mobile sign-out, keyboard-inaccessible upload, low-contrast helper text and mixed cached asset revisions.
- Verified semantic heading/control structure, no horizontal mobile overflow, sampled contrast (minimum 4.73:1), inert stored injection strings, session revocation and empty warning/error logs.
- Added a dependency-free CI accessibility guard for semantics, references, labeling, alt text, auth isolation, focus and reduced-motion contracts.
- Recorded reproducible evidence and limitations; no hosted accessibility scanner, external service or new dependency was added.

## 2026-08-04 — measured concurrency and application-open recovery

- Added a code-bounded local-only concurrent workload using temporary fictional deals/documents and exact persistence/audit assertions.
- Upgraded backup manifests to format 3.0 with governed schema/table contract and current-application restore integrity checks.
- Added a CI-sized concurrency/backup/restore regression and ran two 100-operation, 8-worker probes with zero failures.
- Recorded latency, throughput, backup/restore timings, exact counts, environment and limitations without claiming general production capacity.
- Added no dependency or service; temporary load and recovery processing makes zero network requests.

## 2026-08-04 — schema and operational readiness integrity

- Established governed SQLite schema version 1 and fail-closed rejection of databases created by newer application code.
- Added preventive append-only triggers for audit events while retaining independent hash-chain verification after deliberate control bypass.
- Added an authenticated administrator integrity probe covering SQLite quick/FK/schema status, audit/review chains, streamed original hashes, tombstones and purge staging.
- Added live HTTP and service regression coverage, including zero-network evidence and a Windows-safe future-schema fixture.
- Added no service or dependency; all readiness checks are local and non-billable.

## 2026-08-04 — controlled original-document retention

- Added administrator-only original-byte purge with CSRF and current-password reauthentication, mandatory reason and pre-delete size/SHA-256 verification.
- Added same-volume staging/rollback handling, provenance tombstones and database-trigger-protected append-only purge events.
- Added analyst UI confirmation, explicit residual-data warning and HTTP 410 behavior.
- Added service and live HTTP tests for denial, success, replay, retrieval and purge-event immutability.
- Documented that backups, extracted records and immutable governance history are not erased; no external storage or records service was introduced.

## 2026-08-04 — institutional local administrator bootstrap

- Removed implicit demo-credential creation from normal startup and sign-in.
- Added fail-closed first-run initialization through a non-echoing, confirmation-based terminal prompt with a 16-character minimum.
- Added local password rotation with complete session revocation and hash-chained audit events.
- Kept fictional seed data behind explicit `TEST3_DEMO_MODE=1`; removed prefilled browser credentials.
- Documented the local component in the cost/billing audit; it has no account, network call, dependency or billing mechanism.
- Removed an internal session-token hash from the browser bootstrap projection and added a non-disclosure regression assertion.

## 2026-08-04 — local authentication and session hardening

- Added deterministic process-local sign-in lockouts at account and loopback-address scopes and equal-cost unknown-account password checks.
- Added CSRF-protected server-side session revocation and a visible sign-out action.
- Centralized restrictive security headers across static, JSON, rendered-page and original-document responses; encoded response filenames safely.
- Added optional local-TLS secure-cookie mode and live HTTP replay regression coverage.
- Added no service or dependency; all controls remain local and non-billable.

## 2026-08-04 — reconciliation history integrity

- Replaced destructive reconciliation refreshes with immutable runs and retained finding supersession.
- Added exact input hashes, database immutability triggers, stale-resolution rejection, migration support and regression coverage.
- Updated the analyst UI to distinguish open, resolved and superseded findings.
- Confirmed the zero-cost and permissive-license guards; no service, account or dependency was added.

## 2026-08-04

- Audited empty `test3` and read-only shallow snapshots of `test1` and `test2`.
- Selected isolated local SQLite plus versioned adapters as the safest integration.
- Added local service, analyst UI, ingestion controls, deterministic processing, review states, reconciliation, exports and audit history.
- Added documentation, zero-cost and license guards, CI and fictional-data tests.
- Added PBKDF2 local fictional sign-in and opaque HttpOnly/SameSite sessions.
- Declined hosted deployment and hosted AI paths because they cannot satisfy the absolute zero-cost rule.

## 2026-08-04 — Security and operability tranche

- Enforced role permissions and CSRF tokens on every authenticated mutation.
- Replaced plaintext session identifiers in SQLite with SHA-256 token digests; added expiry cleanup and legacy-session invalidation.
- Serialized audit writes and added full hash-chain verification/tamper detection.
- Added XLSX expanded-size, entry, compression-ratio, row and cell safety limits.
- Added non-overwriting local backups with file manifests, hashes and temporary restore/integrity drills.
- Expanded the suite to 30 tests and validated 401/CSRF/authorized-create behavior over live HTTP.

## 2026-08-04 — Document processing tranche

- Audited and exact-pinned pypdfium2/PDFium, Pillow, openpyxl, defusedxml and transitive et_xmlfile; all are local and permissively licensed.
- Added PDFium page-aware text extraction and normalized source bounding boxes.
- Added local rendered-PDF page endpoint and analyst source-area highlighting.
- Added Pillow decode/pixel safety checks and optional local Tesseract image/scanned-PDF OCR with confidence/bounding provenance.
- Replaced direct XLSX XML parsing with guarded openpyxl read-only parsing; formulas remain unexecuted candidates and macro-enabled files are rejected.

## 2026-08-04 — test2 contract tranche

- Replaced the nominal test3-shaped handoff with a real nested test2 `cre-platform-model` document.
- Made import readiness fail closed when approved forecast, valuation or property inputs are missing or invalid.
- Kept rejected and pending values out of both the model and supporting-source manifest.
- Executed the fictional minimal model through test2's own `parseModelInput` implementation without adding a runtime dependency.
- Honored test2's supply-chain policy when its disposable dependency install rejected newly published lockfile entries; no policy was relaxed.

## 2026-08-04 — extraction governance tranche

- Replaced the ten-field global pattern map with a typed, category-scoped institutional field registry.
- Added deterministic rate, basis-point, integer and date normalization plus registry-derived units and currencies.
- Added category-negative tests so unrelated document types do not emit misleading candidates.
- Preserved tabular row identity and the mandatory human-review boundary.

## 2026-08-04 — approval governance tranche

- Preserved extracted normalization as immutable source evidence and moved reviewer edits into append-only decisions.
- Added database immutability triggers, serialized decision hashes and an independent tamper verifier.
- Added registered, rationale-required manual assumptions that begin pending and retain user-entered provenance.
- Added typed approval validation and explicit supersession of the prior controlling value.
- Included assumption and decision counts in backup restore verification.
- Replaced native prompt interactions with labeled review/resolution forms and completed a clean-console browser workflow.

## 2026-08-04 — test1 local snapshot tranche

- Implemented a strict reader for test1's actual static metadata, policy, political-risk, water, incentive, facility and state-regulation files.
- Added per-file hashes/byte counts, duplicate-key rejection, source/dataset freshness and bounded facility summaries.
- Required an approved typed county FIPS and kept all unavailable/unresearched states explicit.
- Proved compatibility against test1 commit `aa8ab706…` with zero network requests and conservative verification semantics.
- Redistributed no test1 code or data because the source repository has no license file.
- Completed the configured browser path with six context cards, visible freshness/limitations/citations and a clean console.

## 2026-08-04 — canonical reconciliation contract tranche

- Expanded the governed registry from 40 to 57 fields so every scalar rule input has a type, unit, category scope and review boundary.
- Replaced unreachable aliases with canonical existing names for NOI, unit count and interest rate comparisons.
- Corrected lease expiration reconciliation to compare normalized calendar dates without decimal coercion.
- Added a contract regression and a real service workflow that appends 31 approvals and persists sixteen named discrepancies with user-entered provenance.
## 2026-08-04 — immutable export artifact tranche

- Persisted every test1, test2 and memo generation as canonical JSON with content and approval-snapshot SHA-256 hashes.
- Added per-deal/kind versioning, actor/schema metadata, append-only triggers and organization-scoped history/retrieval APIs.
- Extended operational integrity and backup format 4.0 to cover artifact presence and hash validity.
- Updated the browser to acknowledge the locally saved artifact version while preserving content rendering.
## 2026-08-04 — complete IC memo tranche

- Replaced the minimal five-element summary with stable `test3-ic-memo/2.0` coverage of all 18 required areas.
- Limited factual sections to approved values with local document/page links or user-entered rationale.
- Added received/missing sources, explicit missing sections, excluded-value disclosures, deterministic diligence questions/risks and cautiously labeled review steps.
- Rendered the complete schema with escaped content and local links inside the analyst interface; memo artifacts remain deterministic and local.
## 2026-08-04 — first usable release acceptance tranche

- Added three committed fictional OM, rent-roll and T-12 fixtures.
- Proved the complete defined analyst workflow through real authenticated loopback HTTP routes and a fresh database.
- Required exact source retrieval, review decisions, eleven reachable discrepancies, resolution, immutable test2/memo artifacts, audit actions and final operational integrity.
- Documented the acceptance boundary: scalar assumptions are governed, while deeper semantic table models remain an explicit P1 gap.
## 2026-08-04 — tabular source navigation tranche

- Added an authenticated, organization-scoped CSV/XLSX table source endpoint using existing guarded local parsers.
- Bounded previews to 500 rows, 200 columns and 20,000 cells with explicit truncation and formula non-execution metadata.
- Rendered escaped cells in the analyst source pane and highlighted the exact stored logical coordinate.
- Added live HTTP coverage for all three CSV release fixtures and a fictional XLSX source.
## 2026-08-04 — semantic diligence entity tranche

- Added immutable governed rent-roll, operating account/period, lease schedule/options and debt-term row entities.
- Bound every semantic record to its document/version/source row, canonical SHA-256 and exact extracted-cell IDs.
- Derived entity approval from all constituent append-only cell decisions, preventing row-level approval bypass.
- Added semantic integrity verification, schema version 3 and backward-readable backup format 5.0.
## 2026-08-04 — semantic entity review surface tranche

- Added an analyst table for semantic entity type, canonical fields, document/source row and derived review state.
- Linked each entity to a constituent cell in the exact source viewer without adding a row-level approval bypass.
- Extended the live first-release response assertion to require rent-roll and operating semantic records.

## 2026-08-04 — semantic export and release-hardening tranches

- Mapped fully approved, schema-complete semantic spaces, tenants, leases, expenses and debt into test2, with per-row fail-closed diagnostics and real parser evidence at audited test2 commit `9a0581e`.
- Expanded category-scoped fictional header aliases and added negative tests preventing cross-category semantic assignment.
- Added an opt-in loopback-only Ollama probe/JSON-generation interface with redirect blocking, prompt bounds, structured validation, required provenance metadata and candidate-only outputs.
- Re-ran complete local and GitHub CI gates after each focused pull request and updated the final institutional-readiness boundary.
# 2026-08-22 — Durable CREOS identity and source-linked handoffs

- Added an organization-scoped, immutable `creos_entity_links` registry so
  MarketSignal exports preserve property, deal, assumption, handoff, source,
  and provenance identities across repeated CREOS handoffs.
- Made assumption-run handoffs reproducible: the same immutable run now emits
  the same IDs and timestamp, while distinct runs for one deal share the same
  property identity and retain distinct assumption identities.
- Added CREOS Source and Provenance objects for every referenced Test3 evidence
  snapshot, including local source record ID, version, content hash, retrieval
  date, effective date, and license notes. Underwrite no longer receives a
  modeled assumption detached from its evidence inventory.
- Extended operational integrity and backup/restore to schema 12 / backup 12.0,
  with tests for identity immutability, lineage referential integrity, repeated
  export equivalence, and cross-run property continuity.
- No hosted service, paid API, credential, or billing-capable dependency added.
