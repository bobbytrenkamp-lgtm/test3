# Institutional model hardening

This implementation deliberately fails closed at five boundaries that can otherwise make CRE research look more reliable than it is.

## Forecast-origin availability

Target-panel construction preserves delayed releases instead of discarding their lineage. Real-data walk-forward and geographic-holdout validation then require every predictor to have a recorded availability date no later than the applicable forecast origin. Excluded rows are counted under `feature_not_available_at_forecast_origin`. A feature published after a quarter begins cannot be used to predict that quarter.

## Exact model-specification readiness

Target counts alone are not model readiness. Readiness is recalculated against the immutable target-feature panel for each governed specification. It reports complete cases, market and period coverage, feature missingness, availability exclusions, and longitudinal depth. A specification is ready only when its exact leakage-safe complete-case sample passes its own thresholds.

## Governed source harmonization

MAA effective-rent growth and AVB revenue-per-occupied-home growth have different meanings. Cross-source research may be calculated for diagnosis, but its promotion gate fails unless a hash-valid, analyst-approved target-harmonization artifact identifies each source metric and methodology version. No source label is treated as proof of semantic comparability.

## AVB geography hierarchy

AVB schedules can display both regional totals and component markets. Known overlapping totals are retained as candidate evidence with `source_geography_role=overlapping_region_rollup`, but cannot enter a model panel beside their components. Source-defined geographies remain portfolio markets, not CBSAs.

## Market feature aggregation

The feature registry now defines market aggregation separately from CBSA aggregation:

- growth and local rate features use the approved portfolio county weights;
- national macro features are broadcast only after county values agree;
- additive level and other unsupported features remain null rather than being averaged with an economically invalid formula.

Missing county values are never zero-filled and surviving counties are never reweighted.

## Release-date evidence

AVB observations retain the SEC accession and release-date evidence status. When an official exhibit contains an embedded release date, a caller-supplied date must match. Table-only evidence remains `manifest_asserted_review_required`; this limitation is visible and requires review.

The locally retained Q2 2021 AVB filing is valid SEC evidence, but its relevant historical schedule is image-based and does not satisfy the governed table parser. It remains excluded rather than being OCR-estimated or forced through the newer schema.

These controls do not create analyst approval. MAA and AVB candidates, market definitions, and any cross-source semantic bridge remain subject to explicit human attestation.
