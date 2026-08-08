# Extraction specification

The pipeline is governed by the code-owned `FIELD_REGISTRY`. Every registered field has a stable machine name, analyst label, value type, one or more deterministic patterns, applicable document categories, optional unit/currency, confidence policy and optional reconciliation/export use. Registry names are unique and tested. Category scoping prevents, for example, debt terms from being extracted from a lease merely because similar words appear there. Unknown documents remain broad-scan candidates and always require review.

The current registry covers 57 property, transaction, operating, lease, debt, capital and underwriting fields. It includes every scalar consumed by reconciliation; a contract regression rejects rule inputs that are absent from the registry. It is intentionally conservative: adding a field requires a registry entry, fictional positive/category-negative tests and documentation of downstream meaning. A registry entry enables candidate detection, never approval.

Current deterministic methods are filename/content phrase classification, registry patterns, CSV cells, bounded all-sheet openpyxl values, PDFium selectable text/coordinates, Pillow image validation and optional local Tesseract image/scanned-PDF OCR. XLSX accepts at most 64 worksheets and 2,000,000 cells across the workbook. When Tesseract is unavailable, scanned sources remain honestly `needs_review`.

Every candidate stores document/version/category, raw and normalized values, registry-derived unit/currency, optional page/bounding box, exact source excerpt/hash, method/version, confidence, validation/review state, reviewer fields, comments and supersession/final-approval links. Percent signs are normalized to decimal fractions, basis points to fractions, integers reject fractional input, dates require an understood calendar representation, and failed normalization lowers confidence and stays `needs_review`.

XLSX formulas, macros, external links and embedded scripts are never evaluated. Macro-enabled workbooks are rejected by independent archive inspection. PDF/image bounding boxes use normalized top-left coordinates for rendered-page highlighting. Tabular rows retain source-specific `row.<row>.<header>` names so repeated tenants and periods are never collapsed into a single scalar. No benchmark or accuracy claim is made.

CSV/XLSX source review uses an authenticated, bounded logical table view: at most 500 rows, 200 columns per row and 20,000 visible cells. The stored worksheet/cell coordinate selects and outlines the exact escaped cell. The endpoint reports worksheet title/count, truncation and formula non-execution; it does not claim pixel-identical formatting.

Recognized category-specific table headers also create immutable semantic entities without replacing cell evidence. Rent-roll, operating-account/period, lease-schedule and debt-term records retain canonical data hashes, source rows and constituent cell IDs. Approval is inherited only after every mapped source cell is approved; details are in `docs/semantic-entity-contract.md`.

