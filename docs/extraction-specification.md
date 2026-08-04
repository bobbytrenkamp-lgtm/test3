# Extraction specification

The pipeline is registry-oriented by document category. Current deterministic methods are filename/content phrase classification, conservative regex candidates, CSV cells, first-sheet XLSX XML values and simple selectable-PDF text operators. Images and scanned/complex PDFs remain `needs_review` when local OCR is unavailable.

Every candidate stores document/version/category, raw and normalized values, optional unit/currency/page/bounding box, exact source excerpt/hash, method/version, confidence, validation/review state, reviewer fields, comments and supersession/final-approval links.

XLSX formulas, macros, external links and embedded scripts are never evaluated. No benchmark or accuracy claim is made. Tesseract may later be an optional local adapter after executable discovery and test coverage.

