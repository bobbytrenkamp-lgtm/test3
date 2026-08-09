from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import uuid

from .ingestion import ingest_observations
from .manifests import file_sha256, verified_manifests
from .quality import profile_parquet
from .sources import PublicDataRequest, get_adapter
from .storage import WarehousePaths


RUN_SCHEMA = """CREATE TABLE IF NOT EXISTS warehouse_refresh_runs(
id TEXT PRIMARY KEY, source_id TEXT NOT NULL, dataset_id TEXT NOT NULL, started_at TEXT NOT NULL,
completed_at TEXT, status TEXT NOT NULL CHECK(status IN ('running','succeeded','unchanged','failed','cancelled')),
request_parameters_json TEXT NOT NULL, raw_snapshot_hash TEXT, manifest_hash TEXT, row_count INTEGER, error_summary TEXT);
CREATE INDEX IF NOT EXISTS warehouse_refresh_runs_source ON warehouse_refresh_runs(source_id,dataset_id,started_at);"""


def _now(): return datetime.now(timezone.utc).isoformat()


class RefreshLog:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.executescript(RUN_SCHEMA); db.commit()

    def start(self, source_id, dataset_id, request):
        run_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO warehouse_refresh_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (run_id, source_id, dataset_id, _now(), None, "running", json.dumps(request, sort_keys=True), None, None, None, None))
            db.commit()
        return run_id

    def finish(self, run_id, status, *, raw_hash=None, manifest_hash=None, row_count=None, error=None):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE warehouse_refresh_runs SET completed_at=?,status=?,raw_snapshot_hash=?,manifest_hash=?,row_count=?,error_summary=? WHERE id=?",
                       (_now(), status, raw_hash, manifest_hash, row_count, str(error)[:2000] if error else None, run_id))
            db.commit()

    def latest(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM warehouse_refresh_runs ORDER BY started_at DESC")]


def refresh_source(paths: WarehousePaths, source: str, request: PublicDataRequest, *, dry_run=False) -> dict:
    adapter = get_adapter(source)
    request = PublicDataRequest(request.dataset_id, request.from_year, request.to_year, request.geography,
                                {**request.parameters, "_normalizer_version": adapter.normalizer_version})
    dataset_id = adapter.dataset_id
    if adapter.source_id == "census_acs":
        variable = request.parameters.get("variable", "B01003_001E").lower()
        dataset_id = f"acs5_{request.geography or 'county'}_{request.to_year or request.from_year}_{variable}"
    elif adapter.source_id == "census_bps":
        dataset_id = f"annual_county_{request.to_year or request.from_year}"
    elif adapter.source_id == "bls_laus_ces":
        if request.parameters.get("annual_county"):
            dataset_id = f"laus_county_annual_{request.to_year or request.from_year}"
        elif request.parameters.get("qcew_year"):
            dataset_id = f"qcew_county_annual_{request.parameters['qcew_year']}"
        elif request.parameters.get("series"): dataset_id = "national_" + request.parameters["series"].lower()
        elif request.parameters.get("state"): dataset_id = "laus_county_state_" + request.parameters["state"]
        else: dataset_id = "laus_county_chunk_" + request.parameters.get("chunk", "00-04").replace("-", "_")
    elif adapter.source_id == "fred_public":
        dataset_id = "macro_" + request.parameters.get("series", "DGS10").lower()
    elif adapter.source_id == "bea_regional":
        dataset_id = "regional_" + request.parameters.get("table", "CAINC1").lower()
    elif adapter.source_id == "census_cbsa_crosswalk":
        dataset_id = "county_cbsa_" + str(request.parameters.get("vintage", "2023"))
    elif adapter.source_id == "hud_public":
        dataset_id = "fair_market_rents_history"
    elif adapter.source_id == "census_hvs":
        dataset_id = "hvs_" + request.parameters.get("series", "rental_vacancy_rate")
    request = PublicDataRequest(dataset_id, request.from_year, request.to_year, request.geography, request.parameters)
    urls = adapter.discover(request)
    if dry_run:
        return {"source_id": adapter.source_id, "dataset_id": dataset_id, "status": "dry_run", "urls": urls, "request": request.serializable()}
    log = RefreshLog(paths.root / "refresh-state.sqlite3")
    run_id = log.start(adapter.source_id, dataset_id, request.serializable())
    try:
        snapshot = adapter.fetch(request, paths)
        manifest_path = paths.contained(Path("manifests") / adapter.source_id / dataset_id / f"{snapshot.source_version}.json")
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            log.finish(run_id, "unchanged", raw_hash=snapshot.sha256, manifest_hash=payload["manifest_hash"], row_count=payload["row_count"])
            return {"run_id": run_id, "status": "unchanged", "source_id": adapter.source_id, "dataset_id": dataset_id,
                    "source_version": snapshot.source_version, "rows": payload["row_count"], "raw_sha256": snapshot.sha256, "manifest_hash": payload["manifest_hash"]}
        result = ingest_observations(paths, source_id=adapter.source_id, dataset_id=dataset_id,
                                     source_version=snapshot.source_version, domain=adapter.domain,
                                     rows=adapter.validate(adapter.normalize(snapshot)))
        quality = profile_parquet(result.parquet_path)
        quality_path = result.manifest_path.with_suffix(".quality")
        quality_path.write_text(json.dumps({**quality, "quality_version": "1.0.0", "parquet_sha256": file_sha256(result.parquet_path)}, default=str, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        log.finish(run_id, "succeeded", raw_hash=snapshot.sha256, manifest_hash=result.manifest_hash, row_count=result.row_count)
        return {"run_id": run_id, "status": "succeeded", "source_id": adapter.source_id, "dataset_id": dataset_id,
                "source_version": snapshot.source_version, "rows": result.row_count, "raw_sha256": snapshot.sha256,
                "manifest_hash": result.manifest_hash, "quality": quality}
    except Exception as exc:
        log.finish(run_id, "failed", error=exc)
        raise


def manifest_status(paths: WarehousePaths) -> list[dict]:
    runs = RefreshLog(paths.root / "refresh-state.sqlite3").latest()
    by_source = {}
    for run in runs:
        by_source.setdefault((run["source_id"], run["dataset_id"]), run)
    results = []
    for payload in verified_manifests(paths):
        key = (payload["source_id"], payload["dataset_id"])
        result = {name: payload.get(name) for name in ("source_id", "dataset_id", "source_version", "created_at", "status", "row_count", "min_observation_date", "max_observation_date", "manifest_hash")}
        quality_path = paths.contained(Path("manifests") / payload["source_id"] / payload["dataset_id"] / f"{payload['source_version']}.quality")
        result.update({"integrity": "verified", "quality": json.loads(quality_path.read_text()) if quality_path.exists() else None,
                       "last_refresh": by_source.get(key)})
        results.append(result)
    return results
