from __future__ import annotations

from datetime import date


def period_start(value: date, frequency: str) -> date:
    if frequency == "annual":
        return date(value.year, 1, 1)
    if frequency == "quarterly":
        return date(value.year, ((value.month - 1) // 3) * 3 + 1, 1)
    raise ValueError("frequency must be annual or quarterly")


def lagged_period(value: date, frequency: str, periods: int) -> date:
    if periods < 0:
        raise ValueError("periods cannot be negative")
    if frequency == "annual":
        return date(value.year - periods, value.month, 1)
    if frequency == "quarterly":
        absolute = value.year * 4 + (value.month - 1) // 3 - periods
        return date(absolute // 4, (absolute % 4) * 3 + 1, 1)
    raise ValueError("frequency must be annual or quarterly")


def validate_frequency_conversion(input_frequency: str, output_frequency: str, transformation: str) -> None:
    allowed = {
        ("annual", "annual", "source_last_observation"),
        ("annual", "quarterly", "annual_carry_forward"),
        ("daily", "annual", "period_mean_broadcast"),
        ("daily", "annual", "period_end_broadcast"),
        ("weekly", "annual", "period_mean_broadcast"),
        ("monthly", "annual", "period_mean_broadcast"),
        ("daily", "quarterly", "period_mean_broadcast"),
        ("daily", "quarterly", "period_end_broadcast"),
        ("weekly", "quarterly", "period_mean_broadcast"),
        ("monthly", "quarterly", "period_mean_broadcast"),
    }
    if (input_frequency, output_frequency, transformation) not in allowed:
        raise ValueError(f"ungoverned frequency conversion: {input_frequency}->{output_frequency} ({transformation})")
