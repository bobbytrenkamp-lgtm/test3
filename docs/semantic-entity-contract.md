# Semantic entity contract

Tabular ingestion derives four immutable entity families: `rent_roll_record`, `operating_account_period`, `lease_schedule_record` and `debt_term_record`. Header aliases are code-owned and category-specific. Unknown headers are retained as period values only for operating rows; no row is silently assigned a different meaning.

Every record stores organization/deal/document/version/category, entity type, one-based source row, canonical compact JSON, SHA-256, exact constituent extracted-value IDs, extractor version and creation time. Database triggers reject updates and deletes. Operational integrity re-hashes content and verifies that every constituent cell belongs to the same organization, deal and document.

Semantic approval is derived rather than independently editable. A record is `approved` only when all constituent cells are approved through the existing append-only review-decision chain; any rejected cell makes it rejected, and every other combination remains `needs_review`. This prevents a row-level shortcut around human cell review.

The initial deterministic header contract covers required rent-roll identity/area/dates/rent/options/status fields, operating account/classification/monthly/annual values, lease premises/rent/recovery/options/rights fields and debt lender/rate/leverage/fee/reserve/extension fields. Missing headers remain missing and are never replaced with zero.

The analyst semantic-row table shows canonical fields, source document/row and derived state. “Open source cell” navigates to the first constituent value in the exact PDF/image/table source viewer; reviewers continue to approve or reject the individual source cells rather than bypassing them at row level.
