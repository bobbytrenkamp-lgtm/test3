from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


MAX_DATASET_BYTES = 16 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 40 * 1024 * 1024
MAX_ZONING_FILES = 100
DATASETS = {
    "metadata": ("platform_metadata.json", True),
    "policy": ("map_data.json", True),
    "politicalRisk": ("political_risk.json", False),
    "waterStress": ("water_stress.json", False),
    "taxIncentives": ("tax_incentives.json", False),
    "facilities": ("facilities_index.json", False),
    "stateRegulations": ("state_regulations.json", False),
}


class Test1SnapshotError(ValueError):
    __test__ = False
    pass


def _read_json(root: Path, filename: str) -> tuple[object, dict]:
    path = (root / filename).resolve()
    if root not in path.parents or not path.is_file():
        raise Test1SnapshotError(f"Required snapshot dataset is missing: {filename}")
    size = path.stat().st_size
    if size > MAX_DATASET_BYTES:
        raise Test1SnapshotError(f"Snapshot dataset exceeds the safety limit: {filename}")
    content = path.read_bytes()
    try:
        value = json.loads(content, object_pairs_hook=_unique_object)
    except Test1SnapshotError as error:
        raise Test1SnapshotError(f"{error} in {filename}") from error
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise Test1SnapshotError(f"Snapshot dataset is not valid JSON: {filename}") from error
    return value, {"sha256": hashlib.sha256(content).hexdigest(), "bytes": size}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise Test1SnapshotError(f"Snapshot JSON contains duplicate key: {key}")
        value[key] = item
    return value


def load_snapshot(data_dir: Path) -> dict:
    """Load an actual test1 static data directory without making network requests."""
    root = data_dir.resolve()
    if not root.is_dir():
        raise Test1SnapshotError("Configured test1 data directory does not exist")
    loaded, integrity = {}, {}
    total = 0
    for name, (filename, required) in DATASETS.items():
        if not (root / filename).is_file() and not required:
            continue
        value, file_integrity = _read_json(root, filename)
        loaded[name], integrity[filename] = value, file_integrity
        total += file_integrity["bytes"]
        if total > MAX_SNAPSHOT_BYTES:
            raise Test1SnapshotError("Configured test1 snapshot exceeds the total safety limit")

    zoning_dir = root / "zoning" / "normalized"
    if zoning_dir.is_dir():
        zoning_files = sorted(zoning_dir.glob("*.json"))
        if len(zoning_files) > MAX_ZONING_FILES:
            raise Test1SnapshotError("Configured test1 snapshot exceeds the zoning file-count safety limit")
        zoning = {}
        for path in zoning_files:
            value, file_integrity = _read_json(root, path.relative_to(root).as_posix())
            jurisdiction = value.get("jurisdiction") if isinstance(value, dict) else None
            fips = str(jurisdiction.get("county_fips") or "") if isinstance(jurisdiction, dict) else ""
            if not re.fullmatch(r"\d{5}", fips) or not isinstance(value.get("districts"), dict):
                raise Test1SnapshotError(f"Unsupported test1 zoning dataset shape: {path.name}")
            if fips in zoning:
                raise Test1SnapshotError(f"Duplicate test1 zoning jurisdiction for county FIPS: {fips}")
            zoning[fips] = value
            relative = path.relative_to(root).as_posix()
            integrity[relative] = file_integrity
            total += file_integrity["bytes"]
            if total > MAX_SNAPSHOT_BYTES:
                raise Test1SnapshotError("Configured test1 snapshot exceeds the total safety limit")
        if zoning:
            loaded["zoning"] = zoning

    metadata, policy = loaded["metadata"], loaded["policy"]
    if not isinstance(metadata, dict) or metadata.get("_schema") != "platform_metadata_v1":
        raise Test1SnapshotError("Unsupported test1 platform metadata schema")
    if not isinstance(policy, dict) or not isinstance(policy.get("counties"), dict):
        raise Test1SnapshotError("Unsupported test1 map data schema")
    _validate_optional_shapes(loaded)
    return {
        "schemaVersion": "test1-local-data-directory/1.1",
        "loadedAt": datetime.now(timezone.utc).isoformat(),
        "sourceGeneratedAt": policy.get("generated_at") or metadata.get("_generated_at"),
        "sourceLastUpdated": policy.get("source_last_updated"),
        "methodologyVersion": metadata.get("methodology_version"),
        "integrity": integrity,
        "datasets": loaded,
    }


def _validate_optional_shapes(loaded: dict) -> None:
    checks = {
        "politicalRisk": lambda value: isinstance(value, dict) and isinstance(value.get("scores"), list),
        "waterStress": lambda value: isinstance(value, dict) and isinstance(value.get("water_stress"), dict),
        "taxIncentives": lambda value: isinstance(value, dict) and isinstance(value.get("tax_incentives"), list),
        "facilities": lambda value: isinstance(value, list),
        "stateRegulations": lambda value: isinstance(value, dict) and isinstance(value.get("states"), dict),
    }
    for name, check in checks.items():
        if name in loaded and not check(loaded[name]):
            raise Test1SnapshotError(f"Unsupported test1 dataset shape: {DATASETS[name][0]}")


