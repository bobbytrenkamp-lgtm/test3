# Dependency and license audit

Audit date: 2026-08-04.

| Component | Version/source | License | Runtime required | Approved | Notes |
|---|---|---|---|---|---|
| test3 source | 0.1.0 | MIT | Yes | Yes | Repository license |
| Python | 3.11+ | PSF-2.0 | Yes | Yes | Local interpreter |
| SQLite | Python standard library | Public domain | Yes | Yes | Local only |
| DuckDB | 1.5.5 | MIT | Yes | Yes | Embedded local analytical engine and Parquet reader/writer; no service or transitive Python dependency |
| actions/checkout | v4 | MIT | CI only | Yes | GitHub-maintained public action |
| actions/setup-python | v5 | MIT | CI only | Yes | GitHub-maintained public action |
| pypdfium2/PDFium | 5.12.1 | Apache-2.0 OR BSD-3-Clause; bundled PDFium and notices | Yes | Yes | Local PDF text/rendering; wheel notices retained by installation |
| Pillow | 12.3.0 | MIT-CMU | Yes | Yes | Local image decode/validation and OCR rendering |
| openpyxl | 3.1.5 | MIT | Yes | Yes | Local XLSX parser; formula execution disabled |
| et_xmlfile | 2.0.0 | MIT | Yes (openpyxl transitive, explicitly pinned) | Yes | Local streaming XML writer dependency |
| setuptools | 83.0.0 | MIT | Build only | Yes | Exact-pinned local package builder |
| defusedxml | 0.7.1 | PSF-2.0 | Yes | Yes | XML entity/expansion defense used by openpyxl |
| Ollama | Optional/not bundled | MIT | No | Future local option | Loopback only |
| Tesseract | Optional/not bundled | Apache-2.0 | No | Future local option | Local OCR only |

All dependencies are exact-pinned and local; none needs an account, key, payment method, network service, usage allowance or billing connection. `license_guard.py` compares the manifest and CI actions to an exact allowlist. Vendored source is not permitted without a separate license entry and notice review.

