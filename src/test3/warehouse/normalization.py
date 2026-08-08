"""Mapping boundary for source-specific normalizers.

Normalizers must emit canonical dictionaries and may never invent a missing value,
silently forward-fill, or change frequency without recording the transformation.
"""

from __future__ import annotations

from collections.abc import Mapping

from .schemas import normalize_observation


def map_row(raw: Mapping[str, object], column_mapping: Mapping[str, str], constants: Mapping[str, object] | None = None) -> dict:
    candidate = dict(constants or {})
    for source_column, canonical_column in column_mapping.items():
        if source_column in raw:
            candidate[canonical_column] = raw[source_column]
    return normalize_observation(candidate)
