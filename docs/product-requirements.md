# Product requirements

## Purpose

An analyst creates a deal, adds available diligence documents, reviews source-linked candidates, resolves deterministic inconsistencies and exports only approved facts into underwriting.

## Required principles

Traceability, deterministic validation, human approval, reconciliation, privacy, reproducibility, zero possible cost and optional integration with test1/test2.

## Release workflow

Create fictional deal → upload OM/rent roll/T-12 → classify → review exact source → approve/reject → run at least ten rules → resolve conflicts → export versioned package → generate draft summary → inspect audit history.

## States

Not processed, processing, extracted, needs review, conflicting, approved, rejected, superseded and failed. No low-confidence or unresolved candidate may appear approved.

## Explicit exclusions

No legal conclusions, investment advice, hosted AI, third-party document transfer, silent conflict resolution, missing-to-zero substitution or production-readiness claim.

