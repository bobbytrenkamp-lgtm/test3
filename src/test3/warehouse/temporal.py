from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re


@dataclass(frozen=True)
class Period:
    label: str
    period_type: str
    observation_date: date


def normalize_period(value: str | date | datetime, period_type: str | None = None) -> Period:
    raw = value.date().isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else str(value).strip()
    inferred = period_type
    if re.fullmatch(r"\d{4}", raw):
        inferred = inferred or "annual"
        result = Period(raw, inferred, date(int(raw), 1, 1))
    elif match := re.fullmatch(r"(\d{4})-Q([1-4])", raw.upper()):
        inferred = inferred or "quarterly"
        result = Period(raw.upper(), inferred, date(int(match.group(1)), (int(match.group(2)) - 1) * 3 + 1, 1))
    elif match := re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", raw):
        inferred = inferred or "monthly"
        result = Period(raw, inferred, date(int(match.group(1)), int(match.group(2)), 1))
    else:
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"unsupported observation period: {raw!r}") from exc
        inferred = inferred or "irregular"
        result = Period(raw, inferred, parsed)
    expected = {"annual": 4, "quarterly": 7, "monthly": 7, "daily": 10, "weekly": 10, "irregular": 10}
    if inferred not in expected or (inferred != "irregular" and len(raw) != expected[inferred]):
        raise ValueError(f"period {raw!r} does not match period_type {inferred!r}")
    return result
