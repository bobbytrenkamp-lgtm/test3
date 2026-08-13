from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

import duckdb

from test3.features.manifests import verify_feature_manifest
from test3.features.panel import FeaturePanel
from test3.cre_data.geography import market_definitions
from test3.cre_data.metrics import CRE_METRICS
from test3.cre_data.versions import verification_reports
from test3.cre_data.verification import MODEL_BLOCKING_FINDING_CODES
from test3.warehouse.manifests import canonical_json, file_sha256
from test3.warehouse.storage import WarehousePaths
from test3.research.specifications import ModelSpecification


TARGET_PANEL_VERSION = "1.0.0"
SUPPORTED_FREQUENCIES = frozenset({"annual", "quarterly"})


@dataclass(frozen=True)
class ReadinessPolicy:
    minimum_markets: int = 5
    minimum_periods: int = 20
    minimum_observations: int = 100


@dataclass(frozen=True)
class TargetPanelResult:
    property_type: str
    target: str
    frequency: str
    status: str
    rows: int
    markets: int
    periods: int
    panel_path: Path
    manifest_path: Path
    manifest_hash: str
    target_dataset_hashes: tuple[str, ...]
    source_manifest_hashes: tuple[str, ...]
    feature_table_hashes: tuple[str, ...]
    exclusions: dict


def _eligible_rows_from_reports(reports: list[dict], property_type: str | None = None,
                                target: str | None = None) -> tuple[list[dict], Counter]:
    candidates, exclusions = [], Counter()
    for report in reports:
        dataset_hash = report.get("raw_snapshot", {}).get("sha256")
        manifest_hash = report.get("warehouse_manifest_hash")
        for row in report.get("observations", []):
            if property_type and row.get("property_type") != property_type:
                continue
            if target and row.get("metric") != target:
                continue
            if not row.get("model_eligible") or row.get("verification_status") != "analyst_verified":
                exclusions["not_model_eligible"] += 1
                continue
            if set(row.get("verification_findings", [])) & MODEL_BLOCKING_FINDING_CODES:
                exclusions["unresolved_quality_finding"] += 1
                continue
            if row.get("frequency") not in SUPPORTED_FREQUENCIES:
                exclusions["unsupported_frequency"] += 1
                continue
            available_at = row.get("release_date") or str(row.get("retrieved_at") or "")[:10]
            if not available_at:
                exclusions["missing_availability"] += 1
                continue
            candidates.append({**row, "target_dataset_hash": dataset_hash,
                               "target_source_manifest_hash": manifest_hash,
                               "target_available_at": available_at})
    grouped = defaultdict(list)
    for row in candidates:
        grouped[(row["geography_id"], row["period"], row["frequency"], row["property_type"], row["metric"])].append(row)
    longitudinal = defaultdict(list)
    for row in candidates:
        # A source_identifier is row-level evidence and normally changes every
        # quarter. It must not fragment longitudinal methodology validation.
        longitudinal[(row["geography_id"], row["frequency"], row["property_type"], row["metric"],
                      row["source_name"])].append(row)
    incompatible = {
        row["observation_id"] for rows in longitudinal.values()
        if len({row["methodology"] for row in rows}) > 1 for row in rows
    }
    eligible = []
    for rows in grouped.values():
        if any(row["observation_id"] in incompatible for row in rows):
            exclusions["longitudinal_methodology_change"] += len(rows)
        elif len(rows) != 1:
            exclusions["unresolved_multiple_sources"] += len(rows)
        else:
            eligible.append(rows[0])
    return eligible, exclusions


def _eligible_rows(paths: WarehousePaths, property_type: str | None = None, target: str | None = None) -> tuple[list[dict], Counter]:
    return _eligible_rows_from_reports(verification_reports(paths), property_type, target)


def _market_period_depth(rows: list[dict], minimum_periods: int) -> tuple[dict[str, int], int]:
    counts = {market: len({row["period"] for row in rows if row["geography_id"] == market})
              for market in {row["geography_id"] for row in rows}}
    return counts, sum(count >= minimum_periods for count in counts.values())


