from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from test3.cre_data.schema import normalize_cre_record


SOURCE_NAME = "AvalonBay Communities SEC quarterly supplemental"
SOURCE_DATASET = "sec_avb_same_store_market_quarter"
SOURCE_CLASS = "public_company_filing"
SCHEMA_VERSION = "avb-attachment-4/2026.1"
COMPATIBILITY = {
    "average_monthly_revenue_per_occupied_home": {
        "maa_metric": "effective_rent", "classification": "comparable_with_limitation",
        "limitation": "AVB includes amortized concessions and uncollectible lease revenue; MAA reports effective rent.",
    },
    "average_monthly_revenue_growth_yoy": {
        "maa_metric": "rent_growth_yoy", "classification": "comparable_with_limitation",
        "limitation": "Growth is based on AVB residential revenue per occupied home, not MAA effective rent.",
    },
    "occupancy_rate": {
        "maa_metric": "occupancy_rate", "classification": "not_comparable",
        "limitation": "AVB reports economic occupancy while MAA reports physical occupancy.",
    },
    "economic_vacancy_rate": {
        "maa_metric": "vacancy_rate", "classification": "not_comparable",
        "limitation": "Complement of economic occupancy is not physical vacancy.",
    },
    "revenue_growth_yoy": {
        "maa_metric": "revenue_growth_yoy", "classification": "comparable_with_limitation",
        "limitation": "Both are same-store revenue growth, but portfolio eligibility definitions are issuer-specific.",
    },
    "inventory": {
        "maa_metric": "inventory", "classification": "comparable_with_limitation",
        "limitation": "Both are source-defined same-store apartment homes; portfolio membership differs.",
    },
}


class AVBSchemaDriftError(ValueError):
    code = "REVIEW_REQUIRED_SCHEMA_DRIFT"


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables, self.table, self.row, self.cell = [], None, None, None
    def handle_starttag(self, tag, attrs):
        if tag == "table": self.table = []
        elif tag == "tr" and self.table is not None: self.row = []
        elif tag in {"td", "th"} and self.row is not None: self.cell = []
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split())); self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row): self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table); self.table = None


@dataclass(frozen=True)
class AVBParseResult:
    filing_url: str
    filing_date: str
    period: str
    markets: int
    observations: tuple[dict, ...]
    schema_version: str = SCHEMA_VERSION


def write_avb_review_csv(source: str | Path, destination: str | Path, *, filing_url: str,
                         filing_date: str, retrieved_at: str | None = None) -> dict:
    """Convert one lawfully obtained SEC exhibit into a candidate-only review file."""
    source, destination = Path(source), Path(destination)
    content = source.read_bytes()
    result = parse_avb_html(content.decode("utf-8"), filing_url=filing_url, filing_date=filing_date,
                            retrieved_at=retrieved_at)
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = sorted({key for row in result.observations for key in row})
    with destination.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers); writer.writeheader(); writer.writerows(result.observations)
    payload = {"source_sha256": hashlib.sha256(content).hexdigest(), "review_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
               "period": result.period, "markets": result.markets, "observations": len(result.observations),
               "metrics": sorted({row["metric"] for row in result.observations}), "analyst_review_required": True,
               "compatibility": methodology_comparison_artifact()}
    return payload


def methodology_comparison_artifact() -> dict:
    body = {"schema_version": "test3-source-methodology-compatibility/1.0.0",
            "source_a": "MAA", "source_b": "AVB",
            "metrics": [{"avb_metric": metric, **details} for metric, details in sorted(COMPATIBILITY.items())]}
    body["artifact_hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def _number(value: str) -> Decimal:
    text = value.replace("$", "").replace(",", "").replace("%", "").strip()
    if text in {"", "—", "-"}: return Decimal("0")
    if text.startswith("(") and text.endswith(")"): text = "-" + text[1:-1]
    return Decimal(text)


def _market_id(name: str) -> str:
    return "avb-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _base(*, market, period, filing_url, filing_date, retrieved_at, metric, value, unit,
          methodology, homes, evidence):
    return normalize_cre_record({
        "market": market, "geography_type": "market", "geography_id": _market_id(market),
        "period": period, "frequency": "quarterly", "property_type": "multifamily",
        "property_subtype": "avb_same_store_portfolio", "metric": metric, "value": format(value, "f"),
        "unit": unit, "source_name": SOURCE_NAME, "source_identifier": f"{filing_url}#{evidence}",
        "source_period": period, "release_date": filing_date, "retrieved_at": retrieved_at,
        "methodology": methodology, "vintage": filing_date,
        "licensing_notes": "Public SEC-filed numeric facts used for local research; filing text is not redistributed.",
        "redistribution_permitted": "no", "verification_status": "unverified", "source_class": SOURCE_CLASS,
        "sample_count": homes, "target_classification": "institutional_target",
        "notes": "Source-defined AVB same-store portfolio market, not a CBSA; analyst approval and governed geography required.",
    }, row_number=1)


