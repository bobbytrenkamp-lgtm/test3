# Claude Skills under the zero-cost policy

Audit date: 2026-08-08.

## Safe supported approach

Anthropic currently documents custom Skills for its Free plan when code execution is enabled. A free account is required; a payment method is not required for the Free plan; usage stops at session limits instead of creating an overage charge. This repository therefore includes a static, dependency-free candidate-extraction Skill under `integrations/claude-skills/` and a local validator in `test3.claude_skills`.

The optional workflow is deliberately manual:

1. Use only a Claude Free account with no payment method, paid subscription, Console billing, or usage credits.
2. Review and ZIP the `test3-cre-candidate-extraction` folder.
3. In Claude, enable code execution, open Customize > Skills, and upload the ZIP.
4. Upload only a fictional, public, or explicitly authorized document plus its local SHA-256.
5. Download the resulting JSON.
6. Validate it locally with `test3-skill-validate candidate.json --document-sha256 <local-document-hash>`.
7. Place every validated value into the existing analyst-review workflow as a candidate; validation never approves it.

This path is optional and never invoked by Test3. Uploaded content leaves the local computer and is processed by Anthropic, so confidential OMs, leases, appraisals and tenant data must not be uploaded without an explicit data/privacy decision. Recheck plan terms before each use because free-product availability can change.

## Rejected automated path

Claude Code is not a zero-cost Test3 integration. Anthropic currently documents Claude Code authentication through active Console billing or a paid Pro/Max subscription. API/Console usage is billable and may use prepaid or automatically replenished credits. Test3 therefore does not install Claude Code, invoke its executable, request credentials, use its API, or provide an environment variable for it.

For private and fully local documents, use deterministic extraction or the existing optional loopback-only Ollama adapter instead.