def target_readiness(paths: WarehousePaths, *, policy: ReadinessPolicy = ReadinessPolicy(),
                     frequency: str | None = None) -> list[dict]:
    if frequency is not None and frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError("target readiness currently supports annual or quarterly frequency")
    reports = verification_reports(paths)
    pairs = sorted({(property_type, metric.metric) for metric in CRE_METRICS.values()
                    for property_type in metric.property_types} |
                   {(row.get("property_type"), row.get("metric"))
                    for report in reports for row in report.get("observations", [])
                    if row.get("property_type") and row.get("metric")})
    output = []
    for property_type, target in pairs:
        all_rows = [row for report in reports for row in report.get("observations", [])
                    if row.get("property_type") == property_type and row.get("metric") == target
                    and (frequency is None or row.get("frequency") == frequency)]
        eligible, exclusions = _eligible_rows_from_reports(reports, property_type, target)
        if frequency is not None:
            eligible = [row for row in eligible if row.get("frequency") == frequency]
        markets = {row["geography_id"] for row in eligible}
        periods = {row["period"] for row in eligible}
        periods_by_market, longitudinal_markets = _market_period_depth(eligible, policy.minimum_periods)
        possible = len(markets) * len(periods)
        ready = (len(markets) >= policy.minimum_markets and len(periods) >= policy.minimum_periods
                 and longitudinal_markets >= policy.minimum_markets
                 and len(eligible) >= policy.minimum_observations)
        reasons = []
        if len(markets) < policy.minimum_markets:
            reasons.append(f"markets {len(markets)} below minimum {policy.minimum_markets}")
        if len(periods) < policy.minimum_periods:
            reasons.append(f"periods {len(periods)} below minimum {policy.minimum_periods}")
        if longitudinal_markets < policy.minimum_markets:
            reasons.append(f"markets meeting {policy.minimum_periods}-period depth {longitudinal_markets} "
                           f"below minimum {policy.minimum_markets}")
        if len(eligible) < policy.minimum_observations:
            reasons.append(f"eligible observations {len(eligible)} below minimum {policy.minimum_observations}")
        output.append({
            "property_type": property_type, "target": target, "observations": len(all_rows),
            "frequency": frequency or "all",
            "verified_observations": sum(row.get("verification_status") == "analyst_verified" for row in all_rows),
            "model_eligible_observations": len(eligible), "markets": len(markets), "periods": len(periods),
            "markets_meeting_period_minimum": longitudinal_markets,
            "periods_by_market": dict(sorted(periods_by_market.items())),
            "earliest": min(periods, default=None), "latest": max(periods, default=None),
            "missingness": (1.0 - len(eligible) / possible) if possible else None,
            "status": "ready" if ready else "not_ready", "reasons": reasons,
            "exclusions": dict(sorted(exclusions.items())), "policy": asdict(policy),
        })
    return output


def target_readiness_for_specification(paths: WarehousePaths, specification: ModelSpecification) -> dict:
    """Report target readiness against one model's authoritative promotion minimums."""
    policy = ReadinessPolicy(
        minimum_markets=specification.minimum_markets,
        minimum_periods=specification.minimum_periods,
        minimum_observations=specification.minimum_sample,
    )
    matches = [item for item in target_readiness(paths, policy=policy, frequency=specification.frequency)
               if item["property_type"] == specification.property_type and item["target"] == specification.target]
    if not matches:
        raise ValueError("model specification target is not registered")
    return {**matches[0], "model_specification": specification.name,
            "model_specification_version": specification.version}


def _panel_period(value: object, frequency: str) -> str:
    parsed = date.fromisoformat(str(value)[:10])
    return str(parsed.year) if frequency == "annual" else f"{parsed.year}-Q{(parsed.month - 1) // 3 + 1}"


def _feature_source(paths: WarehousePaths, frequency: str, geography: str) -> tuple[dict, Path, Path]:
    table = f"{geography}_{'year' if frequency == 'annual' else 'quarter'}"
    manifest = FeaturePanel(paths, table).latest()
    if manifest is None:
        raise ValueError(f"required feature table is not built: {table}")
    panel_path = paths.contained(Path("features") / table / f"version={manifest['feature_table_version']}" / "panel.parquet")
    verify_feature_manifest(panel_path.parent / "feature_manifest.json")
    lineage_path = panel_path.parent / "lineage.parquet"
    if not lineage_path.is_file():
        raise ValueError(f"required feature lineage is not built: {table}")
    return manifest, panel_path, lineage_path


def _period_end(period: str, frequency: str) -> date:
    if frequency == "annual":
        return date(int(period), 12, 31)
    match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if not match:
        raise ValueError(f"invalid quarterly target period: {period}")
    year, quarter = int(match.group(1)), int(match.group(2))
    month = quarter * 3
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return date.fromordinal(next_month.toordinal() - 1)


def _active_market_definition(definitions: list[dict], row: dict) -> tuple[dict | None, str | None]:
    """Select one source-backed market definition effective at the target period end."""
    period_end = _period_end(row["period"], row["frequency"])
    matches = [item for item in definitions
               if item["market_id"] == row["geography_id"]
               and item["property_type"] == row["property_type"]
               and item.get("review_status") == "analyst_approved"
               and date.fromisoformat(item["effective_from"]) <= period_end
               and (not item.get("effective_to") or period_end <= date.fromisoformat(item["effective_to"]))]
    if len(matches) > 1:
        return None, "ambiguous_market_definition"
    if not matches:
        return None, "missing_market_definition"
    return matches[0], None


