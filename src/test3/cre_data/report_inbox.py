from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pypdfium2 as pdfium


ALLOWED_SUFFIXES = frozenset({".pdf", ".csv", ".xlsx", ".parquet"})
MAX_REPORT_BYTES = 128 * 1024 * 1024
SOURCE_PATTERNS = {"berkadia": "Berkadia", "cbre": "CBRE", "colliers": "Colliers",
                   "jll": "JLL", "cushman": "Cushman & Wakefield", "newmark": "Newmark"}
PROPERTY_TYPES = ("multifamily", "industrial", "office", "retail")


def _quarter(name: str) -> str | None:
    patterns = (r"(?i)\b(?:q([1-4])[-_ ]?((?:19|20)\d{2}))\b", r"(?i)\b((?:19|20)\d{2})[-_ ]?q([1-4])\b")
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, name)
        if match:
            quarter, year = match.groups() if index == 0 else (match.group(2), match.group(1))
            return f"{year}-Q{quarter}"
    return None


def _page_count(path: Path) -> int | None:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        document = pdfium.PdfDocument(str(path))
        count = len(document); document.close()
        return count
    except Exception:
        return None


def _infer(path: Path) -> dict:
    lower = path.stem.lower().replace("_", " ").replace("-", " ")
    source = next((label for token, label in SOURCE_PATTERNS.items() if token in lower), None)
    property_type = next((item for item in PROPERTY_TYPES if item.replace("_", " ") in lower), None)
    period = _quarter(path.stem)
    noise = set(SOURCE_PATTERNS) | set(PROPERTY_TYPES) | {"market", "report", "research", "quarterly", "q1", "q2", "q3", "q4"}
    market_tokens = [token for token in re.split(r"[^a-zA-Z]+", path.stem) if token.lower() not in noise and
                     not re.fullmatch(r"(?:19|20)\d{2}", token)]
    market = " ".join(market_tokens).strip() or None
    confidence = sum(value is not None for value in (source, property_type, period, market)) / 4
    return {"source": source, "likely_market": market, "likely_period": period,
            "likely_property_type": property_type, "inference_confidence": confidence,
            "analyst_review_required": True}


def discover_reports(inbox: str | Path) -> dict:
    root = Path(inbox).resolve()
    root.mkdir(parents=True, exist_ok=True)
    documents = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        size = path.stat().st_size
        if size > MAX_REPORT_BYTES:
            documents.append({"filename": path.name, "bytes": size, "extraction_status": "rejected_too_large"})
            continue
        content = path.read_bytes()
        documents.append({"filename": path.name, "sha256": hashlib.sha256(content).hexdigest(), "bytes": size,
                          "document_type": path.suffix.lower().lstrip("."), "page_count": _page_count(path),
                          "extraction_status": "discovered_candidate", **_infer(path)})
    groups = {}
    for item in documents:
        if item.get("extraction_status") != "discovered_candidate":
            continue
        key = (item.get("source") or "unknown", item.get("likely_market") or "unknown",
               item.get("likely_property_type") or "unknown")
        groups.setdefault(key, []).append(item)
    series = []
    for key, items in sorted(groups.items()):
        periods = sorted({item["likely_period"] for item in items if item.get("likely_period")})
        digest = hashlib.sha256("|".join(key).encode()).hexdigest()[:16]
        missing = []
        if periods:
            values = [int(p[:4]) * 4 + int(p[-1]) - 1 for p in periods]
            present = set(values)
            for value in range(min(values), max(values) + 1):
                if value not in present:
                    missing.append(f"{value // 4}-Q{value % 4 + 1}")
        series.append({"source_series_id": f"cre-report-{digest}", "source": key[0], "market": key[1],
                       "property_type": key[2], "frequency": "quarterly" if periods else "unknown",
                       "documents": [item["sha256"] for item in items], "periods_present": periods,
                       "periods_missing": missing, "methodology_versions": [], "analyst_review_required": True})
    return {"schema_version": "test3-cre-report-discovery/1.0.0", "scanned_at": datetime.now(timezone.utc).isoformat(),
            "inbox": str(root), "documents": documents, "series": series,
            "notice": "Discovery is metadata-only. No observation is approved or model eligible."}


def save_report_discovery(inbox: str | Path) -> dict:
    report = discover_reports(inbox)
    stable = {key: value for key, value in report.items() if key not in {"scanned_at", "inbox"}}
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    destination = Path(inbox).resolve().parent / "manifests" / f"{digest}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text(json.dumps({**report, "manifest_sha256": digest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**report, "manifest_sha256": digest, "manifest_path": str(destination)}
