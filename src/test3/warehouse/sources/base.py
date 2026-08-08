from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

from ..storage import WarehousePaths


@dataclass(frozen=True)
class PublicDataRequest:
    dataset_id: str
    from_year: int | None = None
    to_year: int | None = None
    geography: str | None = None
    parameters: dict[str, str] = field(default_factory=dict)

    def serializable(self) -> dict:
        return {"dataset_id": self.dataset_id, "from_year": self.from_year, "to_year": self.to_year,
                "geography": self.geography, "parameters": dict(sorted(self.parameters.items()))}


@dataclass(frozen=True)
class RawSnapshot:
    source_id: str
    dataset_id: str
    source_version: str
    content_path: Path
    metadata_path: Path
    retrieved_at: str
    source_url: str
    final_url: str
    http_status: int
    content_type: str
    byte_count: int
    sha256: str
    request_parameters: dict


class PublicDataSource(ABC):
    source_id: str
    dataset_id: str
    domain: str
    allowed_hosts: tuple[str, ...]

    @abstractmethod
    def discover(self, request: PublicDataRequest) -> list[str]: ...

    @abstractmethod
    def normalize(self, snapshot: RawSnapshot) -> Iterable[dict]: ...

    def fetch(self, request: PublicDataRequest, paths: WarehousePaths) -> RawSnapshot:
        from .http import GovernedHttpClient
        urls = self.discover(request)
        if len(urls) != 1:
            raise ValueError("each bounded refresh request must resolve to exactly one download")
        response = GovernedHttpClient(self.allowed_hosts).get(urls[0])
        return preserve_raw_snapshot(paths, self.source_id, request, response)

    def validate(self, observations: Iterable[dict]) -> Iterable[dict]:
        return observations


def preserve_raw_snapshot(paths: WarehousePaths, source_id: str, request: PublicDataRequest, response) -> RawSnapshot:
    paths.initialize()
    retrieved = response.retrieved_at
    digest = response.sha256
    version = f"{retrieved[:10]}-{digest[:16]}"
    raw_names = {"census_acs": "census", "bls_laus_ces": "bls", "bea_regional": "bea",
                 "fred_public": "fred", "census_bps": "building_permits", "test1_local": "test1"}
    directory = paths.contained(Path("raw") / raw_names.get(source_id, source_id) /
                                request.dataset_id / version)
    if directory.exists():
        metadata_path = directory / "metadata.json"
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        candidates = [item for item in directory.glob("response.*") if item.is_file()]
        if len(candidates) != 1 or hashlib.sha256(candidates[0].read_bytes()).hexdigest() != digest:
            raise ValueError("existing raw snapshot content does not match its immutable identity")
        return RawSnapshot(source_id, request.dataset_id, version, candidates[0], metadata_path,
                           existing["retrieved_at"], existing["source_url"], existing["final_url"],
                           existing["http_status"], existing["content_type"], existing["bytes"],
                           existing["sha256"], existing["request_parameters"])
    directory.mkdir(parents=True, exist_ok=False)
    content_type = response.content_type.split(";", 1)[0].strip().lower()
    extension = {"application/json": ".json", "text/csv": ".csv", "application/zip": ".zip"}.get(content_type, ".raw")
    content_path = directory / f"response{extension}"
    content_path.write_bytes(response.body)
    metadata = {
        "metadata_version": "1.0.0", "source_id": source_id, "dataset_id": request.dataset_id,
        "request_parameters": request.serializable(), "retrieved_at": retrieved, "source_version": version,
        "source_url": response.request_url, "final_url": response.final_url, "http_status": response.status,
        "content_type": response.content_type, "bytes": len(response.body), "sha256": digest,
    }
    metadata_path = directory / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return RawSnapshot(source_id, request.dataset_id, version, content_path, metadata_path, retrieved,
                       response.request_url, response.final_url, response.status, response.content_type,
                       len(response.body), digest, request.serializable())


def raw_hash(raw: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def canonical_row(snapshot: RawSnapshot, *, series: str, geography_type: str, geography_id: str,
                  observation_date: str, period_type: str, metric: str, value: object, unit: str,
                  source_row: int, state_fips: str | None = None, county_fips: str | None = None,
                  cbsa: str | None = None, methodology: str = "Official source value; no imputation.",
                  quality_level: str = "high", raw: object | None = None) -> dict:
    reference = f"{snapshot.content_path.as_posix()}#row={source_row}"
    return {
        "observation_id": None, "source_id": snapshot.source_id, "source_dataset": snapshot.dataset_id,
        "source_series": series, "source_version": snapshot.source_version,
        "retrieved_at": snapshot.retrieved_at, "as_of_date": snapshot.retrieved_at[:10],
        "geography_type": geography_type, "geography_id": geography_id, "state_fips": state_fips,
        "county_fips": county_fips, "cbsa": cbsa, "city": None, "submarket": None,
        "property_type": None, "property_subtype": None, "observation_date": observation_date,
        "period_type": period_type, "metric": metric, "value": str(value), "unit": unit,
        "currency": "USD" if unit.startswith("USD") else None, "sample_count": None,
        "quality_level": quality_level, "methodology": methodology, "transformation_version": "source-normalizer/1.0.0",
        "raw_source_reference": reference, "raw_row_hash": raw_hash(raw if raw is not None else {"row": source_row}),
        "normalized_row_hash": None,
    }
