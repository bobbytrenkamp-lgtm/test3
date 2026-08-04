from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Finding:
    rule_code: str
    severity: str
    explanation: str
    compared_values: dict
    source_documents: list[str]
    page_references: list[int]
    suggested_next_step: str


def _decimal(values: dict, key: str) -> Decimal | None:
    value = values.get(key)
    try:
        return Decimal(str(value)) if value is not None and value != "" else None
    except Exception:
        return None


def _ratio_difference(left: Decimal, right: Decimal) -> Decimal:
    return abs(left - right) / max(abs(left), abs(right), Decimal("0.0001"))


def reconcile(values: dict) -> list[Finding]:
    findings: list[Finding] = []

    def add(code: str, severity: str, explanation: str, keys: list[str], next_step: str):
        compared = {key: values.get(key) for key in keys}
        documents = sorted({str(values.get(f"{key}__document", "unknown")) for key in keys})
        pages = sorted({int(values.get(f"{key}__page")) for key in keys if values.get(f"{key}__page")})
        findings.append(Finding(code, severity, explanation, compared, documents, pages, next_step))

    price, noi, cap = (_decimal(values, key) for key in ("asking_price", "broker_stated_noi", "broker_stated_cap_rate"))
    if price and noi and cap:
        calculated = noi / price
        stated = cap / 100 if cap > 1 else cap
        if abs(calculated - stated) > Decimal("0.001"):
            add("CAP_RATE_MATH", "high", f"Price and NOI imply {calculated:.2%}, not the stated {stated:.2%} cap rate.", ["asking_price", "broker_stated_noi", "broker_stated_cap_rate"], "Confirm price and NOI against their source pages.")

    occupied, total_area, stated_occupancy = (_decimal(values, key) for key in ("rent_roll_occupied_area", "rent_roll_total_area", "occupancy"))
    if occupied is not None and total_area and stated_occupancy is not None:
        calculated = occupied / total_area
        stated = stated_occupancy / 100 if stated_occupancy > 1 else stated_occupancy
        if abs(calculated - stated) > Decimal("0.01"):
            add("OCCUPANCY_AREA", "high", "Occupied area divided by rent-roll total area does not match stated occupancy.", ["rent_roll_occupied_area", "rent_roll_total_area", "occupancy"], "Review vacancy rows and the occupancy convention.")

    comparisons = [
        ("AREA_OM_VS_RENT_ROLL", "rent_roll_total_area", "rentable_square_feet", Decimal("0.01"), "Rent-roll area differs from OM rentable area."),
        ("RENT_VS_OPERATIONS", "rent_roll_annualized_rent", "operating_rental_revenue", Decimal("0.05"), "Annualized rent differs from operating-statement rental revenue."),
        ("NOI_LINE_ITEMS", "calculated_noi", "operating_statement_noi", Decimal("0.005"), "Revenue less above-NOI expenses differs from stated NOI."),
        ("NOI_HISTORICAL_VS_PRO_FORMA", "historical_noi", "pro_forma_noi", Decimal("0.10"), "Pro forma NOI materially differs from historical NOI."),
        ("LEASE_DATES", "lease_expiration", "rent_roll_expiration", Decimal("0"), "Lease and rent-roll expiration dates differ."),
        ("LEASE_RENT", "lease_current_rent", "rent_roll_current_rent", Decimal("0.01"), "Lease schedule and rent-roll current rent differ."),
        ("LEASE_AREA", "lease_area", "rent_roll_lease_area", Decimal("0.005"), "Lease and rent-roll area differ."),
        ("UNIT_COUNT", "om_unit_count", "rent_roll_unit_count", Decimal("0"), "Unit counts differ across documents."),
        ("PRICE_OM_VS_LOI", "asking_price", "loi_price", Decimal("0"), "Acquisition price differs between OM and LOI."),
        ("PRICE_LOI_VS_PSA", "loi_price", "psa_price", Decimal("0"), "Acquisition price differs between LOI and PSA."),
        ("CAPEX_TOTAL", "capex_line_item_total", "capex_stated_total", Decimal("0.005"), "Capital budget line items do not add to the stated total."),
        ("DEBT_LTV", "calculated_ltv", "stated_ltv", Decimal("0.005"), "Debt amount divided by value differs from stated LTV."),
        ("DEBT_LTC", "calculated_ltc", "stated_ltc", Decimal("0.005"), "Debt amount divided by cost differs from stated LTC."),
        ("ALL_IN_RATE", "calculated_all_in_rate", "stated_interest_rate", Decimal("0.0001"), "Index plus spread does not equal the stated all-in rate."),
    ]
    for code, left_key, right_key, threshold, message in comparisons:
        left, right = _decimal(values, left_key), _decimal(values, right_key)
        if left is None or right is None:
            continue
        mismatch = left != right if threshold == 0 else _ratio_difference(left, right) > threshold
        if mismatch:
            add(code, "medium", message, [left_key, right_key], "Select the controlling source and record the rationale.")

    periods = values.get("operating_periods")
    if isinstance(periods, list) and len(set(periods)) != len(periods):
        add("DUPLICATE_PERIOD", "medium", "The operating statement contains duplicate periods.", ["operating_periods"], "Review duplicated columns or rows.")
    if isinstance(periods, list) and len(periods) not in (0, 12):
        add("MISSING_PERIOD", "high", f"Expected 12 monthly periods; received {len(periods)}.", ["operating_periods"], "Identify and request missing periods.")
    row_ids = values.get("row_identifiers")
    if isinstance(row_ids, list) and len(set(row_ids)) != len(row_ids):
        add("DUPLICATE_ROW", "medium", "Duplicate row identifiers were detected.", ["row_identifiers"], "Review duplicates before approval.")
    expected_rows, actual_rows = _decimal(values, "expected_row_count"), _decimal(values, "actual_row_count")
    if expected_rows is not None and actual_rows is not None and expected_rows != actual_rows:
        add("DROPPED_ROWS", "high", "Parsed row count differs from the source row count.", ["expected_row_count", "actual_row_count"], "Inspect parser warnings and unmapped rows.")
    for candidate in values.get("ocr_values", []) if isinstance(values.get("ocr_values"), list) else []:
        if any(token in str(candidate) for token in ("O.OO", "l,", "S,")):
            add("OCR_PUNCTUATION", "medium", "An OCR value contains characters commonly confused with digits.", ["ocr_values"], "Compare the value with the highlighted image region.")
            break
    names = values.get("tenant_names", [])
    if isinstance(names, list):
        for index, left in enumerate(names):
            for right in names[index + 1:]:
                normalized_left = "".join(ch for ch in left.lower() if ch.isalnum())
                normalized_right = "".join(ch for ch in right.lower() if ch.isalnum())
                if normalized_left != normalized_right and SequenceMatcher(None, normalized_left, normalized_right).ratio() > 0.88:
                    add("TENANT_NAME_VARIATION", "low", f"Tenant names may refer to the same party: {left!r} and {right!r}.", ["tenant_names"], "Confirm legal tenant names; do not merge automatically.")
                    return findings
    return findings


def as_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(finding) for finding in findings]

