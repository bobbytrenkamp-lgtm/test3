# Property opportunity evidence contract for Test2

Schema: `test3-test2-property-opportunity-evidence/1.0.0`.

Test3 creates this sidecar only when the latest decision for an immutable property-opportunity run is `approved`. The approval must already have passed artifact integrity, quality blockers, required acknowledgements, role authorization, and creator/approver separation. A later rejection or change request prevents a new handoff.

The sidecar contains the deal and run IDs; opportunity artifact and input hashes; analysis date and policy version; approval ID, hash, reviewer, rationale and time; subject facts; source names, rights states, licensing notes and file hashes; stable rent/sale comparable reference hashes; available market-definition hashes; governed economic evidence and screening scenarios; explicit no-score or validated-score evidence; quality; limitations; and a content SHA-256.

The envelope always declares:

- `status = ADVISORY_APPROVED_EVIDENCE_NOT_APPLIED`
- `automaticApply = false`
- `controllingUnderwritingEngine = test2`

It is evidence, not a Test2 model mutation. Test2 or an analyst must explicitly decide which facts or assumptions to use. A screening scenario is not a valuation, appraisal, return forecast, or controlling underwriting case. A missing market-definition hash stays missing.

Each approval decision can generate at most one handoff. Handoffs are append-only, organization-scoped, versioned per deal, hash-verified on retrieval, covered by operational integrity, audit history, schema version 8, and backup format 8.0.

## Compatibility boundary

This is a sidecar evidence contract, not the existing `cre-platform-model` underwriting model. It intentionally does not insert buildings, leases, expenses, debt, growth curves, or assumptions into Test2. The existing approved-fact Test2 export remains the only Test3 path that constructs that portable model shape.

