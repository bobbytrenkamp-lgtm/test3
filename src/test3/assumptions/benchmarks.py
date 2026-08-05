from __future__ import annotations

from decimal import Decimal


def quantile(values: list[Decimal], fraction: Decimal) -> Decimal:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * Decimal(len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (Decimal("1") - weight) + ordered[high] * weight


def describe(values: list[str]) -> dict:
    decimals = [Decimal(value) for value in values]
    return {
        "median": format(quantile(decimals, Decimal("0.5")), "f"),
        "q1": format(quantile(decimals, Decimal("0.25")), "f"),
        "q3": format(quantile(decimals, Decimal("0.75")), "f"),
        "minimum": format(min(decimals), "f"), "maximum": format(max(decimals), "f"), "sampleCount": len(decimals),
    }
