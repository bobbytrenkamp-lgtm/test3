from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
import os
from pathlib import Path

from .geography import MarketDefinition, market_definitions, save_market_definition
from .schema import parse_cre_file
from test3.warehouse.storage import WarehousePaths


MARKET_CANDIDATE_SCHEMA = "test3-maa-market-definition-candidates/1.0.0"
MARKET_ATTESTATION_SCHEMA = "test3-maa-market-definition-attestation/1.0.0"
MARKET_DECISIONS = frozenset({"approve", "reject", "modify", "request_further_research"})
MARKET_ACKNOWLEDGEMENTS = (
    "property_evidence_reviewed", "county_fips_reviewed", "weights_reviewed",
    "effective_dates_reviewed", "maa_market_not_cbsa_acknowledged",
)
INVENTORY_COLUMNS = frozenset({
    "market_id", "source_market_name", "property_name", "county_fips", "county_name", "units",
    "inventory_scope", "evidence", "effective_from", "effective_to",
})


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _artifact_hash(payload: dict) -> str:
    body = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    body = json.loads(json.dumps(body))
    if body.get("schema_version") == MARKET_CANDIDATE_SCHEMA:
        body["attestation_template"]["candidate_artifact_sha256"] = ""
    return _hash(body)


def _weights(records: list[dict]) -> tuple[list[dict], str, str] | tuple[None, None, str]:
    if not records:
        return None, None, "no property-level county evidence supplied"
    required = ("property_name", "county_fips", "county_name", "evidence", "effective_from")
    if any(any(not str(item.get(field) or "").strip() for field in required) for item in records):
        return None, None, "property evidence is missing a property, county FIPS/name, evidence, or effective date"
    if any(len(str(item["county_fips"])) != 5 or not str(item["county_fips"]).isdigit() for item in records):
        return None, None, "property evidence contains an invalid county FIPS"
    scopes = {str(item["inventory_scope"]).strip() for item in records}
    units_present = [str(item.get("units") or "").strip() != "" for item in records]
    if all(units_present):
        basis = "same_store_apartment_units" if scopes == {"same_store"} else "property_apartment_units"
        amounts = [Decimal(str(item["units"])) for item in records]
        if any(value <= 0 for value in amounts):
            return None, None, "unit evidence must be positive"
    elif not any(units_present):
        basis, amounts = "property_count", [Decimal("1") for _ in records]
    else:
        return None, None, "mixed unit availability prevents a consistent weighting method"
    county_amounts: dict[tuple[str, str], Decimal] = {}
    for item, amount in zip(records, amounts, strict=True):
        key = (str(item["county_fips"]), str(item["county_name"]).strip())
        county_amounts[key] = county_amounts.get(key, Decimal("0")) + amount
    total = sum(county_amounts.values(), Decimal("0"))
    counties, assigned = [], Decimal("0")
    ordered = sorted(county_amounts.items())
    quantum = Decimal("0.000000000001")
    for index, ((county_fips, county_name), amount) in enumerate(ordered):
        weight = (Decimal("1") - assigned if index == len(ordered) - 1
                  else (amount / total).quantize(quantum, rounding=ROUND_DOWN))
        assigned += weight
        counties.append({"county_fips": county_fips, "county_name": county_name,
                         "weight": format(weight, "f"), "weight_numerator": format(amount, "f"),
                         "weight_denominator": format(total, "f")})
    return counties, basis, ""


