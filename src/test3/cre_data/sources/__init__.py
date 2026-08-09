"""Governed registry of CRE outcome sources and non-target proxies."""

from .catalog import CRE_TARGET_SOURCES, source_catalog
from .spec import CRETargetSourceSpec

__all__ = ["CRETargetSourceSpec", "CRE_TARGET_SOURCES", "source_catalog"]
