# Assumption intelligence architecture decision

Status: accepted for the first market-rent-growth slice. Date: 2026-08-05.

## Product boundary

Test1 remains the read-only source of geographic and economic observations. Test3 imports immutable local snapshots, normalizes evidence, produces candidate-only recommendations and governs analyst decisions. Test2 remains the calculation engine and receives only analyst-approved controlling assumptions. Test3 does not run valuation, lease cash-flow, debt, waterfall or scenario calculations.

## Data flow

1. An analyst imports a local Test1 economic directory or a documented CSV market panel.
2. Test3 preserves the original file hashes and immutable snapshot metadata, then writes normalized observations without converting missing values to zero.
3. A deterministic rent-growth service selects evidence through an explicit geography/property fallback hierarchy and calculates descriptive statistics.
4. A validated real-data model artifact may contribute a model estimate. A fictional artifact is visible for demonstration but is prohibited from controlling a real recommendation.
5. Every run freezes its exact feature vector, evidence IDs, scores, hashes, rationale and limitations.
6. The analyst uses the existing manual-assumption and append-only review-decision path to approve low/base/high/custom or reject. A separate immutable context row links that decision to the run and controlling source; it does not bypass approval.
7. Test2 export maps an approved market-rent-growth assumption to a growth curve only when the current schema supports it. Evidence, model recommendations, decisions and snapshot metadata remain separately labeled in `assumptionIntelligence`.

## Immutability and migration

SQLite changes are additive. Snapshot, observation, model-artifact, run, evidence and decision-context rows are protected against update/delete. Schema version, backup manifest/table requirements, restore verification and operational integrity are advanced together. Imported source files remain local and ignored by Git; committed fixtures are explicitly fictional.

## Statistical boundary

The initial offline R pipeline is transparent and base-R-first. It creates chronological lags and a time-based validation split. The normal application never executes R or arbitrary scripts; it consumes only bounded JSON artifacts whose content and source hashes validate. Statistical significance is diagnostic, not an underwriting conclusion. A fictional model is labeled `FICTIONAL SYNTHETIC MODEL — NOT FOR REAL UNDERWRITING` and cannot produce a controlling recommendation.

## Security and cost

There are no runtime network requests, hosted services, telemetry, paid APIs or new runtime packages. Upload parsers treat data as inert values, reject duplicate columns and formulas, enforce size/row limits, and retain row hashes and validation errors. Browser routes accept no executable paths or commands.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.
