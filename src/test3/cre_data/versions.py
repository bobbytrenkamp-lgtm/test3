from __future__ import annotations

import json
from pathlib import Path

from test3.warehouse.storage import WarehousePaths


VERIFICATION_SCHEMA = "test3-cre-verification/1.0.0"


def verification_reports(paths: WarehousePaths, *, active_only: bool = True) -> list[dict]:
    """Load governed CRE verification reports without double-counting vintages.

    Immutable versions remain on disk for revision analysis. Analytical consumers
    use only the newest report for each dataset unless they explicitly request the
    full history.
    """
    root = paths.contained(Path("verification") / "cre")
    reports: list[dict] = []
    for path in sorted(root.glob("dataset=*/version=*/verification.json")) if root.exists() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"unreadable CRE verification report: {path}") from exc
        schema = payload.get("schema_version")
        if schema not in (None, VERIFICATION_SCHEMA):
            raise ValueError(f"unsupported CRE verification report: {path}")
        payload = {**payload, "_verification_path": str(path)}
        reports.append(payload)
    if not active_only:
        return reports
    latest: dict[str, dict] = {}
    for report in reports:
        dataset = report.get("dataset_id")
        if not dataset:
            raise ValueError(f"CRE verification report is missing dataset_id: {report['_verification_path']}")
        rank = (str(report.get("created_at") or ""), str(report.get("source_version") or ""),
                report["_verification_path"])
        current = latest.get(dataset)
        if current is None:
            latest[dataset] = report
            continue
        current_rank = (str(current.get("created_at") or ""), str(current.get("source_version") or ""),
                        current["_verification_path"])
        if rank > current_rank:
            latest[dataset] = report
    return [latest[key] for key in sorted(latest)]
