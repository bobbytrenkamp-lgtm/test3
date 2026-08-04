# Architecture

```text
Browser (static HTML/CSS/JS)
        │ loopback HTTP only
Python standard-library service
  ├─ upload verification + immutable storage
  ├─ deterministic classification/extraction
  ├─ review + reconciliation services
  ├─ test1/test2/memo adapters
  └─ SQLite metadata + hash-chained audit
```

The runtime binds only to `127.0.0.1` by default. Exact-pinned permissively licensed packages perform PDF rendering/text extraction, image validation and XLSX parsing entirely locally. Original bytes are stored under generated UUID names and never interpreted as code. Spreadsheet formulas are retained for review but never executed. Browser text is escaped and the server applies a restrictive content-security policy.

Production/network use is intentionally blocked pending hardened authentication, CSRF controls and a security review. Static GitHub Pages may host documentation/UI demonstrations, but cannot provide private persistence or document processing; the full application remains local.

