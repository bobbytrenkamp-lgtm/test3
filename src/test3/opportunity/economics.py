from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


SCHEMA_VERSION = "property-economic-evidence/1.0.0"
SOURCE_TYPES = {"analyst_entered", "document_evidence", "public_record", "user_owned", "test2_candidate"}
FIELD_SPECS = {
    "purchase_price": {"unit": "USD", "kind": "amount", "positive": True},
    "renovation_budget": {"unit": "USD", "kind": "amount"},
    "closing_costs": {"unit": "USD", "kind": "amount"},
    "holding_costs": {"unit": "USD", "kind": "amount"},
    "annual_property_taxes": {"unit": "USD/year", "kind": "amount"},
    "annual_insurance": {"unit": "USD/year", "kind": "amount"},
    "annual_utilities": {"unit": "USD/year", "kind": "amount"},
    "annual_other_operating_costs": {"unit": "USD/year", "kind": "amount"},
    "vacancy_rate": {"unit": "decimal_fraction", "kind": "rate"},
    "concessions_rate": {"unit": "decimal_fraction", "kind": "rate"},
    "loan_amount": {"unit": "USD", "kind": "amount"},
    "interest_rate": {"unit": "decimal_fraction", "kind": "rate"},
    "amortization_years": {"unit": "years", "kind": "years"},
    "loan_term_years": {"unit": "years", "kind": "years"},
}


def _number(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def normalize_economic_evidence(rows: list[dict], *, analysis_as_of: date) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("economic_inputs must be a list of no more than 100 fields")
    normalized, seen = [], set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"economic input {index} must be an object")
        field = str(row.get("field") or "").strip()
        if field not in FIELD_SPECS:
            raise ValueError(f"economic input {index} has unsupported field: {field}")
        if field in seen:
            raise ValueError(f"economic input field is duplicated: {field}")
        seen.add(field)
        spec = FIELD_SPECS[field]
        unit = str(row.get("unit") or "").strip()
        if unit != spec["unit"]:
            raise ValueError(f"{field} requires unit {spec['unit']}")
        value = _number(row.get("value"), field)
        if spec["kind"] == "amount" and (value < 0 or (spec.get("positive") and value <= 0)):
            raise ValueError(f"{field} must be {'positive' if spec.get('positive') else 'non-negative'}")
        if spec["kind"] == "rate" and not Decimal("0") <= value <= Decimal("1"):
            raise ValueError(f"{field} must be a decimal fraction between 0 and 1")
        if spec["kind"] == "years" and not Decimal("1") <= value <= Decimal("100"):
            raise ValueError(f"{field} must be between 1 and 100 years")
        source_type = str(row.get("source_type") or "").strip()
        source_reference = str(row.get("source_reference") or "").strip()
        licensing_notes = str(row.get("licensing_notes") or "").strip()
        as_of = str(row.get("as_of_date") or "").strip()
        if source_type not in SOURCE_TYPES or not source_reference or not licensing_notes or not as_of:
            raise ValueError(f"{field} requires governed source_type, source_reference, licensing_notes and as_of_date")
        try:
            as_of_date = date.fromisoformat(as_of)
        except ValueError as exc:
            raise ValueError(f"{field} as_of_date must use YYYY-MM-DD") from exc
        if as_of_date > analysis_as_of:
            raise ValueError(f"{field} cannot use future evidence")
        normalized.append({
            "field": field,
            "value": format(value, "f"),
            "unit": unit,
            "sourceType": source_type,
            "sourceReference": source_reference,
            "licensingNotes": licensing_notes,
            "asOfDate": as_of_date.isoformat(),
            "reviewStatus": "candidate_unapproved",
            "notes": str(row.get("notes") or "").strip() or None,
        })
    return sorted(normalized, key=lambda item: item["field"])


def economic_screen(evidence: list[dict], *, units: object, gross_potential_rent: dict | None) -> dict:
    values = {item["field"]: Decimal(item["value"]) for item in evidence}
    unit_count = _number(units, "subject units") if units not in (None, "") else None
    if unit_count is not None and unit_count <= 0:
        raise ValueError("subject units must be positive")
    basis_fields = ("purchase_price", "renovation_budget", "closing_costs", "holding_costs")
    known_basis = sum((values[field] for field in basis_fields if field in values), Decimal("0"))
    missing_basis = [field for field in basis_fields if field not in values]
    basis = None
    if "purchase_price" in values:
        basis = {
            "knownBasisSubtotal": format(known_basis, "f"),
            "totalEstimatedBasis": format(known_basis, "f") if not missing_basis else None,
            "components": {field: format(values[field], "f") for field in basis_fields if field in values},
            "missingComponents": missing_basis,
            "complete": not missing_basis,
            "basisPerUnit": format(known_basis / unit_count, "f") if unit_count and not missing_basis else None,
            "renovationPerUnit": format(values["renovation_budget"] / unit_count, "f") if unit_count and "renovation_budget" in values else None,
        }
    financing = None
    if basis and basis["complete"] and "loan_amount" in values:
        loan = values["loan_amount"]
        financing = {
            "loanAmount": format(loan, "f"),
            "loanToBasis": format(loan / known_basis, "f") if known_basis else None,
            "equityRequirementBeforeReserves": format(known_basis - loan, "f"),
            "interestRate": format(values["interest_rate"], "f") if "interest_rate" in values else None,
            "amortizationYears": format(values["amortization_years"], "f") if "amortization_years" in values else None,
            "loanTermYears": format(values["loan_term_years"], "f") if "loan_term_years" in values else None,
            "debtServiceCalculated": False,
        }
    annual_cost_fields = (
        "annual_property_taxes", "annual_insurance", "annual_utilities", "annual_other_operating_costs",
    )
    known_costs = sum((values.get(field, Decimal("0")) for field in annual_cost_fields), Decimal("0"))
    operating = None
    if any(field in values for field in annual_cost_fields):
        gross = Decimal(gross_potential_rent["annual"]) if gross_potential_rent else None
        ratio = known_costs / gross if gross and gross > 0 else None
        operating = {
            "knownAnnualOperatingCosts": format(known_costs, "f"),
            "components": {field: format(values[field], "f") for field in annual_cost_fields if field in values},
            "knownCostsAsPercentOfGrossPotentialRent": format(ratio, "f") if ratio is not None else None,
            "partialBreakEvenOccupancyForKnownCosts": format(ratio, "f") if ratio is not None else None,
            "vacancyRateCandidate": format(values["vacancy_rate"], "f") if "vacancy_rate" in values else None,
            "concessionsRateCandidate": format(values["concessions_rate"], "f") if "concessions_rate" in values else None,
            "completeOperatingStatement": False,
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "evidence": evidence,
        "basis": basis,
        "financingScreen": financing,
        "knownOperatingCostScreen": operating,
        "test2CandidateInputs": {
            "status": "ADVISORY_UNAPPROVED",
            "values": evidence,
            "automaticApply": False,
        },
        "limitations": [
            "Inputs are candidate evidence and require analyst review before underwriting use.",
            "Known-cost break-even excludes any unprovided expenses, capital items, reserves, vacancy, concessions and debt service.",
            "Loan-to-basis and equity requirement are screening arithmetic; debt service, covenants and returns remain Test2 calculations.",
            "No missing economic input is inferred or replaced with zero; incomplete basis and operating evidence remain explicitly incomplete.",
        ],
    }
