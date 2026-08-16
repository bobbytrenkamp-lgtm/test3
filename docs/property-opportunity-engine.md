# Property Opportunity Engine

## Purpose

The Property Opportunity Engine turns authorized local property and comparable data into an auditable acquisition-screening package. It is deliberately separate from Test3's institutional market forecasting models. It does not appraise property, promise returns, or write underwriting assumptions into Test2.

The product boundary is:

- **Test1:** authoritative geography, parcels, zoning, restrictions, facilities, infrastructure, and policy context.
- **Test3:** source verification, comparable analysis, market evidence, model evaluation, screening recommendations, and analyst governance.
- **Test2:** detailed property cash flows, financing, valuation, returns, and final underwriting decisions.

Every production increment must preserve local-only execution, source lineage, analyst approval, immutable artifacts, and the repository cost and license guards.

## Institutional implementation plan

### Milestone 1 — Governed property intake and comparable evidence

Status: implemented on the `opportunity-engine-m1` branch.

Deliverables:

- Accept authorized local rent- and sale-comparable CSV evidence.
- Enforce file-size, row-count, date, geography, property-type, unit, and value bounds.
- Exclude future and stale observations without replacing them.
- Rank comparable evidence deterministically and expose every component of the ranking.
- Produce descriptive rent and sale benchmarks only when units are homogeneous.
- Produce an explicitly limited acquisition-basis wedge, not an appraisal or return forecast.
- Store immutable, organization-scoped research artifacts in SQLite with input and artifact hashes.
- Keep every result at `RESEARCH_CANDIDATE_NOT_UNDERWRITING`; no automatic score, approval, forecast promotion, or Test2 mutation is allowed.

Exit criteria:

- Deterministic results and hashes.
- Future/stale evidence excluded and reported.
- Mixed-unit benchmarks withheld.
- Rights and licensing notes required.
- Duplicate artifacts rejected and persisted artifacts immutable.
- Unit, service, database, audit, and boundary tests pass.

### Milestone 2 — Governed neighborhood and accessibility evidence

Status: implemented on the `opportunity-engine-m2` branch.

Deliverables:

- Extend the existing local POI analysis with governed categories for schools, grocery, retail, employment centers, transit, healthcare, parks, and downtown access.
- Consume Test1 local snapshots for parcels, zoning, restrictions, infrastructure, and jurisdiction context; never recreate Test1 pipelines.
- Add effective-dated, evidence-backed destination definitions and local travel-mode inputs.
- Distinguish straight-line distance from actual travel time and withhold unsupported claims.
- Present factual favorable and adverse evidence; never generate subjective school-quality, safety, or demographic desirability claims.

Implemented controls:

- Effective-dated local evidence for schools, grocery, shopping centers, employment centers, transit, healthcare, parks, and downtown context.
- Deterministic straight-line-distance calculations with explicit disclosure that travel time is unavailable.
- Future, stale, expired, not-yet-effective, invalid, and unsupported-category exclusions with visible counts.
- Explicit missing-coverage results rather than false absence claims.
- Reviewer-approved county-FIPS gating before Test1 enrichment; Test3 never guesses or geocodes the county.
- Read-only Test1 results retain snapshot integrity hashes, source dates, coverage, citations, and zero-network evidence.
- Prohibited inference controls for school quality, crime/safety, protected-class demographics, neighborhood desirability, and causal investment performance.

Exit criteria:

- Every location statement links to a local source record and retrieval/effective date.
- Missing categories remain missing.
- No hosted geocoder, routing, mapping, school-rating, or neighborhood-scoring API.
- Fair-housing-sensitive fields are excluded from ranking and recommendation logic.

### Milestone 3 — Renovation, operating, financing, and downside evidence

Status: implemented on the `opportunity-engine-m3` branch.

Deliverables:

- Add versioned local inputs for renovation scope, unit mix, taxes, insurance, utilities, operating expenses, debt terms, and holding costs.
- Preserve base units, timing, source, and analyst status for every assumption.
- Add deterministic sensitivities and break-even calculations with explicit formulas.
- Export candidate evidence to Test2; use Test2 for the controlling cash-flow and return calculations.
- Never infer missing expenses, loan terms, or renovation costs from unrelated comparables.

Implemented controls:

- Versioned candidate evidence for basis, renovation, known operating costs, vacancy/concessions, and financing terms.
- Exact unit, range, source-reference, licensing-note, and as-of-date validation.
- Complete-basis calculations only when every basis component exists; missing components remain explicit.
- Per-unit basis/renovation, loan-to-basis, equity requirement, known-cost ratio, and partial known-cost break-even arithmetic.
- `ADVISORY_UNAPPROVED` Test2 candidate values with automatic application disabled.
- Debt service, detailed NOI, reserves, returns, waterfalls, and controlling valuation remain outside Test3.

