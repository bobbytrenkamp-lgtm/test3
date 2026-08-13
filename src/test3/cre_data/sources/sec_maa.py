from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from test3.cre_data.derivations import derive_vacancy_from_occupancy
from test3.cre_data.schema import REQUIRED, normalize_cre_record


SOURCE_NAME = "Mid-America Apartment Communities SEC quarterly supplement"
SOURCE_CLASS = "public_company_filing"
SOURCE_DATASET = "sec_maa_same_store_market_quarter"
SNAPSHOT_SCHEMA = "test3-sec-browser-snapshot/1.0.0"
_QOQ_HEADINGS = (
    "MULTIFAMILY SAME STORE PORTFOLIO QUARTER OVER QUARTER COMPARISONS",
    "MULTIFAMILY SAME STORE PORTFOLIO QUARTERLY COMPARISONS",
)
_SEQUENTIAL_HEADINGS = (
    "MULTIFAMILY SAME STORE PORTFOLIO SEQUENTIAL QUARTER COMPARISONS",
    "MULTIFAMILY SAME STORE PORTFOLIO SEQUENTIAL QUARTERLY COMPARISONS",
)
_OCCUPANCY_HEADINGS = (
    "MULTIFAMILY SAME STORE PORTFOLIO NOI CONTRIBUTION PERCENTAGE",
    "NOI CONTRIBUTION PERCENTAGE BY MARKET",
)
_ROW = re.compile(r'^\s*- row "(.*)":\s*$', re.MULTILINE)
_MARKET = re.compile(r"^(.+?)\s+(\d[\d,]*)\s+(.*)$")
_PERIOD = re.compile(r"\bQ([1-4])\s+(20\d{2})\b")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_STATE_MARKET = re.compile(r"^.+,\s+(?:[A-Z]{2}|D\.C\.)(?:[/-][A-Z]{2})?$")
_UNSUFFIXED_MARKETS = frozenset({"Northern Virginia"})


@dataclass(frozen=True)
class MAAParseResult:
    filing_url: str
    filing_date: str
    period: str
    effective_rent_rows: int
    rent_growth_rows: int
    inventory_rows: int
    occupancy_rows: int
    vacancy_rows: int
    observations: tuple[dict, ...]


def _market_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"maa-{slug}"


def _is_market_name(name: str) -> bool:
    """Reject date/header rows before numeric shape can make them observations."""
    return bool(_STATE_MARKET.fullmatch(name) or name in _UNSUFFIXED_MARKETS)


def _section(snapshot: str, start: str, end: str | None) -> str:
    start_index = snapshot.find(start)
    if start_index < 0:
        return ""
    end_index = snapshot.find(end, start_index + len(start)) if end else -1
    return snapshot[start_index:end_index if end_index >= 0 else len(snapshot)]


def _first_heading(snapshot: str, candidates: tuple[str, ...]) -> str:
    present = [(snapshot.find(item), item) for item in candidates if snapshot.find(item) >= 0]
    if not present:
        return candidates[0]
    return min(present)[1]


def _numbers(value: str) -> list[Decimal]:
    value = re.sub(r"\(([\d,.]+)\s*\)%", r"-\1%", value)
    return [Decimal(item.replace(",", "")) for item in _NUMBER.findall(value)]


def _period(snapshot: str) -> str:
    section = _section(snapshot, _first_heading(snapshot, _QOQ_HEADINGS),
                       _first_heading(snapshot, _SEQUENTIAL_HEADINGS))
    match = _PERIOD.search(section)
    if not match:
        raise ValueError("MAA filing does not expose a governed current-quarter header")
    return f"{match.group(2)}-Q{match.group(1)}"


def _base_row(*, market: str, period: str, filing_url: str, filing_date: str,
              retrieved_at: str, metric: str, value: Decimal, unit: str,
              methodology: str, sample_count: int, evidence: str,
              verification_status: str) -> dict:
    return {
        "market": market,
        "geography_type": "market",
        "geography_id": _market_id(market),
        "state_fips": None,
        "county_fips": None,
        "cbsa": None,
        "submarket": None,
        "period": period,
        "frequency": "quarterly",
        "property_type": "multifamily",
        "property_subtype": "maa_same_store_portfolio",
        "metric": metric,
        "value": format(value, "f"),
        "unit": unit,
        "source_name": SOURCE_NAME,
        "source_identifier": f"{filing_url}#{evidence}",
        "source_period": period,
        "release_date": filing_date,
        "retrieved_at": retrieved_at,
        "methodology": methodology,
        "vintage": filing_date,
        "licensing_notes": (
            "Public SEC-filed numeric facts used for local analysis. Filing text and proprietary datasets "
            "are not redistributed; cite the exact exhibit, table, market row, and filing date."
        ),
        "redistribution_permitted": "no",
        "verification_status": verification_status,
        "source_class": SOURCE_CLASS,
        "sample_count": sample_count,
        "target_classification": "institutional_target",
        "methodology_version": "maa-same-store-market/1.0.0",
        "notes": (
            "Source-defined MAA same-store portfolio market, not a CBSA. Same-store composition and market "
            "definition may change; source methodology compatibility is required before modeling."
        ),
    }


