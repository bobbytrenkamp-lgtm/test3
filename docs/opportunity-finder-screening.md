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

The Finder UI, lifecycle transitions, Deal Pipeline promotion, and enhanced Opportunity Detail remain the recommended scope for PR #68. Those surfaces must consume this API rather than reproduce policy logic in browser code.
