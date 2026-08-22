# Opportunity Finder deterministic screening

Opportunity Finder is the upstream discovery layer in Test3's governed workflow:

`Find -> Investigate -> Verify -> Approve -> Diligence -> Underwrite`

It is separate from Opportunity Review. Finder prioritizes candidates for analyst attention; Opportunity Review remains the immutable evidence-approval surface. Test2 remains the controlling underwriting engine.

## Screening tier is not an opportunity score

The versioned `OpportunityScreeningPolicy` produces one of four workflow tiers:

- `HIGH_PRIORITY_REVIEW`
- `WORTH_REVIEWING`
- `LOW_PRIORITY`
- `INSUFFICIENT_EVIDENCE`

These tiers are deterministic review priorities, not predictions, investment recommendations, appraisals, or expected-return estimates. Each result includes the exact policy ID, version and hash; evaluation time; source-evidence hash; normalized input hash; evidence completeness; conservative evidence age; a structured freshness breakdown; explicit reasons; explicit warnings; derived Decimal metrics; and a result hash. `analysis_as_of` cannot be later than the UTC evaluation date.

The statistically governed opportunity-score system remains separate. Until eligible realized property outcomes pass time and geography holdouts, baseline competition, stability checks, independent implementation checks, and immutable-lineage gates, the score state remains:

`NO_VALIDATED_OPPORTUNITY_SCORE`

A screening tier never changes that state and never authorizes automatic underwriting.

## Initial policy

Policy `opportunity-finder-deterministic-screening/1.0.0` evaluates only supplied evidence. It never converts missing values to zero. Its evidence dimensions are rent, basis, NOI, cap-rate context, vacancy context, comparables, and location. A dimension counts toward completeness only when the required values exist, an effective evidence date exists, and valid SHA-256 provenance is supplied.

The policy can surface transparent positive review signals such as:

- subject rent below source-linked market-rent evidence;
- acquisition basis below source-linked comparable-sale evidence;
- stabilized NOI above current NOI;
- subject cap rate above source-linked market context;
- subject vacancy above source-linked market vacancy; and
- sufficient source-linked comparable support.

High-priority review requires multiple strong signals, current evidence, governed comparable lineage, and broad evidence coverage. Moderate evidence can be worth reviewing. Complete but unexceptional evidence is low priority. Missing lineage, missing dates, inadequate breadth, or no substantive signal evidence produces insufficient evidence or a lower tier. Stale evidence cannot receive the high-priority tier.

Thresholds are explicit fields on the policy, content-hashed, and independently testable. Changing a threshold or version changes the policy and input hashes.

## Precision and provenance

Money and rates use Python `Decimal`; authoritative screening calculations do not use JavaScript or binary floating point. Rent gaps, basis discounts, NOI deltas and ratios, cap-rate spreads, and vacancy deltas remain exact where decimal arithmetic permits. Units must be explicit for rent and basis comparisons. Partial pairs remain missing rather than being inferred.

Every relied-upon dimension carries field-level source hashes and an evidence date. The combined evidence hash and normalized input snapshot hash allow future persistence/API layers to bind screening results to the exact evidence evaluated. A result also records `automaticUnderwritingApply = false`.

## Persistent Opportunity Finder contract

SQLite schema version 9 persists three organization-scoped records:

- `opportunity_candidates`: stable candidate identity and optional linkage to an existing deal. Candidate creation never creates a deal.
- `opportunity_candidate_versions`: immutable, sequential, content-hashed evidence snapshots. A `BEGIN IMMEDIATE` transaction assigns each version number safely.
- `opportunity_screening_runs`: immutable bindings between a candidate version, policy hash, input/evidence hashes, and complete screening result.

The JSON API provides bounded list/filter/sort pagination and candidate detail/history endpoints:

- `GET /api/opportunities`
- `POST /api/opportunities`
- `GET /api/opportunities/{id}`
- `POST /api/opportunities/{id}/versions`
- `POST /api/opportunities/{id}/screen`
- `GET /api/opportunities/{id}/history`

Analysts have separate `opportunity.create` and `opportunity.screen` permissions. Reviewers can read candidates and retain the independent `opportunity.review` authority, but cannot create evidence or run Finder screening. API clients must send financial and rate values as decimal strings (or exact integers); JSON floats are rejected. Clients cannot submit tiers, reasons, derived metrics, or any other server-computed result.

The current screening projection is derived from the latest immutable run. Operational integrity reproduces every screening result from its persisted evidence version and evaluation timestamp, verifies all hashes and membership bindings, and fails closed on tampering. Backup format 9.0 includes these records; prior backup formats remain readable.

The Finder UI and enhanced Opportunity Detail remain the recommended scope for PR #69. Deal Pipeline promotion remains a later governed workflow. Those surfaces must consume this API rather than reproduce policy logic in browser code.

## Hardening and query semantics

Finder evidence is historical evidence, not a future scenario schema. Evidence-version creation rejects an `analysis_as_of` later than the current UTC date, any dimension evidence date later than `analysis_as_of`, and an insurance evidence date later than `analysis_as_of`. The screening engine repeats these chronology checks as defense in depth. A future planning workflow must use a separately governed scenario-effective date rather than overloading `analysis_as_of`.

