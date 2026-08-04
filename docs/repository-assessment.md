# Repository assessment

Assessment date: 2026-08-04. `test1` and `test2` were inspected using read-only shallow temporary clones; neither repository was modified.

## test3 starting point

The repository contained only `.git`, had no commits and no branch on the remote. There was no working code to preserve and no nested repository was created.

## test1 findings

`test1` is a static HTML/CSS/JavaScript application with Python data pipelines and local JSON artifacts. Its jurisdiction records use stable identifiers such as county FIPS and preserve source, verification, freshness and coverage concepts. Relevant local artifacts include state restrictions, county/city policy, zoning schemas, water stress, tax incentives, economic metadata and facility context. It already owns jurisdiction collection, mapping and derived political/readiness context; `test3` must not duplicate those pipelines.

The adapter should read an explicitly exported local snapshot keyed by FIPS/address/parcel identifiers and retain test1 citations and freshness. Missing snapshots or unmatched coverage must degrade honestly.

## test2 findings

`test2` is a pnpm TypeScript monorepo with web/API/worker applications and packages for domain models, database, deterministic calculations and reporting. Hand-written SQL migrations model organizations, properties, spaces, leases, assumptions, jobs and audit records. Its reporting package owns rent-roll imports and portable exports. Decimal strings and explicit enums avoid floating-point ambiguity.

`test3` must not duplicate underwriting calculations, waterfalls, valuation, scenario, portfolio or reporting engines. It should export approved source facts through a versioned package with diagnostics, then validate against a real test2 fixture/adapter before claiming direct compatibility.

## Safest integration

| Boundary | Approach | Reason |
|---|---|---|
| test3 → test2 | Downloadable versioned JSON; approved values only | Reproducible, inspectable, no cross-database coupling |
| test1 → test3 | Optional read-only local JSON snapshot | test3 remains functional offline; no third-party requests |
| Documents | Immutable local originals and source hashes | Privacy and provenance |
| Identity | Separate test3 organization scope | Prevents accidental cross-product authorization assumptions |

## Duplication avoided

- test1: policy collection, jurisdiction scoring, zoning/facility mapping and economic pipelines.
- test2: underwriting math, valuation, recoveries, debt schedules, waterfall calculations, scenarios and portfolio reporting.

## Audit caveats

The assessment reflects the default branches as downloaded on 2026-08-04. Integration claims remain provisional until test2 executes a contract fixture. Repository licenses and vendored assets must be rechecked when code—not just data—is reused; this implementation copies no source code from either repository.

