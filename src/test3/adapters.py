from __future__ import annotations

from datetime import datetime, timezone


def test2_export(deal: dict, approved: list[dict], findings: list[dict], compatibility_version: str = "test2-0.1") -> dict:
    values = {item["field_name"]: item.get("normalized_value") for item in approved if item.get("review_status") == "approved"}
    hashes = sorted({item.get("document_sha256") for item in approved if item.get("document_sha256")})
    warnings = []
    if not values.get("property_name"):
        warnings.append("Approved property_name is missing")
    return {
        "schemaVersion": "test3-to-test2/1.0",
        "exportVersion": "1.0.0",
        "test2CompatibilityVersion": compatibility_version,
        "sourceDealId": deal["id"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDocumentHashes": hashes,
        "approvalTimestamps": sorted({item.get("reviewed_at") for item in approved if item.get("reviewed_at")}),
        "unresolvedFindings": [item for item in findings if item.get("resolution_status") != "resolved"],
        "mappingDiagnostics": {"approvedFieldCount": len(values), "warnings": warnings},
        "property": {"name": values.get("property_name"), "address": values.get("address"), "propertyType": deal.get("property_type"), "rentableArea": values.get("rentable_square_feet"), "unitCount": values.get("unit_count")},
        "buildings": [], "spaces": [], "tenants": [], "leases": [], "rentSteps": [], "escalations": [], "recoveries": [],
        "marketLeasingAssumptions": [], "operatingExpenses": [], "capitalAssumptions": [], "debtFacilities": [],
        "acquisitionAssumptions": {"purchasePrice": values.get("asking_price")},
        "supportingSources": [{"documentId": item["document_id"], "sha256": item.get("document_sha256"), "page": item.get("page_number"), "field": item["field_name"]} for item in approved if item.get("review_status") == "approved"],
        "importWarnings": warnings,
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
    facts = [{"statement": f"{item['field_name'].replace('_', ' ').title()}: {item.get('normalized_value')}", "source": {"documentId": item["document_id"], "page": item.get("page_number"), "excerptHash": item.get("source_text_hash")}} for item in approved if item.get("review_status") == "approved"]
    return {"title": f"DRAFT — {deal['name']} diligence summary", "draft": True, "legalNotice": "Diligence support only; lease and legal items require qualified review.", "executiveSummary": "This draft includes approved facts only. Missing information is not inferred.", "approvedFacts": facts, "keyDiscrepancies": findings, "sourceAppendix": [fact["source"] for fact in facts]}

