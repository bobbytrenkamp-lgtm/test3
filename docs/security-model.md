# Security and privacy model

## Assets and trust boundaries

Confidential documents, approved assumptions, identities and audit history are sensitive. Uploaded bytes and all text inside them are untrusted. The browser, local service, filesystem and optional local executables are separate boundaries.

## Threats and controls

| Threat | Current control | Remaining work |
|---|---|---|
| Cross-organization access | Organization predicate on service reads/writes | Full adversarial route suite |
| Prompt injection | Document instructions treated only as content; no model by default | Structured local-model sandbox |
| Malicious PDF | Never executed server-side; inline browser viewer, nosniff/CSP | Add local malware adapter; browser parser risk remains |
| Formulas/macros/links | XLSX XML values only; no evaluation | Formula-presence warnings |
| Oversized files/zip bombs | Request/file limits; limited ZIP parsing | Compressed/uncompressed ratio and XML node caps |
| Path traversal/overwrite | basename sanitization, UUID storage, resolved-parent check | Platform fuzzing |
| Stored XSS | UI escaping and CSP | Automated browser payload suite |
| SQL injection | Parameterized SQLite statements | Static query review |
| Session theft | Loopback-only development identity | Hardened password/session/CSRF required before networking |
| External transmission | No telemetry, hosted API or remote model; local endpoint validation | Egress-deny deployment guide |
| Sensitive logging | Metadata-only request log; no content/key logging | Redaction audit |
| Backup/deletion | Uploads local and ignored | Encrypted backup, restore/deletion workflow |
| Audit tampering | Previous-event hash chain | External signed anchor not present |

Malware status is explicitly `not_available`; the application never claims a scan occurred.

