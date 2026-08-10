from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from .metrics import get_cre_metric
from test3.warehouse.storage import WarehousePaths


@dataclass(frozen=True)
class ReportMappingProfile:
    profile_id: str
    version: str
    expected_labels: tuple[str, ...]
    mappings: dict[str, tuple[str, str, str]]  # metric, unit, methodology

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", self.profile_id):
            raise ValueError("invalid report profile id")
        if set(self.mappings) - set(self.expected_labels):
            raise ValueError("profile mapping references an unexpected label")


def save_report_profile(paths: WarehousePaths, profile: ReportMappingProfile) -> Path:
    profile.validate(); paths.initialize()
    payload = asdict(profile); payload["expected_labels"] = list(profile.expected_labels)
    payload["mappings"] = {key: list(value) for key, value in profile.mappings.items()}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    destination = paths.contained(Path("manifests") / "cre_report_profiles" / profile.profile_id /
                                  f"{profile.version}-{digest[:12]}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text(json.dumps({**payload, "sha256": digest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def load_report_profile(path: str | Path) -> ReportMappingProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8")); stored = payload.pop("sha256", None)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != stored:
        raise ValueError("report profile integrity failure")
    return ReportMappingProfile(payload["profile_id"], payload["version"], tuple(payload["expected_labels"]),
                                {key: tuple(value) for key, value in payload["mappings"].items()})


def _number(value: object, unit: str) -> str:
    text = str(value).strip().replace(",", "").replace("$", "")
    percentage = text.endswith("%")
    if percentage:
        text = text[:-1].strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"report value is not numeric: {value!r}") from exc
    if unit == "decimal_fraction" and percentage:
        number /= 100
    return format(number, "f")


def extract_table_candidates(*, rows: list[dict], profile: ReportMappingProfile, context: dict,
                             document_sha256: str, page: int, table: str,
                             long_label_column: str | None = None, long_value_column: str | None = None) -> dict:
    """Map already-extracted wide or long tables to evidence-bound, unapproved candidates."""
    profile.validate()
    if not rows:
        raise ValueError("report table is empty")
    headers = tuple(str(key) for key in rows[0])
    if long_label_column:
        if not long_value_column or long_label_column not in headers or long_value_column not in headers:
            raise ValueError("long table label/value columns are missing")
        observed_labels = {str(row.get(long_label_column, "")).strip() for row in rows}
    else:
        observed_labels = set(headers)
    expected, observed = set(profile.expected_labels), set(observed_labels)
    drift = {"missing_labels": sorted(expected - observed), "unexpected_labels": sorted(observed - expected),
             "compatible": expected == observed}
    if not drift["compatible"]:
        return {"schema_drift": drift, "candidates": [], "status": "review_required"}
    candidates = []
    for row_index, row in enumerate(rows, 1):
        pairs = [(str(row[long_label_column]).strip(), row[long_value_column], long_value_column)] if long_label_column else [
            (label, row.get(label), label) for label in profile.expected_labels]
        for label, original, column in pairs:
            if original in (None, "") or label not in profile.mappings:
                continue
            metric, unit, methodology = profile.mappings[label]
            get_cre_metric(metric, context["property_type"])
            observation = {**context, "metric": metric, "unit": unit, "methodology": methodology,
                           "value": _number(original, unit), "verification_status": "unverified",
                           "notes": f"Candidate extracted with report profile {profile.profile_id}/{profile.version}."}
            candidates.append({"status": "candidate", "analyst_approved": False, "observation": observation,
                               "evidence": {"document_sha256": document_sha256, "page": page, "table": table,
                                            "row": row_index, "column": column, "original_label": label,
                                            "original_value": str(original)}})
    return {"schema_drift": drift, "candidates": candidates, "status": "candidate_only"}
