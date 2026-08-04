# Security and privacy model

## Assets and trust boundaries

Confidential documents, approved assumptions, identities and audit history are sensitive. Uploaded bytes and all text inside them are untrusted. The browser, local service, filesystem and optional local executables are separate boundaries.

## Threats and controls

| Threat | Current control | Remaining work |
|---|---|---|
| Cross-organization access | Organization predicate plus enforced role matrix | Expand adversarial route suite |
| Prompt injection | Document instructions treated only as content; no model by default | Structured local-model sandbox |
| Malicious PDF | Never executed server-side; inline browser viewer, nosniff/CSP | Add local malware adapter; browser parser risk remains |
| Formulas/macros/links | XLSX XML values only; no evaluation | Formula-presence warnings |
| Oversized files/zip bombs | Request/file, ZIP expansion/ratio/entry, XLSX row/cell caps | Streaming XML parser |
| Path traversal/overwrite | basename sanitization, UUID storage, resolved-parent check | Platform fuzzing |
| Stored XSS | UI escaping and CSP | Automated browser payload suite |
| SQL injection | Parameterized SQLite statements | Static query review |
| Session theft/CSRF | PBKDF2 passwords, uniform-cost unknown-account checks, per-account and per-address sign-in lockouts, random opaque sessions stored as hashes, HttpOnly/SameSite cookies, per-session CSRF token and explicit server-side sign-out | TLS and institutional identity bootstrap remain required before any network exposure; server refuses non-loopback binding |

Protected JSON, static and document responses carry a restrictive same-origin CSP, anti-framing, no-sniff, no-referrer and browser-permission-denial headers. JSON bodies are capped at 1 MiB and uploads are rejected from declared length before allocation when over the configured limit. Original filenames in `Content-Disposition` are UTF-8 percent encoded. `TEST3_SECURE_COOKIE=1` is available only for an operator who has explicitly placed the loopback service behind local TLS; direct HTTP operation must retain `0`.
| External transmission | No telemetry, hosted API or remote model; local endpoint validation | Egress-deny deployment guide |
| Sensitive logging | Metadata-only request log; no content/key logging | Redaction audit |
| Backup/deletion | Manifested local backup and temporary restore drill | Encryption and controlled deletion workflow |
| Audit/approval tampering | Serialized audit and append-only review-decision hash chains with independent verifiers and immutable-decision triggers | External signed anchor not present |

Malware status is explicitly `not_available`; the application never claims a scan occurred.

