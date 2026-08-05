# Reconciliation specification

Each execution creates an immutable `reconciliation_runs` record containing the deterministic input hash and engine version. Existing open findings become `superseded`; resolved and superseded findings remain reviewable history. Database triggers reject deletion of findings and modification/deletion of run records. Only findings from the current open set may be resolved.

The deterministic engine includes cap-rate arithmetic, area occupancy, OM versus rent-roll area, rent versus operations, NOI composition and historical/pro-forma comparison, lease dates/rent/area, tenant-name variations, unit counts, debt LTV/LTC, rate components, prices across OM/LOI/PSA, capex totals, missing/duplicate periods, duplicate/dropped rows and likely OCR punctuation corruption.

Rules use decimal arithmetic and stated tolerances. A finding records severity, explanation, compared values, source documents, pages, rule code, next step and resolution. Recency never resolves a conflict automatically; a reviewer records the controlling source.

Every scalar input is a canonical `FIELD_REGISTRY` name and therefore has an enforced type, unit, category scope and review boundary. Lease dates use normalized ISO calendar strings rather than numeric coercion. The structured list inputs (`operating_periods`, `row_identifiers`, `ocr_values` and `tenant_names`) remain separate governed semantic-model work; they cannot be created as untyped scalar assumptions. A service-level regression creates and approves 31 typed assumptions through the real append-only decision workflow and proves sixteen distinct persisted discrepancies, including source provenance.

