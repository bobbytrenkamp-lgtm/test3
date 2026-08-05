from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict


ENTITY_ALIASES = {
    "rent_roll": ("rent_roll_record", {
        "tenant": "tenant_name", "tenant_name": "tenant_name", "unit": "unit", "building": "building",
        "suite": "suite", "unit_type": "unit_type", "rentable_area": "rentable_area",
        "lease_commencement": "lease_commencement", "lease_expiration": "lease_expiration",
        "current_rent": "current_rent", "rent_unit": "rent_unit", "base_rent_basis": "rent_unit", "escalations": "escalations",
        "reimbursements": "reimbursements", "occupancy_status": "occupancy_status",
        "security_deposit": "security_deposit", "concessions": "concessions",
        "renewal_options": "renewal_options", "lease_status": "occupancy_status", "notes": "notes",
    }),
    "t12_operating_statement": ("operating_account_period", {"account": "account_label", "account_label": "account_label", "classification": "account_classification", "annual_total": "annual_total", "source_total": "source_total"}),
    "historical_operating_statement": ("operating_account_period", {"account": "account_label", "account_label": "account_label", "classification": "account_classification", "annual_total": "annual_total", "source_total": "source_total"}),
    "commercial_lease": ("lease_schedule_record", {"tenant": "tenant_name", "party": "party", "premises": "premises", "rentable_area": "rentable_area", "commencement": "commencement", "expiration": "expiration", "base_rent": "base_rent", "base_rent_basis": "base_rent_basis", "lease_status": "lease_status", "free_rent": "free_rent", "recovery_structure": "recovery_structure", "base_year": "base_year", "expense_stop": "expense_stop", "pro_rata_share": "pro_rata_share", "renewal_options": "renewal_options", "termination_rights": "termination_rights", "guarantor": "guarantor"}),
    "lease_amendment": ("lease_schedule_record", {"tenant": "tenant_name", "party": "party", "premises": "premises", "rentable_area": "rentable_area", "commencement": "commencement", "expiration": "expiration", "base_rent": "base_rent", "base_rent_basis": "base_rent_basis", "lease_status": "lease_status", "renewal_options": "renewal_options", "termination_rights": "termination_rights", "amendment_effects": "amendment_effects"}),
    "debt_quote": ("debt_term_record", {"lender": "lender", "loan_amount": "loan_amount", "funding_date": "funding_date", "debt_type": "debt_type", "rate_type": "rate_type", "interest_rate": "interest_rate", "index": "index", "spread": "spread", "rate_floor": "rate_floor", "rate_cap": "rate_cap", "amortization": "amortization", "interest_only_period": "interest_only_period", "term": "term", "maturity": "maturity", "origination_fee": "origination_fee", "exit_fee": "exit_fee", "prepayment_terms": "prepayment_terms", "dscr_requirement": "dscr_requirement", "debt_yield_requirement": "debt_yield_requirement", "ltv_requirement": "ltv_requirement", "ltc_requirement": "ltc_requirement", "recourse": "recourse", "reserves": "reserves", "extension_options": "extension_options", "conditions_precedent": "conditions_precedent"}),
    "loan_term_sheet": ("debt_term_record", {"lender": "lender", "loan_amount": "loan_amount", "funding_date": "funding_date", "debt_type": "debt_type", "rate_type": "rate_type", "interest_rate": "interest_rate", "index": "index", "spread": "spread", "rate_floor": "rate_floor", "rate_cap": "rate_cap", "amortization": "amortization", "interest_only_period": "interest_only_period", "term": "term", "maturity": "maturity", "origination_fee": "origination_fee", "exit_fee": "exit_fee", "prepayment_terms": "prepayment_terms", "dscr_requirement": "dscr_requirement", "debt_yield_requirement": "debt_yield_requirement", "ltv_requirement": "ltv_requirement", "ltc_requirement": "ltc_requirement", "recourse": "recourse", "reserves": "reserves", "extension_options": "extension_options", "conditions_precedent": "conditions_precedent"}),
}


def derive_entities(category: str, cells: list[dict]) -> list[dict]:
    contract = ENTITY_ALIASES.get(category)
    if not contract:
        return []
    entity_type, aliases = contract
    grouped: dict[int, list[dict]] = defaultdict(list)
    for cell in cells:
        match = re.fullmatch(r"row\.(\d+)\.(.+)", cell["field_name"])
        if match:
            grouped[int(match.group(1))].append({**cell, "header": match.group(2)})
    entities = []
    for source_row, row_cells in sorted(grouped.items()):
        data, period_values, source_ids = {}, {}, []
        for cell in row_cells:
            value = cell.get("normalized_value") if cell.get("normalized_value") is not None else cell.get("raw_value")
            canonical = aliases.get(cell["header"])
            if canonical:
                data[canonical] = value
                source_ids.append(cell["id"])
            elif entity_type == "operating_account_period":
                period_values[cell["header"]] = value
                source_ids.append(cell["id"])
        if period_values:
            data["period_values"] = period_values
        if not data or (entity_type == "operating_account_period" and "account_label" not in data):
            continue
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
        entities.append({"entity_type": entity_type, "source_row": source_row, "data": data, "data_json": canonical_json, "data_sha256": hashlib.sha256(canonical_json.encode()).hexdigest(), "source_value_ids": sorted(source_ids)})
    return entities