def prepare_maa_market_definitions(target_input: str | Path, output_path: str | Path,
                                   property_inventory: str | Path | None = None, *,
                                   source_company: str = "MAA") -> dict:
    target, output = Path(target_input), Path(output_path)
    if output.exists():
        raise FileExistsError("MAA market-definition candidate artifacts are immutable")
    rows, errors, metadata = parse_cre_file(target.read_bytes(), suffix=target.suffix)
    if errors or not rows:
        raise ValueError("target input must contain structurally valid MAA observations")
    inventory_rows: list[dict] = []
    inventory_hash = None
    if property_inventory:
        inventory_path = Path(property_inventory)
        with inventory_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if frozenset(reader.fieldnames or ()) != INVENTORY_COLUMNS:
                raise ValueError("property inventory columns must exactly match the governed schema")
            inventory_rows = list(reader)
        inventory_hash = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    definitions = []
    for market_id in sorted({row["geography_id"] for row in rows}):
        market_rows = [row for row in rows if row["geography_id"] == market_id]
        records = [item for item in inventory_rows if item["market_id"] == market_id]
        dates = {(item.get("effective_from"), item.get("effective_to") or None) for item in records}
        counties, basis, problem = _weights(records)
        if len(dates) > 1:
            counties, basis, problem = None, None, "property evidence spans multiple effective definitions"
        effective_from = (next(iter(dates))[0] if len(dates) == 1 else
                          f"{min(row['period'] for row in market_rows)[:4]}-01-01")
        effective_to = next(iter(dates))[1] if len(dates) == 1 else None
        source_market_names = sorted({row["market"] for row in market_rows})
        evidence = sorted({item["evidence"] for item in records if item.get("evidence")})
        proposal = {
            "source_market_name": source_market_names[0], "source_market_type": f"{source_company}_same_store_portfolio_market",
            "market_id": market_id, "property_type": "multifamily", "definition_version": "1.0.0",
            "effective_from": effective_from, "effective_to": effective_to, "counties": counties or [],
            "weighting_methodology": basis, "evidence": evidence,
            "rationale": (f"Candidate {basis} definition derived from {len(records)} property evidence row(s)."
                          if counties else "Unresolved: source market totals do not establish county composition."),
            "confidence": ("high" if basis == "same_store_apartment_units" else "moderate" if basis else "unresolved"),
            "review_status": "candidate_review_required", "feature_eligible": False,
            "unresolved_reason": problem or None,
        }
        proposal["definition_hash"] = _hash(proposal)
        definitions.append(proposal)
    unknown_inventory = sorted({item["market_id"] for item in inventory_rows} - {item["market_id"] for item in definitions})
    if unknown_inventory:
        raise ValueError(f"property inventory contains unknown MAA markets: {unknown_inventory}")
    payload = {
        "schema_version": MARKET_CANDIDATE_SCHEMA, "authoritative": False,
        "target_dataset_sha256": metadata["sha256"], "property_inventory_sha256": inventory_hash,
        "source_limitations": [
            f"{source_company} source-market names and aggregate market units do not establish county boundaries.",
            "Current public community listings are not proof of historical same-store composition.",
            "A definition remains unresolved without property-level county evidence and a consistent weighting basis.",
        ],
        "definitions": definitions,
        "attestation_template": {
            "schema_version": MARKET_ATTESTATION_SCHEMA, "candidate_artifact_sha256": "",
            "analyst_identity": "", "analyst_signature": "", "signed_at": "", "rationale": "",
            "decisions": [{"market_id": item["market_id"], "definition_hash": item["definition_hash"],
                           "decision": "", "rationale": ""} for item in definitions],
            "acknowledgements": {name: False for name in MARKET_ACKNOWLEDGEMENTS},
        },
    }
    payload["artifact_sha256"] = _artifact_hash(payload)
    payload["attestation_template"]["candidate_artifact_sha256"] = payload["artifact_sha256"]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return {"candidate_artifact": str(output), "markets": len(definitions),
            "candidate_definitions": sum(bool(item["counties"]) for item in definitions),
            "unresolved_definitions": sum(not item["counties"] for item in definitions),
            "status": "AWAITING_MARKET_DEFINITION_APPROVAL"}


def _intervals_overlap(left: dict, right: dict) -> bool:
    left_start, right_start = date.fromisoformat(left["effective_from"]), date.fromisoformat(right["effective_from"])
    left_end = date.max if not left.get("effective_to") else date.fromisoformat(left["effective_to"])
    right_end = date.max if not right.get("effective_to") else date.fromisoformat(right["effective_to"])
    return max(left_start, right_start) <= min(left_end, right_end)


