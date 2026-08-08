"""Local analytical warehouse boundary for Test3."""

from .catalog import SOURCE_CATALOG, SourceSpec
from .duckdb_engine import WarehouseEngine
from .ingestion import IngestResult, ingest_observations
from .storage import WarehousePaths

__all__ = ["SOURCE_CATALOG", "IngestResult", "SourceSpec", "WarehouseEngine", "WarehousePaths", "ingest_observations"]
