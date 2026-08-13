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
    source_market_name: str | None = None
    definition_version: str = "1.0.0"
    weighting_methodology: str = ""
    analyst_rationale: str = ""
    source_evidence: str = ""
    review_status: str = "draft"

    def validate(self) -> None:
        date.fromisoformat(self.effective_from)
        if self.effective_to and date.fromisoformat(self.effective_to) < date.fromisoformat(self.effective_from):
            raise ValueError("market definition effective_to precedes effective_from")
        if not self.source_definition.strip() or not self.counties:
            raise ValueError("market definition requires source evidence and counties")
        if self.review_status not in {"draft", "analyst_approved", "rejected"}:
            raise ValueError("invalid market definition review status")
        if self.review_status == "analyst_approved" and not all((
            (self.source_market_name or "").strip(), self.definition_version.strip(),
            self.weighting_methodology.strip(), self.analyst_rationale.strip(), self.source_evidence.strip(),
        )):
            raise ValueError("approved market definitions require version, rationale, weighting, and evidence")
        total = Decimal("0")
        seen = set()
        for item in self.counties:
            county_fips = str(item.get("county_fips", ""))
            if not county_fips.isdigit() or len(county_fips) != 5:
                raise ValueError("market county mapping requires five-digit county FIPS")
            if county_fips in seen:
                raise ValueError("market county mappings may not repeat a county")
            seen.add(county_fips)
            weight = Decimal(str(item.get("weight")))
            if weight <= 0:
                raise ValueError("market weights must be positive")
            total += weight
        if total != Decimal("1"):
            raise ValueError("market county weights must total one exactly")


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
