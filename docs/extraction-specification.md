# Extraction specification

The pipeline is registry-oriented by document category. Current deterministic methods are filename/content phrase classification, regex candidates, CSV cells, first-sheet openpyxl values, PDFium selectable text/coordinates, Pillow image validation and optional local Tesseract image/scanned-PDF OCR. When Tesseract is unavailable, scanned sources remain honestly `needs_review`.

Every candidate stores document/version/category, raw and normalized values, optional unit/currency/page/bounding box, exact source excerpt/hash, method/version, confidence, validation/review state, reviewer fields, comments and supersession/final-approval links.

XLSX formulas, macros, external links and embedded scripts are never evaluated. Macro-enabled workbooks are rejected by independent archive inspection. PDF/image bounding boxes use normalized top-left coordinates for rendered-page highlighting. No benchmark or accuracy claim is made.

