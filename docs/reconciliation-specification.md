# Reconciliation specification

Each execution creates an immutable `reconciliation_runs` record containing the deterministic input hash and engine version. Existing open findings become `superseded`; resolved and superseded findings remain reviewable history. Database triggers reject deletion of findings and modification/deletion of run records. Only findings from the current open set may be resolved.

The deterministic engine includes cap-rate arithmetic, area occupancy, OM versus rent-roll area, rent versus operations, NOI composition and historical/pro-forma comparison, lease dates/rent/area, tenant-name variations, unit counts, debt LTV/LTC, rate components, prices across OM/LOI/PSA, capex totals, missing/duplicate periods, duplicate/dropped rows and likely OCR punctuation corruption.

Rules use decimal arithmetic and stated tolerances. A finding records severity, explanation, compared values, source documents, pages, rule code, next step and resolution. Recency never resolves a conflict automatically; a reviewer records the controlling source.