def parse_avb_html(content: str, *, filing_url: str, filing_date: str,
                   retrieved_at: str | None = None) -> AVBParseResult:
    """Fail-closed parser for AVB Attachment 4 current-quarter versus prior-year rows."""
    if not filing_url.startswith("https://www.sec.gov/Archives/edgar/data/915912/"):
        raise ValueError("AVB evidence must be an official allowlisted SEC Archives filing")
    parser = _Tables(); parser.feed(content)
    candidates = []
    for table in parser.tables:
        flat = " ".join(cell for row in table for cell in row)
        if not all(label in flat for label in ("Apartment Homes", "Average Monthly Revenue", "Economic Occupancy", "Residential Revenue")):
            continue
        match = re.search(r"Q([1-4])\s*(?:20)?(\d{2}).*Q\1\s*(?:20)?(\d{2})", flat)
        if match and int(match.group(2)) - int(match.group(3)) == 1:
            candidates.append((table, match))
    if len(candidates) != 1:
        raise AVBSchemaDriftError("REVIEW_REQUIRED_SCHEMA_DRIFT: expected exactly one AVB current/prior-year table")
    table, match = candidates[0]
    period = f"20{match.group(2)}-Q{match.group(1)}"; retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    output = []
    for raw_cells in table:
        cells = [cell for cell in raw_cells if cell not in {"", "$", "%"}]
        if len(cells) != 11: continue
        market = cells[0].strip()
        if not market or market in {"Market"} or market.startswith(("Total", "Apartment Homes", "Quarterly", "AvalonBay")): continue
        try:
            homes = int(_number(cells[1])); current = _number(cells[2]); prior = _number(cells[3])
            growth = _number(cells[4]) / 100; occupancy = _number(cells[5]) / 100
            prior_occupancy = _number(cells[6]) / 100; occupancy_change = _number(cells[7]) / 100
            revenue = _number(cells[8]); prior_revenue = _number(cells[9]); reported_revenue_growth = _number(cells[10]) / 100
        except (ValueError, ArithmeticError):
            raise AVBSchemaDriftError(f"REVIEW_REQUIRED_SCHEMA_DRIFT: malformed AVB row {market!r}") from None
        if homes <= 0 or prior <= 0 or prior_revenue <= 0:
            raise AVBSchemaDriftError(f"REVIEW_REQUIRED_SCHEMA_DRIFT: invalid AVB row {market!r}")
        if abs(current / prior - 1 - growth) > Decimal("0.0015"):
            raise AVBSchemaDriftError(f"REVIEW_REQUIRED_SCHEMA_DRIFT: revenue-per-home reconciliation failed for {market}")
        if abs(occupancy - prior_occupancy - occupancy_change) > Decimal("0.0015"):
            raise AVBSchemaDriftError(f"REVIEW_REQUIRED_SCHEMA_DRIFT: economic occupancy reconciliation failed for {market}")
        revenue_growth = revenue / prior_revenue - 1
        if abs(revenue_growth - reported_revenue_growth) > Decimal("0.0015"):
            raise AVBSchemaDriftError(f"REVIEW_REQUIRED_SCHEMA_DRIFT: residential revenue reconciliation failed for {market}")
        values = (
            ("average_monthly_revenue_per_occupied_home", current, "USD_per_unit_month", "same_store_revenue_per_occupied_home"),
            ("average_monthly_revenue_growth_yoy", growth, "decimal_fraction", "same_store_revenue_per_occupied_home_yoy"),
            ("occupancy_rate", occupancy, "decimal_fraction", "economic_occupancy"),
            ("economic_vacancy_rate", Decimal("1") - occupancy, "decimal_fraction", "economic_vacancy"),
            ("revenue_growth_yoy", revenue_growth, "decimal_fraction", "same_store_revenue_yoy"),
            ("inventory", Decimal(homes), "units", "same_store_inventory"),
        )
        for metric, value, unit, method in values:
            output.append(_base(market=market, period=period, filing_url=filing_url, filing_date=filing_date,
                                retrieved_at=retrieved_at, metric=metric, value=value, unit=unit,
                                methodology=method, homes=homes, evidence=f"attachment-4:{_market_id(market)}:{metric}"))
    if not output:
        raise AVBSchemaDriftError("REVIEW_REQUIRED_SCHEMA_DRIFT: no unambiguous AVB market rows")
    return AVBParseResult(filing_url, filing_date, period, len({row["geography_id"] for row in output}), tuple(output))
