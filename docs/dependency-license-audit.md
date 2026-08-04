# Dependency and license audit

Audit date: 2026-08-04.

| Component | Version/source | License | Runtime required | Approved | Notes |
|---|---|---|---|---|---|
| test3 source | 0.1.0 | MIT | Yes | Yes | Repository license |
| Python | 3.11+ | PSF-2.0 | Yes | Yes | Local interpreter |
| SQLite | Python standard library | Public domain | Yes | Yes | Local only |
| actions/checkout | v4 | MIT | CI only | Yes | GitHub-maintained public action |
| actions/setup-python | v5 | MIT | CI only | Yes | GitHub-maintained public action |
| Ollama | Optional/not bundled | MIT | No | Future local option | Loopback only |
| Tesseract | Optional/not bundled | Apache-2.0 | No | Future local option | Local OCR only |

No third-party Python or JavaScript library is declared. `license_guard.py` fails when a package lock/requirements manifest appears without an explicit audit update. Vendored source is not permitted without a separate license entry and notice review.

