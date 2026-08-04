# Local resilience evidence

Evidence date: 2026-08-04. Environment: Windows, Python 3.12.13, AMD64 Family 25 Model 80. These are bounded development-machine results, not a capacity promise for other hardware or document sizes.

## Workload

Command:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m test3.load_probe --operations 100 --workers 8
```

The harness creates a unique fictional deal and ingests/extracts one unique fictional CSV per operation. Each operation produces serialized hash-chained audit events. After all workers finish, the harness checks exact database counts, SQLite/schema/FK health, both integrity chains and every original file hash. It then creates backup format 3.0, extracts it into another temporary directory, opens it through current `Service`/schema code and repeats operational integrity checks. Source data, archive and restore are temporary and local; reported network requests are zero.

## Results

| Run | Completed / failures | Throughput ops/s | Latency p50 / p95 / p99 / max ms | Backup s | Restore + integrity s | Exact counts | Integrity |
|---|---:|---:|---:|---:|---:|---|---|
| 1 | 100 / 0 | 21.74 | 43.22 / 1048.61 / 3161.96 / 3396.76 | 0.130 | 0.424 | 101 deals, 100 documents, 201 audit events | Pass |
| 2 | 100 / 0 | 24.11 | 56.16 / 1315.76 / 1772.71 / 1858.39 | 0.128 | 0.467 | 101 deals, 100 documents, 201 audit events | Pass |

Acceptance for this bounded probe is correctness: every operation completes, exact counts match, no lock/integrity error occurs, restored table/document counts match and all readiness checks pass. Both runs passed.

## Limitations

This probe does not model large PDFs, OCR CPU cost, browser rendering, sustained multi-hour use, network users or hardware failure during a filesystem transaction. The server remains loopback-only and the project does not claim production readiness from these results alone. Operators must rerun the harness on target hardware after material schema/parser changes and choose workload/retention limits appropriate to their documents.
