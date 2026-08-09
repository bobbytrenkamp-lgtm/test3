from __future__ import annotations

from decimal import Decimal


def exact_growth(current: Decimal | str, prior: Decimal | str, *, years: int = 1) -> Decimal | None:
    current_value, prior_value = Decimal(str(current)), Decimal(str(prior))
    if prior_value == 0:
        return None
    if years < 1:
        raise ValueError("years must be positive")
    return (current_value / prior_value) ** (Decimal(1) / Decimal(years)) - 1


def ratio_per_1000(numerator: Decimal | str, denominator: Decimal | str) -> Decimal | None:
    denominator_value = Decimal(str(denominator))
    return None if denominator_value == 0 else Decimal(str(numerator)) / denominator_value * 1000
