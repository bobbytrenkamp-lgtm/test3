from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5


TEST2_PROPERTY_TYPES = frozenset(
    {
        "office", "industrial", "retail", "multifamily", "mixed_use",
        "student_housing", "self_storage", "medical_office", "life_science",
        "data_center", "hotel", "senior_housing", "manufactured_housing",
        "parking", "land", "ground_lease",
    }
)
TEST2_REQUIRED_APPROVED_FIELDS = (
    "property_name", "forecast_start_date", "forecast_months", "discount_rate"
)


def _approved_values(approved: list[dict]) -> dict[str, object]:
    """Return only reviewer-approved values; later duplicate fields win deterministically."""
    return {
        item["field_name"]: item.get("normalized_value")
        for item in approved
        if item.get("review_status") == "approved"
    }


def _stable_id(deal_id: str, suffix: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"test3:{deal_id}:{suffix}"))


def _test2_model(deal: dict, values: dict[str, object]) -> tuple[dict | None, list[str]]:
    missing = [name for name in TEST2_REQUIRED_APPROVED_FIELDS if values.get(name) in (None, "")]
    errors: list[str] = []
    property_type = deal.get("property_type")
    if property_type not in TEST2_PROPERTY_TYPES:
        errors.append("deal.property_type is not a supported test2 property type")

    months: int | None = None
    if "forecast_months" not in missing:
        try:
            months = int(str(values["forecast_months"]))
            if not 1 <= months <= 600:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("approved forecast_months must be an integer from 1 through 600")

    discount_rate: str | None = None
    if "discount_rate" not in missing:
        try:
            rate = Decimal(str(values["discount_rate"]))
            if not Decimal("0") <= rate <= Decimal("1"):
                raise ValueError
            discount_rate = format(rate, "f")
        except (InvalidOperation, TypeError, ValueError):
            errors.append("approved discount_rate must be a decimal fraction from 0 through 1")

    start_date = str(values.get("forecast_start_date", ""))
    if "forecast_start_date" not in missing:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            errors.append("approved forecast_start_date must use YYYY-MM-DD")

    rentable_area = values.get("rentable_square_feet")
    unit_count = values.get("unit_count")
    if unit_count not in (None, ""):
        try:
            unit_count = int(str(unit_count))
            if unit_count < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("approved unit_count must be a non-negative integer")

    if rentable_area not in (None, ""):
        try:
            rentable_area = format(Decimal(str(rentable_area)), "f")
        except (InvalidOperation, TypeError):
            errors.append("approved rentable_square_feet must be decimal-compatible")

    if missing or errors:
        return None, [*(f"missing approved {name}" for name in missing), *errors]

    deal_id = str(deal["id"])
    acquisition_price = values.get("asking_price")
    valuation: dict[str, object] = {"discountRate": discount_rate}
    if acquisition_price not in (None, ""):
        try:
            valuation["acquisitionPrice"] = format(Decimal(str(acquisition_price)), "f")
        except (InvalidOperation, TypeError):
            errors.append("approved asking_price must be decimal-compatible")
            return None, errors

    return {
        "modelId": _stable_id(deal_id, "model"),
        "modelName": str(values["property_name"]),
        "currency": "USD",
        "areaUnit": "sqft",
        "forecast": {"startDate": start_date, "months": months},
        "property": {
            "id": _stable_id(deal_id, "property"),
            "name": str(values["property_name"]),
            "propertyType": property_type,
            **({"rentableArea": rentable_area} if rentable_area not in (None, "") else {}),
            **({"unitCount": unit_count} if unit_count not in (None, "") else {}),
        },
        "growthCurves": [], "spaces": [], "tenants": [], "leases": [],
        "marketLeasingProfiles": [], "otherRevenue": [], "expenses": [],
        "capital": [], "debt": [], "valuation": valuation,
    }, []


def test2_export(
    deal: dict,
    approved: list[dict],
    findings: list[dict],
    compatibility_version: str = "0.1.0",
) -> dict:
    values = _approved_values(approved)
    hashes = sorted({item.get("document_sha256") for item in approved if item.get("review_status") == "approved" and item.get("document_sha256")})
    model, blockers = _test2_model(deal, values)
    generated_at = datetime.now(timezone.utc).isoformat()
    portable = None
    if model is not None:
        portable = {
            "format": "cre-platform-model",
            "formatVersion": 1,
            "exportedAt": generated_at,
            "engineVersion": compatibility_version,
            "model": model,
        }
    return {
        "schemaVersion": "test3-underwriting-package/2.0",
        "exportVersion": "2.0.0",
        "test2CompatibilityVersion": compatibility_version,
        "sourceDealId": deal["id"],
        "generatedAt": generated_at,
        "sourceDocumentHashes": hashes,
        "approvalTimestamps": sorted({item.get("reviewed_at") for item in approved if item.get("review_status") == "approved" and item.get("reviewed_at")}),
        "unresolvedFindings": [item for item in findings if item.get("resolution_status") != "resolved"],
        "mappingDiagnostics": {
            "approvedFieldCount": len(values),
            "importReady": portable is not None,
            "blockers": blockers,
        },
        "test2PortableModel": portable,
        "supportingSources": [
            {
                "sourceType": item.get("source_kind", "document"),
                "documentId": item.get("document_id"),
                "sha256": item.get("document_sha256"),
                "page": item.get("page_number"), "field": item["field_name"],
                **({"rationale": item.get("rationale") or item.get("source_excerpt")} if item.get("source_kind") == "user_entered" else {}),
            }
            for item in approved if item.get("review_status") == "approved"
        ],
    }


def test1_enrichment(address: dict, local_snapshot: dict | None = None) -> dict:
    if not local_snapshot:
        return {"status": "unavailable", "verified": False, "coverage": "missing", "message": "No local test1 snapshot was configured; deal workflow remains available.", "inputs": address, "results": {}}
    key = address.get("county_fips")
    result = local_snapshot.get(str(key)) if key else None
    if result is None:
        return {"status": "no_match", "verified": False, "coverage": "incomplete", "inputs": address, "results": {}}
    return {"status": "matched", "verified": bool(result.get("verified")), "coverage": result.get("coverage", "sample"), "inputs": address, "results": result}


def diligence_summary(deal: dict, approved: list[dict], findings: list[dict]) -> dict:
    facts = [{"statement": f"{item['field_name'].replace('_', ' ').title()}: {item.get('normalized_value')}", "source": {"sourceType": item.get("source_kind", "document"), "documentId": item.get("document_id"), "page": item.get("page_number"), "excerptHash": item.get("source_text_hash")}} for item in approved if item.get("review_status") == "approved"]
    return {"title": f"DRAFT — {deal['name']} diligence summary", "draft": True, "legalNotice": "Diligence support only; lease and legal items require qualified review.", "executiveSummary": "This draft includes approved facts only. Missing information is not inferred.", "approvedFacts": facts, "keyDiscrepancies": findings, "sourceAppendix": [fact["source"] for fact in facts]}
