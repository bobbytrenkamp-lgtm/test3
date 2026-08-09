from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from test3.warehouse.storage import WarehousePaths


@dataclass(frozen=True)
class MarketDefinition:
    market_id: str
    market_name: str
    property_type: str
    source_definition: str
    effective_from: str
    effective_to: str | None
    counties: tuple[dict, ...]

    def validate(self) -> None:
        date.fromisoformat(self.effective_from)
        if self.effective_to and date.fromisoformat(self.effective_to) < date.fromisoformat(self.effective_from):
            raise ValueError("market definition effective_to precedes effective_from")
        if not self.source_definition.strip() or not self.counties:
            raise ValueError("market definition requires source evidence and counties")
        total = Decimal("0")
        for item in self.counties:
            if not str(item.get("county_fips", "")).isdigit() or len(str(item["county_fips"])) != 5:
                raise ValueError("market county mapping requires five-digit county FIPS")
            weight = Decimal(str(item.get("weight")))
            if weight <= 0:
                raise ValueError("market weights must be positive")
            total += weight
        if abs(total - Decimal("1")) > Decimal("0.000001"):
            raise ValueError("market county weights must total one")


def save_market_definition(paths: WarehousePaths, definition: MarketDefinition) -> Path:
    definition.validate(); paths.initialize()
    payload = asdict(definition); payload["counties"] = list(definition.counties)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    directory = paths.contained(Path("manifests") / "cre_market_definitions" / definition.market_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{definition.effective_from}-{digest[:12]}.json"
    if not destination.exists():
        destination.write_text(json.dumps({**payload, "sha256": digest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def market_definitions(paths: WarehousePaths) -> list[dict]:
    root = paths.contained(Path("manifests") / "cre_market_definitions")
    output = []
    for path in sorted(root.glob("*/*.json")) if root.exists() else ():
        payload = json.loads(path.read_text(encoding="utf-8")); stored = payload.pop("sha256", None)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != stored:
            raise ValueError(f"market definition integrity failure: {path}")
        output.append({**payload, "sha256": stored})
    return output