def enrich(inputs: dict, snapshot: dict | None) -> dict:
    base = {"inputs": inputs, "networkRequests": 0}
    if snapshot is None:
        return {**base, "status": "unavailable", "verified": False, "coverage": "missing", "message": "No local test1 data directory was configured; deal workflow remains available.", "results": {}}
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") not in {"test1-local-data-directory/1.0", "test1-local-data-directory/1.1"}:
        raise Test1SnapshotError("Unsupported normalized test1 snapshot version")
    fips = str(inputs.get("county_fips") or "")
    if not re.fullmatch(r"\d{5}", fips):
        return {**base, "status": "input_required", "verified": False, "coverage": "missing", "message": "A reviewer-approved five-digit county FIPS is required; test3 does not geocode or infer it.", "results": {}}

    datasets = snapshot["datasets"]
    policy = datasets["policy"]["counties"].get(fips)
    political = next((item for item in datasets.get("politicalRisk", {}).get("scores", []) if isinstance(item, dict) and str(item.get("fips")) == fips), None)
    water = datasets.get("waterStress", {}).get("water_stress", {}).get(fips)
    incentives = [item for item in datasets.get("taxIncentives", {}).get("tax_incentives", []) if isinstance(item, dict) and fips in [str(value) for value in item.get("fips_list", [])]]
    facilities = [item for item in datasets.get("facilities", []) if isinstance(item, dict) and str(item.get("county_fips")) == fips]
    state = datasets.get("stateRegulations", {}).get("states", {}).get(fips[:2])
    zoning = datasets.get("zoning", {}).get(fips)
    county_match = any((policy, political, water is not None, incentives, facilities, zoning))
    if not county_match and not state:
        return {**base, "status": "no_match", "verified": False, "coverage": "not_researched", "snapshot": _snapshot_metadata(snapshot), "results": {}}

    results = {
        "countyFips": fips,
        "policy": _policy_result(policy),
        "politicalRisk": _political_result(political),
        "waterStress": _water_result(water, datasets.get("waterStress")),
        "taxIncentives": [_incentive_result(item) for item in incentives],
        "facilities": _facility_result(facilities) if facilities else None,
        "stateRegulation": _state_result(state),
        "zoning": _zoning_result(zoning),
    }
    present = sum(value not in (None, [], {}) for value in results.values()) - 1
    freshness = _freshness(snapshot)
    return {
        **base, "status": "matched" if county_match else "state_only", "verified": bool(policy and policy.get("pipeline_verified") and freshness["status"] == "current"),
        "coverage": "state_only" if not county_match else "partial" if present < 5 else "multi_dataset",
        "snapshot": _snapshot_metadata(snapshot), "results": results,
        "limitations": datasets["metadata"].get("disclaimers", []),
    }


def _snapshot_metadata(snapshot: dict) -> dict:
    return {**{key: snapshot.get(key) for key in ("schemaVersion", "sourceGeneratedAt", "sourceLastUpdated", "methodologyVersion", "integrity")}, "freshness": _freshness(snapshot), "datasetDates": _dataset_dates(snapshot.get("datasets", {}))}


def _freshness(snapshot: dict) -> dict:
    raw = snapshot.get("sourceLastUpdated") or snapshot.get("sourceGeneratedAt")
    if not raw:
        return {"status": "unknown", "asOf": None, "ageDays": None, "currentThresholdDays": 90}
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc).date() - parsed.date()).days
    except ValueError:
        return {"status": "invalid", "asOf": raw, "ageDays": None, "currentThresholdDays": 90}
    status = "future_dated" if age < 0 else "current" if age <= 90 else "stale"
    return {"status": status, "asOf": raw, "ageDays": age, "currentThresholdDays": 90}


def _dataset_dates(datasets: dict) -> dict:
    political = datasets.get("politicalRisk", {})
    return {
        "policy": datasets.get("policy", {}).get("source_last_updated"),
        "politicalRisk": political.get("meta", {}).get("last_updated") if isinstance(political, dict) else None,
        "waterStress": datasets.get("waterStress", {}).get("_last_updated"),
        "taxIncentives": datasets.get("taxIncentives", {}).get("_last_updated"),
        "stateRegulations": datasets.get("stateRegulations", {}).get("_last_updated"),
    }


def _citations(sources: object) -> list[dict]:
    if not isinstance(sources, list):
        return []
    return [
        {"label": str(item.get("label", "Source")), "url": str(item["url"])}
        for item in sources if isinstance(item, dict) and re.match(r"^https?://", str(item.get("url", "")))
    ]