The current screening projection is the newest screening run for the highest evidence version that has actually been screened. It is never silently presented as current when newer evidence exists. API responses expose:

- `latest_evidence_version` and its analysis date;
- `latest_screened_version`;
- `screening_currency_status`: `CURRENT`, `OUTDATED_EVIDENCE`, or `NOT_SCREENED`; and
- the immutable run projection used for display.

The preferred name for that retained run is `latest_screening`. `current_screening` remains a deprecated compatibility alias and can refer to an older evidence version when `screening_currency_status` is `OUTDATED_EVIDENCE`; clients must not infer currency from the alias name.

Workflow tier ordering is explicit: `HIGH_PRIORITY_REVIEW` (1), `WORTH_REVIEWING` (2), `LOW_PRIORITY` (3), `INSUFFICIENT_EVIDENCE` (4), and no screening (5). `screening_priority_rank` is only an analyst-workflow ordering. It is not an opportunity score, expected return, investment recommendation, or underwriting conclusion.

List projections expose exact decimal strings for rent gap, basis discount, evidence-supported NOI delta, NOI ratio, cap-rate spread, and vacancy delta. Test3 compares supplied current and stabilized NOI evidence; it does not forecast NOI in Finder. Test2 remains responsible for controlling underwriting. Completeness, evidence age, reason/warning counts, score availability, and screening currency are also projected from the immutable result so browser code does not reproduce authoritative calculations.

The bounded list endpoint supports deterministic search across display name, address, market, and submarket plus filters for property type, market, lifecycle status, tier, screening currency, completeness range, minimum rent/basis gaps, and maximum evidence age. Search is limited to 200 characters and escapes SQL wildcard characters. Tier sorting uses workflow rank. Completeness sorts numerically. Freshness sorts by evidence age: ascending means fresher first and descending means stalest first. The version and screening indexes support local pagination; a committed test exercises the bounded projection at 10,000 candidates.

Authoritative completeness, rent-gap, and basis-discount threshold inclusion uses SQLite deterministic scalar functions backed by Python `Decimal`. SQLite `REAL` is retained only for approximate display ordering. Exact comparison preserves boundary behavior, totals, and pagination for values immediately above, equal to, and immediately below a threshold without adding duplicated projection columns or changing the database/backup format.

`Service.opportunity_candidate_query_plan()` exposes the representative bounded query through `EXPLAIN QUERY PLAN`. Tests verify use of `opportunity_candidates_list`, `opportunity_candidate_versions_candidate`, and `opportunity_screening_runs_candidate`; SQLite may still use a bounded temporary B-tree for the derived tier/version ordering. `scripts/opportunity_finder_scale_benchmark.py` creates an ignored, temporary 10,000-candidate fictional fixture with more than 15,000 evidence versions and 8,000 screening runs, then measures the required filter, sort, search, exact-threshold, and high-offset queries. The standard CI fixture is smaller but retains the same relational shapes and all currency/tier states.

Address duplicate warnings use conservative normalization only: case and whitespace normalization, harmless punctuation removal, and a small explicit street-suffix dictionary. Unit/subunit text remains part of identity. The system never geocodes, fuzzily matches, merges, or blocks candidate creation.

The only lifecycle transition introduced here is the explicit, audited `candidate -> archived` action at `POST /api/opportunities/{id}/archive`. Archiving retains every evidence version and screening run. Archived candidates remain queryable with `status=archived`; they cannot receive new evidence or screening. Promotion and reopening remain separate future governed workflows.

Archive timestamps returned from the action and candidate detail are read from the immutable `opportunity.candidate_archived` audit event. A transient application timestamp is not treated as lifecycle evidence.

Historic policy implementations are immutable and registered by policy ID and version. Integrity reproduction selects the exact registered policy and verifies its stored hash. It never evaluates an old run with a newer default policy. If an implementation is unavailable or its hash differs, integrity reports `policyImplementationUnavailable`, counts a screening mismatch, and fails closed.

## Opportunity Finder interface

The local interface uses the bounded `GET /api/opportunities` query for search, filters, sorting, pagination, and filter-aware summary counts. It never recreates screening calculations in JavaScript. Common financial projections remain exact decimal strings in the API and are formatted only for display. The list defaults to active candidates and explicit workflow-priority ordering; archived candidates remain available through the status filter.

Candidate detail keeps three states visibly separate: immutable evidence versions, immutable screening runs, and screening currency. `OUTDATED_EVIDENCE` is rendered as **New evidence — rescreen**, while the retained historic run remains inspectable. Viewer and reviewer roles are read-only. Analyst and administrator roles may create a candidate, add a new immutable evidence version, invoke server-side screening, and archive an active candidate. Archive is a retained, audited lifecycle transition rather than deletion.

The interface labels the server's NOI comparison as **Evidence-supported NOI delta** and explicitly states that it is a comparison of supplied current and stabilized evidence, not a Test2 forecast. Missing values render as an em dash, never as zero. The validated-score panel reports that no validated opportunity score exists until governed realized-outcome data supports one.
