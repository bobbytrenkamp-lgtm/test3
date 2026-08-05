# Tabular source-view contract

Authenticated `GET /api/documents/{documentId}/table` provides an organization-scoped, non-executing view of retained CSV or XLSX originals. It uses the same guarded parsers as extraction, returns the first XLSX worksheet or CSV rows, and states `formulasExecuted: false`.

The response is bounded to 500 rows, 200 columns per row and 20,000 visible cells; it reports source row count, visible cell count and truncation. Existing extracted-value bounding coordinates identify the zero-based visible row/column. The analyst review pane renders escaped cell text and visibly outlines the selected cell. It never inserts spreadsheet markup or evaluates formulas, macros, links or scripts.

This closes exact logical cell navigation for current CSV/XLSX extraction. It is not a pixel-identical spreadsheet renderer and makes no claim about formatting, hidden sheets or formula results.
