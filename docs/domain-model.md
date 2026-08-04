# Domain model

- Organization owns users, deals, documents, extracted values, findings and audit events.
- User has admin, analyst, reviewer or viewer role. The current seed is development-only.
- Deal groups a diligence event and never owns underwriting calculations.
- Document records original name, generated storage name, independent MIME result, SHA-256, size, uploader, category and explicit malware-scan status.
- Document version identifies a reproducible processing attempt.
- Extracted value stores the complete provenance/review fields required by the brief; source excerpt hashes guard accidental changes.
- Finding stores severity, values, sources/pages, deterministic rule, next step and human resolution.
- Audit event links to the previous organization event hash.

All organization-scoped reads include `organization_id`; repository tests exercise isolation.

