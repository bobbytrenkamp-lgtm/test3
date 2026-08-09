from __future__ import annotations

import json
from pathlib import Path
import re

import duckdb

from test3.warehouse.duckdb_engine import sql_literal
from test3.warehouse.storage import WarehousePaths

from .manifests import verify_feature_manifest


class FeaturePanel:
    def __init__(self, paths: WarehousePaths, table_name: str):
        if table_name not in {"county_year", "county_quarter", "cbsa_year", "cbsa_quarter"}:
            raise ValueError("unsupported governed feature table")
        self.paths, self.table_name = paths, table_name

    def versions(self) -> list[dict]:
        root = self.paths.contained(Path("features") / self.table_name)
        manifests = [verify_feature_manifest(path) for path in root.glob("version=*/feature_manifest.json")] if root.exists() else []
        return sorted(manifests, key=lambda item: item["created_at"])

    def latest(self) -> dict | None:
        root = self.paths.contained(Path("features") / self.table_name)
        candidates = []
        for path in root.glob("version=*/feature_manifest.json") if root.exists() else ():
            try:
                created_at = json.loads(path.read_text(encoding="utf-8"))["created_at"]
            except (OSError, json.JSONDecodeError, KeyError) as exc:
                raise ValueError(f"unreadable feature manifest: {path}") from exc
            candidates.append((created_at, path))
        return verify_feature_manifest(max(candidates)[1]) if candidates else None

    def query(self, *, columns: tuple[str, ...] | None = None, geography_id: str | None = None, limit: int = 1000) -> list[dict]:
        manifest = self.latest()
        if manifest is None:
            return []
        allowed = {"geography_type", "geography_id", "state_fips", "county_fips", "cbsa", "period_start", "year", "quarter", *manifest["features"], *manifest.get("availability_columns", [])}
        selected = columns or tuple(sorted(allowed))
        if not selected or set(selected) - allowed:
            raise ValueError("feature query contains unknown columns")
        if not 1 <= limit <= 100_000:
            raise ValueError("limit must be between 1 and 100000")
        panel_path = self.paths.contained(Path("features") / self.table_name / f"version={manifest['feature_table_version']}" / "panel.parquet")
        sql = f"SELECT {','.join(chr(34) + item + chr(34) for item in selected)} FROM read_parquet({sql_literal(str(panel_path))})"
        params = []
        if geography_id is not None:
            sql += " WHERE geography_id=?"; params.append(geography_id)
        sql += " ORDER BY geography_id,period_start LIMIT ?"; params.append(limit)
        with duckdb.connect(":memory:") as db:
            result = db.execute(sql, params)
            names = [item[0] for item in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

    def lineage(self, lineage_id: str) -> dict | None:
        if not re.fullmatch(r"[0-9a-f]{64}", lineage_id or ""):
            raise ValueError("lineage_id must be a SHA-256 hex digest")
        manifest = self.latest()
        if manifest is None:
            return None
        lineage_path = self.paths.contained(Path("features") / self.table_name / f"version={manifest['feature_table_version']}" / "lineage.parquet")
        with duckdb.connect(":memory:") as db:
            result = db.execute(f"SELECT * FROM read_parquet({sql_literal(str(lineage_path))}) WHERE lineage_id=? LIMIT 1", [lineage_id])
            row = result.fetchone()
            if not row:
                return None
            value = dict(zip([item[0] for item in result.description], row, strict=True))
            for field in ("input_observation_ids_json", "input_feature_lineage_ids_json", "input_manifest_hashes_json"):
                value[field.removesuffix("_json")] = json.loads(value.pop(field))
            return value

    def trace_lineage(self, lineage_id: str, *, maximum_nodes: int = 10_000) -> dict:
        """Resolve the feature-lineage DAG to original observation and manifest identifiers."""
        if not 1 <= maximum_nodes <= 100_000:
            raise ValueError("maximum_nodes must be between 1 and 100000")
        if not re.fullmatch(r"[0-9a-f]{64}", lineage_id or ""):
            raise ValueError("lineage_id must be a SHA-256 hex digest")
        manifest = self.latest()
        if manifest is None:
            raise ValueError("feature table has no published version")
        lineage_path = self.paths.contained(Path("features") / self.table_name / f"version={manifest['feature_table_version']}" / "lineage.parquet")
        pending, visited, nodes = [lineage_id], set(), []
        observations, manifests = set(), set()
        with duckdb.connect(":memory:") as db:
            db.execute("SET enable_progress_bar=false")
            while pending:
                pending = [item for item in pending if item not in visited]
                if not pending:
                    break
                batch = sorted(set(pending))[:500]
                batch_set = set(batch)
                pending = [item for item in pending if item not in batch_set]
                if len(visited) + len(batch) > maximum_nodes:
                    raise ValueError("feature lineage exceeds the configured node bound")
                placeholders = ",".join("?" for _ in batch)
                result = db.execute(f"SELECT * FROM read_parquet({sql_literal(str(lineage_path))}) WHERE lineage_id IN ({placeholders})", batch)
                names = [item[0] for item in result.description]
                found = {}
                for raw in result.fetchall():
                    node = dict(zip(names, raw, strict=True))
                    for field in ("input_observation_ids_json", "input_feature_lineage_ids_json", "input_manifest_hashes_json"):
                        node[field.removesuffix("_json")] = json.loads(node.pop(field))
                    found[node["lineage_id"]] = node
                missing = set(batch) - set(found)
                if missing:
                    raise ValueError(f"broken feature-lineage reference: {sorted(missing)[0]}")
                for current in batch:
                    node = found[current]; visited.add(current); nodes.append(node)
                    observations.update(node["input_observation_ids"]); manifests.update(node["input_manifest_hashes"])
                    pending.extend(node["input_feature_lineage_ids"])
        return {"root_lineage_id": lineage_id, "nodes": nodes,
                "input_observation_ids": sorted(observations), "input_manifest_hashes": sorted(manifests)}
