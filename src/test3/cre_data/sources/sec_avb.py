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
SCHEMA_VERSION = "avb-attachment-4/2026.2"
# These issuer-reported regions overlap displayed child markets and therefore
# cannot enter a cross-market panel alongside their components.
OVERLAPPING_ROLLUPS = {
    "Metro NY/NJ": ("New York City", "New York City, NY", "New York - Suburban", "New York Suburban", "New Jersey"),
    "Northern California": ("East Bay", "Oakland - East Bay, CA", "Oakland-East Bay, CA",
                            "Oakland-East Bay", "Oakland/East Bay", "San Francisco", "San Francisco, CA",
                            "San Jose", "San Jose, CA"),
    "Southern California": ("Los Angeles", "Los Angeles, CA", "Orange County", "Orange County, CA",
                            "San Diego", "San Diego, CA"),
    "Mid-Atlantic": ("Washington Metro", "Northern Virginia", "Suburban Maryland", "Washington DC",
                     "Washington, DC", "Baltimore", "Baltimore, MD"),
}
SOURCE_MARKET_ALIASES = {
    "Oakland - East Bay, CA": "East Bay", "Oakland-East Bay, CA": "East Bay",
    "Oakland-East Bay": "East Bay", "Oakland/East Bay": "East Bay",
    "Los Angeles, CA": "Los Angeles", "Orange County, CA": "Orange County", "San Diego, CA": "San Diego",
    "San Francisco, CA": "San Francisco", "San Jose, CA": "San Jose",
    "New York City, NY": "New York City", "New York Suburban": "New York - Suburban",
    "Baltimore": "Baltimore, MD", "Washington, DC": "Washington DC",
}
COMPATIBILITY = {
    "average_monthly_revenue_per_occupied_home": {
        "maa_metric": "effective_rent", "classification": "comparable_with_limitation",
        "limitation": "AVB includes amortized concessions and uncollectible lease revenue; MAA reports effective rent.",
    },
    "average_monthly_revenue_growth_yoy": {
        "maa_metric": "rent_growth_yoy", "classification": "comparable_with_limitation",
        "limitation": "Growth is based on AVB residential revenue per occupied home, not MAA effective rent.",
    },
    "average_rental_rate_growth_yoy": {
        "maa_metric": "rent_growth_yoy", "classification": "comparable_with_limitation",
        "limitation": "AVB's legacy average rental rate includes its disclosed concession methodology; issuer portfolios differ.",
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
    "revenue_growth_yoy_excluding_rent_relief": {
        "maa_metric": "revenue_growth_yoy", "classification": "not_comparable",
        "limitation": "AVB's disclosed rent-relief adjustment is source-specific and is retained separately.",
    },
    "revenue_growth_yoy_cash_basis": {
        "maa_metric": "revenue_growth_yoy", "classification": "not_comparable",
        "limitation": "AVB's cash-basis concession treatment is a distinct source-specific series.",
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


def write_avb_series_review_csv(filings: list[dict], destination: str | Path) -> dict:
    """Build one immutable candidate review file from explicitly enumerated SEC exhibits."""
    destination = Path(destination)
    observations, evidence, schemas = [], [], set()
    if not filings:
        raise ValueError("at least one AVB filing is required")
    for filing in filings:
        source = Path(filing["path"])
        if not source.is_file():
            raise ValueError(f"AVB evidence file does not exist: {source}")
        content = source.read_bytes()
        result = parse_avb_html(content.decode("utf-8"), filing_url=filing["filing_url"],
                                filing_date=filing["filing_date"], retrieved_at=filing.get("retrieved_at"))
        observations.extend(result.observations); schemas.add(result.schema_version)
        evidence.append({"path": source.name, "filing_url": result.filing_url,
                         "filing_date": result.filing_date, "period": result.period,
                         "source_sha256": hashlib.sha256(content).hexdigest(),
                         "schema_version": result.schema_version,
                         "source_accession": result.observations[0].get("source_accession"),
                         "release_date_evidence_status": result.observations[0].get(
                             "release_date_evidence_status")})
    identities = [row["observation_id"] for row in observations]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate AVB observations across supplied filings")
    observations.sort(key=lambda row: (row["period"], row["geography_id"], row["metric"]))
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite immutable AVB review file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = sorted({key for row in observations for key in row})
    with destination.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers); writer.writeheader(); writer.writerows(observations)
    periods = sorted({row["period"] for row in observations})
    payload = {"schema_version": "test3-avb-sec-series/1.0.0", "evidence": evidence,
               "review_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
               "periods": periods, "period_count": len(periods),
               "markets": len({row["geography_id"] for row in observations}),
               "observations": len(observations), "schema_versions": sorted(schemas),
               "metrics": sorted({row["metric"] for row in observations}),
               "analyst_review_required": True, "compatibility": methodology_comparison_artifact()}
    payload["continuity"] = series_continuity_artifact(observations, evidence)
    payload["artifact_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _quarter_ordinal(period: str) -> int:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if not match:
        raise ValueError(f"invalid quarterly period: {period}")
    return int(match.group(1)) * 4 + int(match.group(2)) - 1


def series_continuity_artifact(observations: list[dict], evidence: list[dict]) -> dict:
    """Expose market-universe and methodology breaks; never harmonize them silently."""
    periods = sorted({row["period"] for row in observations}, key=_quarter_ordinal)
    markets_by_period = {
        period: sorted({row["market"] for row in observations if row["period"] == period})
        for period in periods
    }
    period_gaps = []
    market_transitions = []
    for previous, current in zip(periods, periods[1:]):
        distance = _quarter_ordinal(current) - _quarter_ordinal(previous)
        if distance != 1:
            period_gaps.append({"previous_period": previous, "next_period": current,
                                "missing_quarters": distance - 1})
        previous_markets, current_markets = set(markets_by_period[previous]), set(markets_by_period[current])
        added, removed = sorted(current_markets - previous_markets), sorted(previous_markets - current_markets)
        if added or removed:
            market_transitions.append({"previous_period": previous, "next_period": current,
                                       "added": added, "removed": removed,
                                       "review_required": True})
    ordered_evidence = sorted(evidence, key=lambda row: _quarter_ordinal(row["period"]))
    schema_transitions = []
    for previous, current in zip(ordered_evidence, ordered_evidence[1:]):
        if previous["schema_version"] != current["schema_version"]:
            schema_transitions.append({"previous_period": previous["period"], "next_period": current["period"],
                                       "from_schema": previous["schema_version"],
                                       "to_schema": current["schema_version"],
                                       "pooling_permitted": False, "review_required": True})
    metric_periods = {
        metric: sorted({row["period"] for row in observations if row["metric"] == metric}, key=_quarter_ordinal)
        for metric in sorted({row["metric"] for row in observations})
    }
    body = {"schema_version": "test3-avb-series-continuity/1.0.0", "periods": periods,
            "period_gaps": period_gaps, "markets_by_period": markets_by_period,
            "market_transitions": market_transitions, "schema_transitions": schema_transitions,
            "metric_periods": metric_periods,
            "release_date_evidence": [{"period": row["period"],
                                         "source_accession": row.get("source_accession"),
                                         "status": row.get("release_date_evidence_status")}
                                        for row in ordered_evidence],
            "homogeneous_methodology": not schema_transitions,
            "automatic_harmonization_permitted": False if schema_transitions else True}
    body["artifact_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body


def methodology_comparison_artifact() -> dict:
    body = {"schema_version": "test3-source-methodology-compatibility/1.0.0",
            "source_a": "MAA", "source_b": "AVB",
            "metrics": [{"avb_metric": metric, **details} for metric, details in sorted(COMPATIBILITY.items())]}
    body["artifact_hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def _number(value: str, *, reported_change: bool = False) -> Decimal:
    text = value.replace("$", "").replace(",", "").replace("%", "").strip()
    dash_only = bool(text) and all(not character.isalnum() for character in text)
    mojibake_dash = text in {"\u00e2\u20ac\u201d", "\u00e2\u20ac\u201c"}
    if (dash_only or mojibake_dash) and reported_change:
        return Decimal("0")
    if not text or dash_only or mojibake_dash:
        raise ValueError("missing numeric value")
    if text.startswith("(") and text.endswith(")"): text = "-" + text[1:-1]
    return Decimal(text)


def _market_id(name: str) -> str:
    canonical = SOURCE_MARKET_ALIASES.get(name, name)
    return "avb-" + re.sub(r"[^a-z0-9]+", "-", canonical.lower()).strip("-")


def _base(*, market, period, filing_url, filing_date, retrieved_at, metric, value, unit,
          methodology, homes, evidence, schema_version, geography_role, parent_market,
          source_accession, release_date_evidence_status):
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
        "source_market_name": market, "canonical_source_market": SOURCE_MARKET_ALIASES.get(market, market),
        "source_geography_role": geography_role, "source_parent_market": parent_market,
        "source_accession": source_accession,
        "release_date_evidence_status": release_date_evidence_status,
        "notes": ("Source-defined AVB same-store portfolio market, not a CBSA; analyst approval and governed "
                  f"geography required. Source schema: {schema_version}."),
    }, row_number=1)


def parse_avb_html(content: str, *, filing_url: str, filing_date: str,
                   retrieved_at: str | None = None) -> AVBParseResult:
    """Fail-closed parser for AVB Attachment 4 current-quarter versus prior-year rows."""
    if not filing_url.startswith("https://www.sec.gov/Archives/edgar/data/915912/"):
        raise ValueError("AVB evidence must be an official allowlisted SEC Archives filing")
    accession_match = re.search(r"/Archives/edgar/data/915912/(\d{18})/", filing_url)
    if not accession_match:
        raise ValueError("AVB SEC filing URL must contain an issuer accession identifier")
    source_accession = accession_match.group(1)
    embedded_dates = re.findall(
        r"(?:For Immediate (?:News )?Release\s*)?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2})",
        content, flags=re.IGNORECASE,
    )
    parsed_embedded_dates = []
    for value in embedded_dates:
        try:
            parsed_embedded_dates.append(datetime.strptime(value, "%B %d, %Y").date().isoformat())
        except ValueError:
            continue
    if parsed_embedded_dates and filing_date not in parsed_embedded_dates:
        raise ValueError("supplied AVB release date does not match embedded SEC evidence date")
    release_date_evidence_status = ("embedded_release_date_verified" if parsed_embedded_dates
                                    else "manifest_asserted_review_required")
    parser = _Tables(); parser.feed(content)
    candidates = []
    for table in parser.tables:
        flat = " ".join(cell for row in table for cell in row)
        if not ("Apartment Homes" in flat and
                ("Average Monthly Revenue" in flat or "Average Monthly Rental Revenue" in flat or
                 "Average Rental Rates" in flat or "Average Rental Revenue Per Occupied Home" in flat) and
                "Economic Occupancy" in flat and
                ("Residential Revenue" in flat or "Residential Rental Revenue" in flat)):
            continue
        match = re.search(r"Q([1-4])\s*(?:20)?(\d{2}).*Q\1\s*(?:20)?(\d{2})", flat)
        if match and int(match.group(2)) - int(match.group(3)) == 1:
            candidates.append((table, match))
    if len(candidates) != 1:
        raise AVBSchemaDriftError("REVIEW_REQUIRED_SCHEMA_DRIFT: expected exactly one AVB current/prior-year table")
    table, match = candidates[0]
    period = f"20{match.group(2)}-Q{match.group(1)}"; retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    output = []
    table_text = " ".join(
        cell for row in table for cell in row
    )
    has_rent_relief_adjustment = "% Change Excluding Rent Relief" in table_text
    has_cash_basis_adjustment = "% Change on a Cash Basis" in table_text
    legacy_rental_rate = "Average Rental Rates" in table_text
    rental_revenue_per_home = "Average Rental Revenue Per Occupied Home" in table_text
    schema_version = ("avb-attachment-4/legacy-rental-rate-cash-basis-v1" if legacy_rental_rate else
                      "avb-attachment-4/rental-revenue-cash-basis-v1" if rental_revenue_per_home else
                      "avb-attachment-4/rent-relief-adjusted-v1" if has_rent_relief_adjustment else
                      "avb-attachment-4/core-v1")
    source_parent_by_child = {child: parent for parent, children in OVERLAPPING_ROLLUPS.items() for child in children}
    for raw_cells in table:
        cells = [cell for cell in raw_cells if cell not in {"", "$", "%"}]
        expected_cells = 12 if (has_rent_relief_adjustment or has_cash_basis_adjustment) else 11
        if len(cells) != expected_cells: continue
        market = cells[0].strip()
        if not market or market in {"Market"} or market.startswith(("Total", "Apartment Homes", "Quarterly", "AvalonBay")): continue
        try:
            homes = int(_number(cells[1])); current = _number(cells[2]); prior = _number(cells[3])
            growth = _number(cells[4], reported_change=True) / 100; occupancy = _number(cells[5]) / 100
            prior_occupancy = _number(cells[6]) / 100; occupancy_change = _number(cells[7], reported_change=True) / 100
            revenue = _number(cells[8]); prior_revenue = _number(cells[9]); reported_revenue_growth = _number(cells[10], reported_change=True) / 100
            adjusted_revenue_growth = (_number(cells[11], reported_change=True) / 100) if has_rent_relief_adjustment else None
            cash_basis_revenue_growth = (_number(cells[11], reported_change=True) / 100) if has_cash_basis_adjustment else None
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
        values = [
            (("average_rental_rate" if legacy_rental_rate else "average_monthly_revenue_per_occupied_home"),
             current, "USD_per_unit_month",
             ("same_store_average_rental_rate" if legacy_rental_rate else "same_store_revenue_per_occupied_home")),
            (("average_rental_rate_growth_yoy" if legacy_rental_rate else "average_monthly_revenue_growth_yoy"),
             growth, "decimal_fraction",
             ("same_store_average_rental_rate_yoy" if legacy_rental_rate else "same_store_revenue_per_occupied_home_yoy")),
            ("occupancy_rate", occupancy, "decimal_fraction", "economic_occupancy"),
            ("economic_vacancy_rate", Decimal("1") - occupancy, "decimal_fraction", "economic_vacancy"),
            ("revenue_growth_yoy", revenue_growth, "decimal_fraction", "same_store_revenue_yoy"),
            ("inventory", Decimal(homes), "units", "same_store_inventory"),
        ]
        if adjusted_revenue_growth is not None:
            values.append(("revenue_growth_yoy_excluding_rent_relief", adjusted_revenue_growth,
                           "decimal_fraction", "same_store_revenue_yoy_excluding_rent_relief"))
        if cash_basis_revenue_growth is not None:
            values.append(("revenue_growth_yoy_cash_basis", cash_basis_revenue_growth,
                           "decimal_fraction", "same_store_revenue_yoy_cash_basis"))
        for metric, value, unit, method in values:
            geography_role = "overlapping_region_rollup" if market in OVERLAPPING_ROLLUPS else "leaf_or_standalone"
            output.append(_base(market=market, period=period, filing_url=filing_url, filing_date=filing_date,
                                retrieved_at=retrieved_at, metric=metric, value=value, unit=unit,
                                methodology=method, homes=homes, evidence=f"attachment-4:{_market_id(market)}:{metric}",
                                schema_version=schema_version, geography_role=geography_role,
                                parent_market=source_parent_by_child.get(market), source_accession=source_accession,
                                release_date_evidence_status=release_date_evidence_status))
    if not output:
        raise AVBSchemaDriftError("REVIEW_REQUIRED_SCHEMA_DRIFT: no unambiguous AVB market rows")
    inventory = {row["source_market_name"]: int(row["value"]) for row in output if row["metric"] == "inventory"}
    for rollup, children in OVERLAPPING_ROLLUPS.items():
        present = [name for name in children if name in inventory]
        if rollup in inventory and present and sum(inventory[name] for name in present) != inventory[rollup]:
            raise AVBSchemaDriftError(
                f"REVIEW_REQUIRED_SCHEMA_DRIFT: {rollup} inventory does not reconcile to displayed components")
    return AVBParseResult(filing_url, filing_date, period,
                          len({row["geography_id"] for row in output}), tuple(output), schema_version)