def _policy_result(record: object) -> dict | None:
    if not isinstance(record, dict):
        return None
    keep = ("name", "state", "level", "types", "title", "description", "effective_date", "status", "lifecycle_stage", "last_reviewed", "confidence", "confidence_score", "source_tier", "pipeline_verified")
    return {**{key: record.get(key) for key in keep}, "citations": _citations(record.get("sources"))}


def _political_result(record: object) -> dict | None:
    if not isinstance(record, dict):
        return None
    keep = ("risk_score", "score_label", "score_description", "evidence_summary", "confidence", "signal_count", "last_updated")
    citations = [{"label": str(item.get("label", "Evidence")), "url": str(item["source_url"])} for item in record.get("signals", []) if isinstance(item, dict) and re.match(r"^https?://", str(item.get("source_url", "")))]
    return {**{key: record.get(key) for key in keep}, "citations": citations}


def _water_result(score: object, dataset: object) -> dict | None:
    if score is None:
        return None
    labels = {0: "Low", 1: "Low-Medium", 2: "Medium-High", 3: "High", 4: "Extremely High"}
    source = dataset if isinstance(dataset, dict) else {}
    return {"score": score, "label": labels.get(score, "Unknown"), "approximate": True, "lastUpdated": source.get("_last_updated"), "disclaimer": source.get("_disclaimer"), "sourceNotes": source.get("_sources", [])}


def _incentive_result(record: dict) -> dict:
    keep = ("state", "program_name", "incentive_type", "min_investment_m", "notes")
    return {key: record.get(key) for key in keep}


def _facility_result(records: list[dict]) -> dict:
    capacity = sum((Decimal(str(item["capacity_mw_known"])) for item in records if isinstance(item.get("capacity_mw_known"), (int, float))), Decimal("0"))
    return {"count": len(records), "operationalCount": sum(item.get("operational_status") == "operational" for item in records), "knownCapacityMw": format(capacity, "f"), "examples": [{key: item.get(key) for key in ("facility_id", "name", "operator", "operational_status", "capacity_mw_known", "confidence_score")} for item in records[:10]]}


def _state_result(record: object) -> dict | None:
    if not isinstance(record, dict):
        return None
    keep = ("name", "abbr", "level", "status", "summary", "types", "last_reviewed")
    return {**{key: record.get(key) for key in keep}, "citations": _citations(record.get("sources"))}


def _zoning_result(record: object) -> dict | None:
    """Return bounded, review-oriented zoning context; never infer parcel zoning."""
    if not isinstance(record, dict) or not isinstance(record.get("jurisdiction"), dict):
        return None
    jurisdiction = record["jurisdiction"]
    jurisdiction_keep = (
        "jurisdiction_id", "jurisdiction_name", "jurisdiction_type", "state", "county",
        "county_fips", "controlling_authority", "source_license", "retrieval_method",
        "source_last_updated", "source_last_checked", "ordinance_effective_date",
        "ordinance_version", "data_coverage_status", "geometry_coverage_status",
        "dimensional_standard_coverage", "permitted_use_coverage", "overlay_coverage",
        "verification_status", "known_limitations", "pilot_notes", "notes",
    )
    official_sources = [
        {"label": label, "url": str(jurisdiction[key])}
        for key, label in (
            ("official_zoning_page_url", "Official zoning page"),
            ("official_zoning_map_url", "Official zoning map"),
            ("official_ordinance_url", "Official ordinance"),
        )
        if re.match(r"^https?://", str(jurisdiction.get(key, "")))
    ]
    districts = []
    for code, district in sorted(record.get("districts", {}).items())[:100]:
        if not isinstance(district, dict):
            continue
        standards = district.get("standards", {})
        districts.append({
            "districtCode": str(district.get("district_code") or code),
            "districtName": district.get("district_name"),
            "districtCategory": district.get("district_category"),
            "baseOrOverlay": district.get("base_or_overlay"),
            "confidenceLevel": district.get("confidence_level"),
            "lastVerified": district.get("last_verified"),
            "eligibilitySummary": district.get("dc_eligibility_summary"),
            "officialSourceUrl": str(district["official_source_url"]) if re.match(r"^https?://", str(district.get("official_source_url", ""))) else None,
            "standardCount": len(standards) if isinstance(standards, dict) else 0,
            "manualReviewRequired": any(isinstance(item, dict) and item.get("manual_review_required") is True for item in standards.values()) if isinstance(standards, dict) else False,
        })
    return {
        "jurisdiction": {key: jurisdiction.get(key) for key in jurisdiction_keep},
        "officialSources": official_sources,
        "districts": districts,
        "districtCount": len(record.get("districts", {})),
        "disclaimer": record.get("disclaimer"),
        "parcelDistrictKnown": False,
        "decisionUse": "preliminary_research_only",
    }
