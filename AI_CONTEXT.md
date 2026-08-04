# AI context

## Non-negotiable constraints

- No billable, metered, trial-to-paid or card-requiring service.
- No hosted model provider. Optional model endpoints must be loopback Ollama only.
- No real deal documents or secrets in Git.
- Every extracted value retains document, page/excerpt and source-text hash.
- Only explicit human approvals enter default exports.
- Do not claim production readiness or extraction accuracy.

## Session workflow

Before a major phase run `python scripts/cost_guard.py`, tests and the license guard. Update `AI_CHANGELOG.md`, `BUG_TRACKER.md` and `docs/feature-status.md`. Preserve compatibility contracts.

