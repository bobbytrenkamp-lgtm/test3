from __future__ import annotations

import json
from pathlib import Path

from test3.warehouse.storage import WarehousePaths


VERIFICATION_SCHEMA = "test3-cre-verification/1.0.0"
_HEADER_BYTES = 64 * 1024


def _top_level_string_values(prefix: str, fields: set[str]) -> dict[str, str]:
    """Extract complete top-level JSON string fields from a bounded prefix."""
    decoder = json.JSONDecoder()
    values: dict[str, str] = {}
    depth = 0
    index = 0
    while index < len(prefix) and values.keys() != fields:
        character = prefix[index]
        if character == '"':
            try:
                token, end = decoder.raw_decode(prefix, index)
            except json.JSONDecodeError:
                break
            if depth == 1 and isinstance(token, str):
                cursor = end
                while cursor < len(prefix) and prefix[cursor].isspace():
                    cursor += 1
                if cursor < len(prefix) and prefix[cursor] == ":":
                    cursor += 1
                    while cursor < len(prefix) and prefix[cursor].isspace():
                        cursor += 1
                    if token in fields and cursor < len(prefix) and prefix[cursor] == '"':
                        try:
                            value, value_end = decoder.raw_decode(prefix, cursor)
                        except json.JSONDecodeError:
                            break
                        if isinstance(value, str) and value:
                            values[token] = value
                        index = value_end
                        continue
            index = end
            continue
        if character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
        index += 1
    return values


def _load_report(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable CRE verification report: {path}") from exc
    schema = payload.get("schema_version")
    if schema not in (None, VERIFICATION_SCHEMA):
        raise ValueError(f"unsupported CRE verification report: {path}")
    return {**payload, "_verification_path": str(path)}


def _report_header(path: Path) -> tuple[str, str] | None:
    """Read only enough metadata to select the active immutable version.

    Verification reports can contain millions of bytes of observation evidence.
    The governed writers place ``dataset_id`` and ``created_at`` before those
    arrays. Older, differently ordered reports fall back to a complete parse so
    compatibility is preserved.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(_HEADER_BYTES)
    except OSError as exc:
        raise ValueError(f"unreadable CRE verification report: {path}") from exc
    values = _top_level_string_values(prefix, {"dataset_id", "created_at"})
    if set(values) != {"dataset_id", "created_at"}:
        return None
    return values["dataset_id"], values["created_at"]


def verification_reports(paths: WarehousePaths, *, active_only: bool = True) -> list[dict]:
    """Load governed CRE verification reports without double-counting vintages.

    Immutable versions remain on disk for revision analysis. Analytical consumers
    use only the newest report for each dataset unless they explicitly request the
    full history.
    """
    root = paths.contained(Path("verification") / "cre")
    report_paths = list(sorted(root.glob("dataset=*/version=*/verification.json"))) if root.exists() else []
    if not active_only:
        return [_load_report(path) for path in report_paths]

    # Select active versions using bounded header reads, then deserialize only
    # the selected reports. This keeps status/readiness commands proportional to
    # active data rather than every retained historical vintage.
    latest: dict[str, tuple[tuple[str, str], Path]] = {}
    for path in report_paths:
        header = _report_header(path)
        if header is None:
            report = _load_report(path)
            dataset = report.get("dataset_id")
            if not dataset:
                raise ValueError(f"CRE verification report is missing dataset_id: {path}")
            created_at = str(report.get("created_at") or "")
        else:
            dataset, created_at = header
        rank = (created_at, str(path))
        current = latest.get(dataset)
        if current is None or rank > current[0]:
            latest[dataset] = (rank, path)
    return [_load_report(latest[key][1]) for key in sorted(latest)]