def _weighted_county_features(definition: dict, period: str, feature_names: set[str],
                              feature_rows: dict) -> dict | None:
    component_rows = []
    for component in definition["counties"]:
        row = feature_rows.get(("county", str(component["county_fips"]), period))
        if row is None:
            return None
        component_rows.append((row, float(component["weight"])))
    output = {}
    for name in sorted(feature_names):
        values = [(row.get(name), weight) for row, weight in component_rows]
        # Missing county inputs remain missing; they are never zero-filled or
        # reweighted over the counties that happen to have data.
        output[name] = (sum(float(value) * weight for value, weight in values)
                        if values and all(value is not None for value, _ in values) else None)
        availability = [row.get(name + "__available_at") for row, _ in component_rows]
        output[name + "__available_at"] = (max(availability)
                                             if availability and all(value is not None for value in availability)
                                             else None)
        output[name + "__lineage_ids"] = sorted({identifier for row, _ in component_rows
                                                   for identifier in row.get(name + "__lineage_ids", [])})
        output[name + "__input_observation_ids"] = sorted({identifier for row, _ in component_rows
                                                            for identifier in row.get(name + "__input_observation_ids", [])})
    return output


def _manifest_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json({key: value for key, value in payload.items() if key != "manifest_hash"}).encode()).hexdigest()


