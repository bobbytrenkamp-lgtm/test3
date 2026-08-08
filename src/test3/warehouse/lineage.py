from __future__ import annotations

import json
from pathlib import Path
import duckdb

from .duckdb_engine import sql_literal
from .manifests import verified_manifests


def observation_lineage(paths, observation_id: str) -> dict | None:
    if not observation_id or len(observation_id) > 128:
        raise ValueError("a bounded observation ID is required")
    for manifest in verified_manifests(paths):
        files = manifest["resolved_files"]
        source = "read_parquet([" + ",".join(sql_literal(str(path)) for path in files) + "])"
        with duckdb.connect(":memory:") as db:
            result = db.execute(f"SELECT * REPLACE (CAST(retrieved_at AS VARCHAR) AS retrieved_at) FROM {source} WHERE observation_id=? LIMIT 1", [observation_id])
            row = result.fetchone()
            if row:
                observation = dict(zip([item[0] for item in result.description], row, strict=True))
                reference = Path(str(observation["raw_source_reference"]).split("#", 1)[0])
                metadata_path = reference.parent / "metadata.json"
                return {"observation": observation, "source": manifest["source_id"], "dataset": manifest["dataset_id"],
                        "source_series": observation["source_series"], "raw_snapshot": json.loads(metadata_path.read_text()) if metadata_path.exists() else None,
                        "raw_source_reference": observation["raw_source_reference"], "retrieval_date": str(observation["retrieved_at"]),
                        "manifest": {key: value for key, value in manifest.items() if key not in ("resolved_files",)},
                        "transformation_version": observation["transformation_version"], "quality_status": observation["quality_level"]}
    return None