def approve_maa_market_definitions(paths: WarehousePaths, candidate_path: str | Path,
                                   attestation_path: str | Path, decision_output: str | Path) -> dict:
    candidate_file, attestation_file, output = Path(candidate_path), Path(attestation_path), Path(decision_output)
    if output.exists():
        raise FileExistsError("market-definition decision artifacts are immutable")
    payload = json.loads(candidate_file.read_text(encoding="utf-8"))
    stored_hash = payload.get("artifact_sha256")
    if payload.get("schema_version") != MARKET_CANDIDATE_SCHEMA or stored_hash != _artifact_hash(payload):
        raise ValueError("market-definition candidate integrity failure")
    attestation = json.loads(attestation_file.read_text(encoding="utf-8"))
    if attestation.get("schema_version") != MARKET_ATTESTATION_SCHEMA or attestation.get("candidate_artifact_sha256") != stored_hash:
        raise ValueError("market-definition attestation is not bound to the candidate artifact")
    for field in ("analyst_identity", "analyst_signature", "signed_at", "rationale", "decisions"):
        if attestation.get(field) in (None, "", []):
            raise ValueError(f"market-definition attestation requires {field}")
    signed_at = datetime.fromisoformat(str(attestation["signed_at"]).replace("Z", "+00:00"))
    if signed_at.tzinfo is None:
        raise ValueError("market-definition signed_at must include a timezone")
    missing = [name for name in MARKET_ACKNOWLEDGEMENTS if (attestation.get("acknowledgements") or {}).get(name) is not True]
    if missing:
        raise ValueError(f"market-definition acknowledgements are incomplete: {missing}")
    proposals = {item["market_id"]: item for item in payload["definitions"]}
    decisions = attestation["decisions"]
    if len(decisions) != len(proposals) or {item.get("market_id") for item in decisions} != set(proposals):
        raise ValueError("every candidate market requires exactly one decision")
    existing = market_definitions(paths)
    saved, decision_rows = [], []
    for decision in decisions:
        proposal = proposals[decision["market_id"]]
        if decision.get("definition_hash") != proposal["definition_hash"] or decision.get("decision") not in MARKET_DECISIONS:
            raise ValueError("market decision is invalid or bound to a different definition")
        if len(str(decision.get("rationale") or "").strip()) < 10:
            raise ValueError("every market decision requires a rationale")
        if decision["decision"] == "approve":
            if not proposal["counties"] or proposal["unresolved_reason"]:
                raise ValueError(f"unresolved market cannot be approved: {proposal['market_id']}")
            if any(item["market_id"] == proposal["market_id"] and item.get("review_status") == "analyst_approved"
                   and _intervals_overlap(item, proposal) for item in existing):
                raise ValueError(f"approved market definition overlaps an existing effective definition: {proposal['market_id']}")
            definition = MarketDefinition(
                market_id=proposal["market_id"], market_name=proposal["source_market_name"],
                property_type="multifamily", source_definition="; ".join(proposal["evidence"]),
                effective_from=proposal["effective_from"], effective_to=proposal["effective_to"],
                counties=tuple(proposal["counties"]), source_market_name=proposal["source_market_name"],
                definition_version=proposal["definition_version"], weighting_methodology=proposal["weighting_methodology"],
                analyst_rationale=f"{attestation['rationale']} | {decision['rationale']}",
                source_evidence="; ".join(proposal["evidence"]), review_status="analyst_approved",
            )
            saved.append(str(save_market_definition(paths, definition)))
        decision_rows.append({"market_id": proposal["market_id"], "definition_hash": proposal["definition_hash"],
                              "decision": decision["decision"], "rationale": decision["rationale"]})
    result = {"schema_version": "test3-maa-market-definition-decisions/1.0.0",
              "candidate_artifact_sha256": stored_hash,
              "attestation_sha256": hashlib.sha256(attestation_file.read_bytes()).hexdigest(),
              "decisions": decision_rows, "approved_definition_paths": saved}
    result["artifact_sha256"] = _artifact_hash(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return {"status": "MARKET_DEFINITION_DECISIONS_RECORDED", "approved": len(saved),
            "unapproved": len(decision_rows) - len(saved), "decision_artifact": str(output)}