def parse_maa_accessibility_snapshot(snapshot: str, *, filing_url: str, filing_date: str,
                                     retrieved_at: str | None = None,
                                     verification_status: str = "unverified") -> MAAParseResult:
    """Parse browser-visible SEC table rows without treating extraction as analyst approval."""
    if not filing_url.startswith("https://www.sec.gov/Archives/edgar/data/912595/"):
        raise ValueError("MAA evidence must be an official allowlisted SEC Archives filing")
    if verification_status not in {"unverified", "analyst_verified"}:
        raise ValueError("MAA snapshot rows must be unverified or analyst_verified")
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    period = _period(snapshot)
    rows: list[dict] = []

    qoq_heading = _first_heading(snapshot, _QOQ_HEADINGS)
    qoq = _section(snapshot, qoq_heading, _first_heading(snapshot, _SEQUENTIAL_HEADINGS))
    for row_text in _ROW.findall(qoq):
        match = _MARKET.match(row_text)
        if not match:
            continue
        market, units_text, rest = match.groups()
        if market.startswith(("Total ", "Other", "Units ")) or not _is_market_name(market):
            continue
        values = [Decimal(units_text.replace(",", "")), *_numbers(rest)]
        if len(values) < 13:
            continue
        units = int(values[0])
        current_rent, prior_rent, reported_yoy = values[-3], values[-2], values[-1] / Decimal("100")
        if prior_rent <= 0 or abs((current_rent / prior_rent - 1) - reported_yoy) > Decimal("0.0015"):
            raise ValueError(f"MAA rent-growth cross-check failed for {market} {period}")
        for metric, value, unit, method, evidence in (
            ("effective_rent", current_rent, "USD_per_unit_month", "effective_rent", "same-store-qoq-effective-rent"),
            ("rent_growth_yoy", reported_yoy, "decimal_fraction", "same_store_yoy", "same-store-qoq-rent-yoy"),
            ("inventory", Decimal(units), "units", "same_store_inventory", "same-store-qoq-apartment-units"),
        ):
            raw = _base_row(market=market, period=period, filing_url=filing_url, filing_date=filing_date,
                            retrieved_at=retrieved_at, metric=metric, value=value, unit=unit,
                            methodology=method, sample_count=units, evidence=f"{evidence}:{_market_id(market)}",
                            verification_status=verification_status)
            rows.append(normalize_cre_record(raw, row_number=len(rows) + 1))

    occupancy_heading = _first_heading(snapshot, _OCCUPANCY_HEADINGS)
    occupancy = _section(snapshot, occupancy_heading, qoq_heading)
    occupancy_rows: list[dict] = []
    for row_text in _ROW.findall(occupancy):
        match = _MARKET.match(row_text)
        if not match:
            continue
        market, units_text, rest = match.groups()
        if market.startswith(("Total ", "Other", "Units ", "Apartment Units ")) or not _is_market_name(market):
            continue
        values = [Decimal(units_text.replace(",", "")), *_numbers(rest)]
        if len(values) < 4:
            continue
        # After apartment units and NOI contribution, the first percentage is
        # current-quarter physical occupancy. Later columns may be prior-year,
        # YTD-current and YTD-prior occupancy; selecting from the end silently
        # substituted YTD for Q2-Q4 filings.
        current_quarter_occupancy = values[2]
        raw = _base_row(market=market, period=period, filing_url=filing_url, filing_date=filing_date,
                        retrieved_at=retrieved_at, metric="occupancy_rate", value=current_quarter_occupancy / Decimal("100"),
                        unit="decimal_fraction", methodology="physical_occupancy", sample_count=int(values[0]),
                        evidence=f"same-store-occupancy:{_market_id(market)}",
                        verification_status=verification_status)
        occupancy_rows.append(normalize_cre_record(raw, row_number=len(rows) + len(occupancy_rows) + 1))
    rows.extend(occupancy_rows)
    rent_units = {(row["geography_id"], row["period"]): row["sample_count"] for row in rows
                  if row["metric"] == "effective_rent"}
    for row in occupancy_rows:
        key = row["geography_id"], row["period"]
        if key in rent_units and rent_units[key] != row["sample_count"]:
            raise ValueError(f"MAA apartment-unit cross-check failed for {row['market']} {row['period']}")
    vacancy_rows = derive_vacancy_from_occupancy(occupancy_rows)
    rows.extend(vacancy_rows)
    return MAAParseResult(
        filing_url=filing_url,
        filing_date=filing_date,
        period=period,
        effective_rent_rows=sum(row["metric"] == "effective_rent" for row in rows),
        rent_growth_rows=sum(row["metric"] == "rent_growth_yoy" for row in rows),
        inventory_rows=sum(row["metric"] == "inventory" for row in rows),
        occupancy_rows=sum(row["metric"] == "occupancy_rate" for row in rows),
        vacancy_rows=sum(row["metric"] == "vacancy_rate" for row in rows),
        observations=tuple(rows),
    )


def load_snapshot_bundle(folder: str | Path) -> tuple[list[dict], list[dict]]:
    """Load immutable browser snapshot + metadata pairs into a conservative review package."""
    folder = Path(folder)
    observations, filings = [], []
    for metadata_path in sorted(folder.glob("*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("schema_version") != SNAPSHOT_SCHEMA:
            continue
        snapshot_path = folder / metadata["snapshot_file"]
        content = snapshot_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != metadata["sha256"]:
            raise ValueError(f"SEC snapshot integrity failure: {snapshot_path.name}")
        result = parse_maa_accessibility_snapshot(
            content.decode("utf-8"), filing_url=metadata["filing_url"], filing_date=metadata["filing_date"],
            retrieved_at=metadata["retrieved_at"], verification_status="unverified",
        )
        observations.extend(result.observations)
        filings.append({key: value for key, value in result.__dict__.items() if key != "observations"})
    return observations, filings


def write_review_csv(folder: str | Path, destination: str | Path) -> dict:
    rows, filings = load_snapshot_bundle(folder)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = sorted(REQUIRED | {key for row in rows for key in row if key not in {
        "observation_id", "observation_date", "currency", "source_row", "raw_row_hash"
    }})
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {"filings": filings, "observations": len(rows), "review_csv": str(destination),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "analyst_review_required": True}