Exit criteria:

- All inputs are source-linked or explicitly analyst-entered.
- Scenario ranges are labeled as scenarios, not confidence intervals.
- Test2 export is advisory, versioned, and cannot overwrite an existing assumption without analyst action.

### Milestone 4 — Backtested opportunity scoring and ranking

Status: governance implemented on the `opportunity-engine-m4` branch; production score explicitly rejected because no eligible realized property-level outcome dataset is installed.

Deliverables:

- Define a versioned score policy before producing any score.
- Train and evaluate property-type-specific candidates only on legitimate, rights-documented outcomes.
- Use time-aware validation, geography holdouts, naïve baselines, stability checks, and independent implementation checks.
- Separate market forecasting evidence from property screening signals.
- Expose score components, sensitivity, coverage, limitations, and rejection reasons.

Implemented controls:

- Versioned, content-hashed multifamily score policy and property-outcome schema.
- Real-data, rights, verification, property-type, outcome-definition, lineage, duplicate, chronology, and leakage gates.
- Minimum observation, market, total-period, and per-market longitudinal-depth requirements.
- Mandatory time holdout, geography holdout, baseline improvement, stability, independent Python, optional-policy R, and immutable-lineage promotion gates.
- Synthetic outcomes can never satisfy readiness.
- The product currently emits `NO_VALIDATED_OPPORTUNITY_SCORE`, a complete rejection-reason list, `scoreProduced=false`, and `eligibleForControllingUnderwriting=false`.

Exit criteria:

- No synthetic or candidate-only observation can validate a production score.
- A score cannot promote unless it beats its governed baselines and passes leakage, lineage, sample, holdout, and stability gates.
- If no method qualifies, the product displays `NO VALIDATED OPPORTUNITY SCORE`.

### Milestone 5 — Analyst workbench and approval workflow

Status: implemented and tested on the Milestone 5 branch. The workbench shows immutable evidence, sources, economics, location, quality, score status, limitations and decision history. Decisions are separate, artifact-bound, append-only and permission-scoped; approval enforces independent review and mandatory acknowledgements, while a requested modification creates a new change request rather than editing retained evidence. See `docs/opportunity-analyst-workbench.md`.

Deliverables:

- Add property intake, comparable selection, evidence conflicts, location context, scenario comparison, and approval views.
- Provide exception-first review and deterministic clean-data samples.
- Record analyst approve, modify, or reject decisions separately from model output.
- Provide a complete artifact history and lineage drill-down.

Exit criteria:

- The interface never visually blends evidence, a model forecast, a Test3 recommendation, and an analyst-approved assumption.
- Keyboard, responsive, security, accessibility, and browser workflow tests pass.
- No demo or synthetic result appears as real evidence.

### Milestone 6 — Test2 evidence handoff and institutional release audit

Deliverables:

- Define and version the Test3-to-Test2 property-opportunity evidence contract.
- Include source hashes, comparable IDs, market-definition hashes, model versions, validation metrics, scenarios, limitations, and analyst decisions.
- Validate the payload using Test2's public parser in a disposable local test environment.
- Complete recovery, migration, performance, threat-model, cost, dependency, license, and operational-readiness evidence.

Exit criteria:

- Test3 remains advisory and Test2 remains the controlling underwriting engine.
- Old artifacts remain reproducible after policy and model changes.
- All repository checks pass from a clean local reconstruction.
- The exact zero-cost confirmation can be truthfully issued.

## Data and decision states

The engine preserves the following state progression:

`candidate evidence -> structurally valid -> rights documented -> analyst reviewed -> governed research result -> analyst decision -> optional Test2 evidence export`

No step implies the next. In particular, a research result is never an approval and an analyst-approved evidence package is never an appraisal.

## Current Milestone 1 output

Milestone 1 produces:

- selected and excluded rent comparable evidence;
- selected and excluded sale comparable evidence;
- descriptive benchmark distributions;
- a gross-potential-rent proxy when the required compatible fields exist;
- acquisition-basis scenarios derived from observed sale-comparable units;
- transparent quality components and explicit limitations;
- an immutable research-candidate artifact.

It does not yet produce:

- travel-time or parcel-level conclusions;
- renovation or detailed operating economics;
- leveraged cash flows or investment returns;
- a validated opportunity score;
- an analyst-approved underwriting assumption;
- an automatic Test2 change.

## Cost boundary

The implementation uses only Python standard-library processing, existing local Test3 components, SQLite, local files, and optional user-supplied Test1/Test2 artifacts. It has no API credentials, account dependency, hosted processing, telemetry, cloud storage, or billing path.
