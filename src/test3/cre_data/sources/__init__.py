"""Governed registry of CRE outcome sources and non-target proxies."""

from .catalog import CRE_TARGET_SOURCES, source_catalog
from .discovery import CANDIDATES, CRESourceCandidate, discovery_catalog
from .spec import CRETargetSourceSpec

__all__ = ["CANDIDATES", "CRESourceCandidate", "CRETargetSourceSpec", "CRE_TARGET_SOURCES",
           "discovery_catalog", "source_catalog"]
