from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

from .test1_snapshot import enrich as enrich_test1_snapshot


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
    return enrich_test1_snapshot(address, local_snapshot)


def diligence_summary(deal: dict, approved: list[dict], findings: list[dict], documents: list[dict] | None = None, all_values: list[dict] | None = None) -> dict:
    documents, all_values = documents or [], all_values or approved
    documents_by_name = {item["original_name"]: item for item in documents}
    documents_by_id = {item["id"]: item for item in documents}

    def source(item: dict) -> dict:
        document_id = item.get("document_id")
        return {
            "sourceType": item.get("source_kind", "document"), "documentId": document_id,
            "documentVersion": item.get("document_version"), "page": item.get("page_number"),
            "excerptHash": item.get("source_text_hash"),
            "sourceUrl": f"/api/documents/{document_id}/page/{item.get('page_number')}" if document_id and item.get("page_number") and documents_by_id.get(document_id, {}).get("detected_mime") == "application/pdf" else (f"/api/documents/{document_id}" if document_id else None),
            **({"rationale": item.get("rationale") or item.get("source_excerpt")} if not document_id else {}),
        }

    facts = [
        {"field": item["field_name"], "statement": f"{item['field_name'].replace('_', ' ').title()}: {item.get('normalized_value')}", "sourceRefs": [source(item)]}
        for item in approved if item.get("review_status") == "approved"
    ]
    by_field = {item["field"]: item for item in facts}

    def fact_section(section_id: str, title: str, fields: tuple[str, ...]) -> dict:
        items = [by_field[field] for field in fields if field in by_field]
        return {"id": section_id, "title": title, "status": "supported" if items else "missing", "items": items, "note": None if items else "No approved source-backed facts are available for this section."}

    received = [{"statement": f"{item['original_name']} ({item['category']}, {item['processing_status']})", "sourceRefs": [{"sourceType": "document", "documentId": item["id"], "documentVersion": 1, "page": None, "excerptHash": None, "sourceUrl": None if item.get("original_purged_at") else f"/api/documents/{item['id']}"}]} for item in documents]
    required_sources = {"offering_memorandum": "Offering memorandum", "rent_roll": "Rent roll", "t12_operating_statement": "T-12 operating statement"}
    received_categories = {item.get("category") for item in documents}
    missing_sources = [{"statement": f"{label}: not received", "sourceRefs": []} for category, label in required_sources.items() if category not in received_categories]
    open_findings = [item for item in findings if item.get("resolution_status", "open") == "open"]
    discrepancy_items = [{"statement": item["explanation"], "severity": item.get("severity"), "ruleCode": item.get("rule_code"), "sourceRefs": [{"sourceType": "document_reference", "documentName": name, "documentId": documents_by_name.get(name, {}).get("id"), "page": page, "sourceUrl": (f"/api/documents/{documents_by_name[name]['id']}/page/{page}" if name in documents_by_name and page and documents_by_name[name].get("detected_mime") == "application/pdf" else (f"/api/documents/{documents_by_name[name]['id']}" if name in documents_by_name else None))} for name in item.get("source_documents", []) for page in (item.get("page_references") or [None])]} for item in open_findings]
    unverified = [{"statement": f"{item['field_name'].replace('_', ' ').title()}: {item.get('review_status', 'needs_review').replace('_', ' ')}; excluded from approved facts.", "sourceRefs": [source(item)]} for item in all_values if item.get("review_status") != "approved"]
    questions = [{"statement": f"Resolve {item.get('rule_code', 'discrepancy')}: {item.get('suggested_next_step') or 'Review controlling sources.'}", "sourceRefs": []} for item in open_findings]
    questions.extend({"statement": f"Obtain and review the missing {item['statement'].split(':', 1)[0].lower()}.", "sourceRefs": []} for item in missing_sources)
    risks = [{"statement": item["explanation"], "severity": item.get("severity"), "sourceRefs": []} for item in open_findings if item.get("severity") in ("high", "medium")]
    mitigants = [{"statement": f"Potential review step (not an established mitigant): {item.get('suggested_next_step')}", "sourceRefs": []} for item in open_findings if item.get("suggested_next_step")]
    appendix_by_key = {}
    for sourced_item in [*facts, *received, *discrepancy_items]:
        for ref in sourced_item["sourceRefs"]:
            key = (ref.get("sourceType"), ref.get("documentId"), ref.get("page"), ref.get("excerptHash"), ref.get("rationale"))
            appendix_by_key[key] = ref
    appendix = list(appendix_by_key.values())
    sections = [
        {"id": "executiveSummary", "title": "Executive summary", "status": "supported" if facts else "missing", "items": [{"statement": f"This draft contains {len(facts)} approved source-backed fact(s) and {len(open_findings)} open discrepancy finding(s). Missing information is not inferred.", "sourceRefs": []}]},
        fact_section("propertyOverview", "Property overview", ("property_name", "address", "year_built", "rentable_square_feet", "unit_count", "occupancy")),
        {"id": "sourcesReceived", "title": "Sources received", "status": "supported" if received else "missing", "items": received, "note": None if received else "No diligence documents have been received."},
        {"id": "sourcesMissing", "title": "Sources missing", "status": "supported" if missing_sources else "not_applicable", "items": missing_sources, "note": "Compared with the first-usable-release OM, rent roll and T-12 set."},
        fact_section("purchaseAssumptions", "Purchase assumptions", ("asking_price", "loi_price", "psa_price", "broker_stated_cap_rate")),
        fact_section("historicalOperations", "Historical operations", ("historical_noi", "operating_rental_revenue", "gross_revenue", "operating_expenses", "reported_noi")),
        fact_section("proFormaAssumptions", "Pro forma assumptions", ("pro_forma_noi", "forecast_start_date", "forecast_months", "discount_rate")),
        fact_section("tenantUnitSummary", "Tenant or unit summary", ("tenant_name", "suite", "unit_count", "rent_roll_unit_count", "rent_roll_occupied_area")),
        fact_section("leaseRollover", "Lease rollover", ("lease_commencement_date", "lease_expiration_date", "rent_roll_expiration", "lease_current_rent", "rent_roll_current_rent")),
        fact_section("debtTerms", "Debt terms", ("loan_amount", "interest_rate", "loan_spread", "loan_term_months", "amortization_months", "interest_only_months", "stated_ltv", "stated_ltc", "minimum_dscr")),
        {"id": "keyDiscrepancies", "title": "Key discrepancies", "status": "open" if discrepancy_items else "none_identified", "items": discrepancy_items},
        {"id": "materialDiligenceQuestions", "title": "Material diligence questions", "status": "open" if questions else "none_identified", "items": questions},
        fact_section("locationJurisdictionContext", "Location and jurisdiction context", ("address", "county_fips", "state", "municipality", "parcel_id")),
        {"id": "majorRisks", "title": "Major risks", "status": "open" if risks else "none_identified", "items": risks, "note": "Only unresolved deterministic findings are listed; no broader risk conclusion is inferred."},
        {"id": "potentialMitigants", "title": "Potential mitigants", "status": "review_required" if mitigants else "missing", "items": mitigants, "note": "These are review steps, not verified mitigants or recommendations."},
        {"id": "approvedFacts", "title": "Approved facts", "status": "supported" if facts else "missing", "items": facts},
        {"id": "unverifiedStatements", "title": "Unverified statements", "status": "review_required" if unverified else "none_identified", "items": unverified, "note": "Pending, rejected and superseded values are excluded from factual sections."},
        {"id": "sourceAppendix", "title": "Source appendix", "status": "supported" if appendix else "missing", "items": [{"statement": f"Source {index + 1}", "sourceRefs": [ref]} for index, ref in enumerate(appendix)]},
    ]
    return {
        "schemaVersion": "test3-ic-memo/2.0", "title": f"DRAFT — {deal['name']} diligence summary", "draft": True,
        "legalNotice": "Diligence support only; this is not investment, legal or accounting advice. Lease and legal items require qualified review.",
        "executiveSummary": sections[0]["items"][0]["statement"], "sections": sections,
        "approvedFacts": facts, "keyDiscrepancies": discrepancy_items, "sourceAppendix": appendix,
    }
