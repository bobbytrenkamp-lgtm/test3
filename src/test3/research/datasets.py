from __future__ import annotations

from dataclasses import dataclass
from calendar import monthrange
from datetime import date
import hashlib
import json
import math
from typing import Iterable, Mapping


def _period(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("panel period is required")
    # Lexical order is chronological for the governed ISO/year/quarter forms.
    if len(text) == 4 and text.isdigit():
        return text
    if len(text) == 7 and text[4:6] == "-Q" and text[:4].isdigit() and text[6] in "1234":
        return text
    if len(text) == 7 and text[4] == "-":
        try:
            date.fromisoformat(text + "-01")
        except ValueError as exc:
            raise ValueError(f"unsupported panel period: {text}") from exc
        return text
    try:
        date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"unsupported panel period: {text}") from exc
    return text[:10]


def period_bounds(value: object) -> tuple[date, date]:
    """Return inclusive bounds for a governed panel period."""
    label = _period(value)
    if len(label) == 4:
        year = int(label)
        return date(year, 1, 1), date(year, 12, 31)
    if len(label) == 7 and label[4:6] == "-Q":
        year, quarter = int(label[:4]), int(label[-1])
        start_month, end_month = (quarter - 1) * 3 + 1, quarter * 3
        return date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1])
    if len(label) == 7:
        year, month = int(label[:4]), int(label[5:7])
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    parsed = date.fromisoformat(label[:10])
    return parsed, parsed


def availability_date(value: object) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError("availability date is required")
    if len(text) in {4, 7}:
        return period_bounds(text)[1]
    return date.fromisoformat(text[:10])


def _number(value: object, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


@dataclass(frozen=True)
class PanelDataset:
    rows: tuple[dict, ...]
    target: str
    features: tuple[str, ...]
    entity_column: str
    time_column: str
    excluded_missing: int
    dataset_hash: str

    @property
    def entities(self) -> tuple[str, ...]:
        return tuple(sorted({row[self.entity_column] for row in self.rows}))

    @property
    def periods(self) -> tuple[str, ...]:
        return tuple(sorted({row[self.time_column] for row in self.rows}))

    @property
    def periods_by_entity(self) -> dict[str, int]:
        return {entity: len({row[self.time_column] for row in self.rows
                             if row[self.entity_column] == entity}) for entity in self.entities}


def prepare_panel(
    records: Iterable[Mapping[str, object]], *, target: str, features: Iterable[str],
    entity_column: str = "market_id", time_column: str = "period",
    property_type_column: str | None = "property_type", required_property_type: str | None = None,
    availability_suffix: str = "__available_at",
) -> PanelDataset:
    """Create a complete-case, leakage-checked panel without imputing missing values."""
    feature_names = tuple(dict.fromkeys(str(item) for item in features))
    if not feature_names:
        raise ValueError("at least one feature is required")
    if target in feature_names:
        raise ValueError("target cannot be included as a predictor")
    if any(not item.isidentifier() for item in (target, *feature_names, entity_column, time_column)):
        raise ValueError("panel column names must be safe identifiers")
    rows, excluded, keys, observed_property_types = [], 0, set(), set()
    for source in records:
        entity, period = str(source.get(entity_column) or "").strip(), _period(source.get(time_column))
        if not entity:
            raise ValueError("panel entity is required")
        key = (entity, period)
        if key in keys:
            raise ValueError(f"duplicate panel observation: {entity}/{period}")
        keys.add(key)
        property_type = str(source.get(property_type_column) or "").strip().lower() if property_type_column else ""
        if property_type:
            observed_property_types.add(property_type)
        if required_property_type and property_type != required_property_type.lower():
            continue
        values = [source.get(target), *(source.get(name) for name in feature_names)]
        if any(value is None or value == "" for value in values):
            excluded += 1
            continue
        row = {entity_column: entity, time_column: period, target: _number(source[target], target)}
        row.update({name: _number(source[name], name) for name in feature_names})
        if property_type_column:
            row[property_type_column] = property_type or None
        _, period_end = period_bounds(period)
        for name in feature_names:
            available = source.get(name + availability_suffix)
            if available not in (None, ""):
                available_on = availability_date(available)
                if available_on > period_end:
                    raise ValueError(f"future leakage: {name} was unavailable at {entity}/{period}")
                row[name + availability_suffix] = available_on.isoformat()
        target_available = source.get(target + availability_suffix)
        if target_available not in (None, ""):
            row[target + availability_suffix] = availability_date(target_available).isoformat()
        rows.append(row)
    if required_property_type is None and len(observed_property_types) > 1:
        raise ValueError("mixed property types require an explicit property-type filter")
    rows.sort(key=lambda item: (item[time_column], item[entity_column]))
    if not rows:
        raise ValueError("panel has no complete eligible observations")
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PanelDataset(tuple(rows), target, feature_names, entity_column, time_column, excluded,
                        hashlib.sha256(payload.encode()).hexdigest())
