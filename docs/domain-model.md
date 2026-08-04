# Domain model

- Organization owns users, deals, documents, extracted values, manual assumptions, review decisions, reconciliation runs, findings and audit events.
- A reconciliation run is append-only and records its rule-engine version, exact normalized-input SHA-256, actor, timestamp and finding count. Findings are retained permanently; a later run supersedes prior open findings rather than deleting them.
- User has admin, analyst, reviewer or viewer role. The current seed is development-only.
- Deal groups a diligence event and never owns underwriting calculations.
- Document records original name, generated storage name, independent MIME result, SHA-256, size, uploader, category and explicit malware-scan status.
- Document version identifies a reproducible processing attempt.
- Extracted value stores immutable source evidence and the latest review-state projection; source excerpt hashes guard accidental changes.
- Manual assumption is a registered, user-entered proposed value with mandatory rationale. It starts in `needs_review` and has no fictional document citation.
- Review decision is append-only, database-trigger protected and linked into an organization decision hash chain. Edited normalization lives in the decision, not in source evidence. Explicit approval of a replacement marks the prior controlling value `superseded`.
- Finding stores severity, values, sources/pages, deterministic rule, next step and human resolution.
- Audit event links to the previous organization event hash.

All organization-scoped reads include `organization_id`; repository tests exercise isolation. The decision and audit chains have independent tamper verifiers.

