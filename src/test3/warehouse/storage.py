from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


WAREHOUSE_DIRS = (
    "raw/census", "raw/bls", "raw/fred", "raw/bea", "raw/hud",
    "raw/building_permits", "raw/housing", "raw/test1", "raw/user_imports", "raw/cre_market",
    "normalized/demographics", "normalized/labor", "normalized/income", "normalized/housing",
    "normalized/construction", "normalized/capital_markets", "normalized/rent", "normalized/vacancy",
    "normalized/supply", "normalized/transactions", "normalized/expenses", "normalized/geography",
    "features/county_month", "features/county_quarter", "features/cbsa_month",
    "features/cbsa_quarter", "features/market_quarter", "features/property_type_market_quarter",
    "models", "manifests",
)


@dataclass(frozen=True)
class WarehousePaths:
    root: Path

    @classmethod
    def from_data_root(cls, data_root: str | Path = "data") -> "WarehousePaths":
        return cls(Path(data_root).resolve() / "warehouse")

    def initialize(self) -> None:
        for relative in WAREHOUSE_DIRS:
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def contained(self, relative: str | Path) -> Path:
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("warehouse path escapes the configured root")
        return candidate