def build_target_panel(paths: WarehousePaths, *, property_type: str, target: str,
                       frequency: str = "quarterly") -> TargetPanelResult:
    if frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError("target panels currently support annual or quarterly frequency")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", property_type or "") or not re.fullmatch(r"[a-z][a-z0-9_]*", target or ""):
        raise ValueError("property type and target must use governed identifiers")
    eligible, exclusions = _eligible_rows(paths, property_type, target)
    eligible = [row for row in eligible if row["frequency"] == frequency]
    if not eligible:
        raise ValueError("no model-eligible target observations match the requested panel")

    definitions = market_definitions(paths)
    row_definitions: dict[str, dict] = {}
    required = set()
    for row in eligible:
        if row.get("cbsa"):
            required.add("cbsa")
        elif row.get("county_fips") or row.get("geography_type") == "county":
            required.add("county")
        else:
            definition, problem = _active_market_definition(definitions, row)
            if problem:
                exclusions[problem] += 1
            else:
                required.add("county")
                row_definitions[row["observation_id"]] = definition
    sources = {geography: _feature_source(paths, frequency, geography) for geography in required}
    feature_rows, feature_names, feature_hashes, source_hashes = {}, set(), set(), set()
    for geography, (manifest, panel_path, lineage_path) in sources.items():
        feature_names.update(manifest["features"])
        feature_hashes.add(manifest["manifest_hash"])
        source_hashes.update(manifest.get("input_manifest_hashes", []))
        with duckdb.connect(":memory:") as connection:
            lineage_result = connection.execute("SELECT * FROM read_parquet(?)", [str(lineage_path)])
            lineage_names = [item[0] for item in lineage_result.description]
            lineage = {}
            for raw in lineage_result.fetchall():
                item = dict(zip(lineage_names, raw, strict=True))
                key = (str(item["geography_id"]), _panel_period(item["period_start"], frequency), item["feature_name"])
                lineage[key] = {
                    "lineage_ids": [item["lineage_id"]],
                    "input_observation_ids": json.loads(item.get("input_observation_ids_json") or "[]"),
                }
            result = connection.execute("SELECT * FROM read_parquet(?)", [str(panel_path)])
            names = [item[0] for item in result.description]
            for raw in result.fetchall():
                item = dict(zip(names, raw, strict=True))
                period = _panel_period(item["period_start"], frequency)
                for feature_name in manifest["features"]:
                    evidence = lineage.get((str(item["geography_id"]), period, feature_name), {})
                    item[feature_name + "__lineage_ids"] = evidence.get("lineage_ids", [])
                    item[feature_name + "__input_observation_ids"] = evidence.get("input_observation_ids", [])
                feature_rows[(geography, item["geography_id"], period)] = item

    joined = []
    for target_row in eligible:
        definition = None
        if target_row.get("cbsa"):
            geography, feature_id = "cbsa", target_row["cbsa"]
        elif target_row.get("county_fips") or target_row.get("geography_type") == "county":
            geography, feature_id = "county", target_row.get("county_fips") or target_row["geography_id"]
        elif target_row["observation_id"] in row_definitions:
            geography, feature_id = "market_weighted_counties", target_row["geography_id"]
            definition = row_definitions[target_row["observation_id"]]
        else:
            continue
        features = (_weighted_county_features(definition, target_row["period"], feature_names, feature_rows)
                    if definition else feature_rows.get((geography, feature_id, target_row["period"])))
        if features is None:
            exclusions["missing_feature_period"] += 1
            continue
        row = {
            "market_id": target_row["geography_id"], "feature_geography_type": geography,
            "feature_geography_id": feature_id, "period": target_row["period"],
            "property_type": property_type, target: float(target_row["value"]),
            f"{target}__available_at": target_row["target_available_at"],
            "target_observation_id": target_row["observation_id"],
            "target_dataset_hash": target_row["target_dataset_hash"],
            "target_source_manifest_hash": target_row["target_source_manifest_hash"],
            "market_definition_hash": definition["sha256"] if definition else None,
        }
        for name in sorted(feature_names):
            row[name] = features.get(name)
            available = features.get(name + "__available_at")
            row[name + "__available_at"] = available.isoformat() if isinstance(available, (date, datetime)) else available
            row[name + "__lineage_ids"] = json.dumps(features.get(name + "__lineage_ids", []), separators=(",", ":"))
            row[name + "__input_observation_ids"] = json.dumps(
                features.get(name + "__input_observation_ids", []), separators=(",", ":"))
        joined.append(row)
    if not joined:
        raise ValueError("no model-eligible target rows matched an immutable feature period")
    joined.sort(key=lambda row: (row["period"], row["market_id"]))

    target_hashes = tuple(sorted({row["target_dataset_hash"] for row in joined if row.get("target_dataset_hash")}))
    source_hashes.update(row["target_source_manifest_hash"] for row in joined if row.get("target_source_manifest_hash"))
    identity = {
        "schema_version": TARGET_PANEL_VERSION, "property_type": property_type, "target": target,
        "frequency": frequency, "target_dataset_hashes": list(target_hashes),
        "source_manifest_hashes": sorted(source_hashes), "feature_table_hashes": sorted(feature_hashes),
        "market_definition_hashes": sorted({row["market_definition_hash"] for row in joined
                                             if row.get("market_definition_hash")}),
        "rows_hash": hashlib.sha256(canonical_json(joined).encode()).hexdigest(),
    }
    version = hashlib.sha256(canonical_json(identity).encode()).hexdigest()[:24]
    final_dir = paths.contained(Path("research") / "target_panels" / property_type / target / f"version={version}")
    manifest_path, panel_path = final_dir / "target_panel_manifest.json", final_dir / "panel.parquet"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_hash") != _manifest_hash(manifest):
            raise ValueError("target-panel manifest integrity failure")
        if not panel_path.is_file() or file_sha256(panel_path) != manifest["panel_sha256"]:
            raise ValueError("target-panel Parquet integrity failure")
        return TargetPanelResult(property_type, target, frequency, "unchanged", manifest["rows"], manifest["markets"],
                                 manifest["periods"], panel_path, manifest_path, manifest["manifest_hash"], target_hashes,
                                 tuple(sorted(source_hashes)), tuple(sorted(feature_hashes)), manifest["exclusions"])
    staging = final_dir.parent / f".staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        columns = list(joined[0])
        definitions = []
        for name in columns:
            sample = next((row[name] for row in joined if row.get(name) is not None), None)
            definitions.append(f'"{name}" ' + ("DOUBLE" if isinstance(sample, float) else "VARCHAR"))
        with duckdb.connect(":memory:") as connection:
            connection.execute(f"CREATE TABLE target_panel({','.join(definitions)})")
            connection.executemany(f"INSERT INTO target_panel VALUES ({','.join('?' for _ in columns)})",
                                   [[row.get(name) for name in columns] for row in joined])
            connection.execute("COPY target_panel TO ? (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)", [str(staging / "panel.parquet")])
        payload = {**identity, "created_at": datetime.now(timezone.utc).isoformat(), "version": version,
                   "rows": len(joined), "markets": len({row["market_id"] for row in joined}),
                   "periods": len({row["period"] for row in joined}), "features": sorted(feature_names),
                   "exclusions": dict(sorted(exclusions.items())), "panel_sha256": file_sha256(staging / "panel.parquet"),
                   "limitations": ["Only analyst-approved, model-eligible targets are included.",
                                   "Multiple unresolved sources for one market-period are excluded, never averaged.",
                                   "Analyst-defined markets use only explicit, effective-dated county weights; missing county features remain null.",
                                   "Unknown release dates use the conservative retrieval-date fallback recorded at import."]}
        payload["manifest_hash"] = _manifest_hash(payload)
        (staging / "target_panel_manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staging, final_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return TargetPanelResult(property_type, target, frequency, "succeeded", len(joined),
                             len({row["market_id"] for row in joined}), len({row["period"] for row in joined}),
                             panel_path, manifest_path, manifest["manifest_hash"], target_hashes,
                             tuple(sorted(source_hashes)), tuple(sorted(feature_hashes)), dict(sorted(exclusions.items())))
