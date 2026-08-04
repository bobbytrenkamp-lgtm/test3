from __future__ import annotations

import argparse
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .backup import create_backup, verify_backup
from .service import Service


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile)))
    return round(ordered[index] * 1000, 2)


def run_probe(operations: int = 100, workers: int = 8) -> dict:
    if not 1 <= operations <= 1000 or not 1 <= workers <= 32:
        raise ValueError("operations must be 1..1000 and workers must be 1..32")
    started = time.perf_counter()
    latencies: list[float] = []
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="test3-load-probe-") as temporary:
        service = Service(Path(temporary), max_upload_bytes=100_000)
        user = service.seed()

        def operation(index: int) -> float:
            operation_started = time.perf_counter()
            deal = service.create_deal(user["organization_id"], user["id"], {"name": f"Concurrent Fictional Deal {index}", "property_type": "office"})
            content = f"Property Name,Asking Price\nConcurrent Fictional Deal {index},{1000000 + index}\n".encode()
            service.upload(user["organization_id"], user["id"], deal["id"], f"fictional-{index}.csv", content)
            return time.perf_counter() - operation_started

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(operation, index) for index in range(operations)]
            for future in as_completed(futures):
                try:
                    latencies.append(future.result())
                except Exception as error:
                    failures.append(type(error).__name__)
        integrity = service.operational_integrity(user["organization_id"])
        with service.db.connect() as connection:
            counts = {
                "deals": connection.execute("SELECT COUNT(*) FROM deals WHERE organization_id=?", (user["organization_id"],)).fetchone()[0],
                "documents": connection.execute("SELECT COUNT(*) FROM documents WHERE organization_id=?", (user["organization_id"],)).fetchone()[0],
                "auditEvents": connection.execute("SELECT COUNT(*) FROM audit_events WHERE organization_id=?", (user["organization_id"],)).fetchone()[0],
            }
        backup_started = time.perf_counter()
        archive = Path(temporary) / "resilience-drill.zip"
        create_backup(Path(temporary), archive)
        backup_seconds = time.perf_counter() - backup_started
        restore_started = time.perf_counter()
        restore = verify_backup(archive)
        restore_seconds = time.perf_counter() - restore_started
    elapsed = time.perf_counter() - started
    expected_counts = {"deals": operations + 1, "documents": operations, "auditEvents": 1 + operations * 2}
    counts_match = counts == expected_counts
    restore_passed = restore["valid"] and restore["restoredOperationalIntegrity"] and restore["counts"]["documents"] == operations
    ok = not failures and len(latencies) == operations and integrity["ok"] and counts_match and restore_passed
    return {
        "format": "test3-local-load-probe/1.0",
        "ok": ok,
        "localOnly": True,
        "networkRequests": 0,
        "operations": operations,
        "workers": workers,
        "completed": len(latencies),
        "failures": failures,
        "elapsedSeconds": round(elapsed, 3),
        "throughputOperationsPerSecond": round(operations / elapsed, 2),
        "latencyMs": {"p50": _percentile(latencies, 0.50), "p95": _percentile(latencies, 0.95), "p99": _percentile(latencies, 0.99), "max": round(max(latencies) * 1000, 2)},
        "counts": counts,
        "expectedCounts": expected_counts,
        "integrityPassed": integrity["ok"],
        "backupSeconds": round(backup_seconds, 3),
        "restoreDrillSeconds": round(restore_seconds, 3),
        "restoreDrillPassed": restore_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a temporary, fictional, local-only concurrent test3 workload")
    parser.add_argument("--operations", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    try:
        report = run_probe(args.operations, args.workers)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
