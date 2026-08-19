"""Phase 6: MarketSignal -> Underwrite handoff (export side).

Builds a real ``creos-handoff-v1`` payload from one assumption run — this
app's candidate market-forecast recommendation for a single deal — for a
human at CREOS Underwrite to review. Mirrors test1 (SiteIntel)'s
``js/parcel/handoff.js``, the Phase 5 precedent for this same contract;
see that file's header comment for the sibling design rationale. The
authoritative schema lives in the CREOS Enterprise repository
(``src/domain/handoff.ts``, ``assumption.ts``, ``property.ts``) — no
shared package exists between these independently deployed applications,
so this module is a hand-written producer, not a generated client.

Translation-layer decisions, each real and each worth stating explicitly
rather than leaving implicit:

1. ``market`` (not ``property``) is what test4's own design doc says a
   MarketSignal handoff should carry. This module deliberately does NOT
   populate it. A CREOS ``Market`` record needs a *stable* ``marketId``
   that means the same real-world market on every export — this app has
   no persistent per-market identity (deals aren't linked to a
   ``MarketDefinition`` record, and ``market_observations``' geography
   fields are too granular/inconsistent to safely collapse into one).
   Minting a fresh random ULID on every export would misrepresent
   identity continuity that doesn't actually exist here, which is a form
   of fabrication this project doesn't accept even implicitly.
2. ``property`` IS populated, and that's a different case: it's fine (and
   is exactly what test1's SiteIntel handoff already does) to mint a
   fresh ``propertyId`` the first time a specific deal's property crosses
   this boundary — a deal's ``name`` is real, stable, non-fabricated
   context, unlike a market-wide identity this app doesn't actually
   track. No structured ``identity.address`` for the same reason Phase 5
   omitted one: this app only has a single-line address, never a
   decomposed city/state/postal code.
3. Every assumption is ``sourceType: 'modeled'``, never ``'observed'`` —
   an assumption run is an algorithmic recommendation (a documented
   method + fallback hierarchy over market observations), not a raw
   fact this app read directly. ``status`` is always ``'proposed'``,
   regardless of whether this specific run has already been decided
   *inside* test3 for test3's own purposes — that decision does not
   carry over to a different deal's model in a different application;
   Underwrite's own analyst makes that call after ingestion, same rule
   Phase 5 enforced for SiteIntel.
4. ``category`` carries the exact catalog name (``vacancy``,
   ``exit_cap_rate``, ...) from ``assumptions/catalog.py``'s
   ``ASSUMPTION_CATALOG`` — not a human label — specifically so a
   receiving translator can match against it exactly rather than parsing
   prose. ``name`` carries the human-readable label for display.
5. test3's own confidence vocabulary (``high``/``moderate``/``low``/
   ``unavailable``) is mapped onto CREOS's (``low``/``medium``/``high``/
   ``verified``) via a fixed table; ``unavailable`` omits the field
   rather than guessing a CREOS tier.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .creos_ids import generate_creos_ulid

SCHEMA_VERSION = "creos-handoff-v1"

_CONFIDENCE_MAP = {"high": "high", "moderate": "medium", "low": "low", "unavailable": None}

# CREOS Property.classification.propertyType's real enum (src/domain/property.ts).
# A deal's own property_type is free text; only map it across when it's an exact
# match, otherwise carry the real value in `subtype` rather than dropping it or
# guessing a category the deal never actually stated.
_PROPERTY_TYPES = {"office", "industrial", "multifamily", "retail", "data_center", "hospitality", "land", "other"}


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _map_confidence(value: str | None) -> str | None:
    if not value:
        return None
    return _CONFIDENCE_MAP.get(value)


def _numeric_or_string(raw: object) -> tuple[str, object]:
    if raw is None:
        return "string", None
    try:
        return "number", float(raw)
    except (TypeError, ValueError):
        return "string", str(raw)


def _property_from_deal(deal: dict) -> dict:
    property_type_raw = (deal.get("property_type") or "").strip()
    normalized = property_type_raw.lower().replace(" ", "_")
    classification: dict = {}
    if normalized in _PROPERTY_TYPES:
        classification["propertyType"] = normalized
    elif property_type_raw:
        classification["propertyType"] = "other"
        classification["subtype"] = property_type_raw

    property_payload: dict = {
        "identity": {
            "propertyId": generate_creos_ulid(),
            "propertyName": deal.get("name") or "Unnamed deal",
        },
    }
    if classification:
        property_payload["classification"] = classification
    return property_payload


def build_assumption_run_handoff(*, run: dict, deal: dict, catalog_spec, now: str | None = None) -> dict:
    """Builds a creos-handoff-v1 payload for a single assumption run.

    Pure function: no I/O, no ID lookups beyond generating fresh ULIDs, so
    it's directly unit-testable (see tests/test_creos_handoff.py) without a
    database. Raises ValueError if the run has no base_recommendation to
    send -- a handoff with no actual value would be pointless, not merely
    incomplete.
    """
    ts = now or _now_iso()

    value_type, value = _numeric_or_string(run.get("base_recommendation"))
    if value is None:
        raise ValueError("build_assumption_run_handoff: run has no base_recommendation to send")

    methodology_parts = [
        f"MarketSignal candidate recommendation (method: {run.get('method') or 'unavailable'}, "
        f"fallback level: {run.get('fallback_level') or 'unavailable'}).",
    ]
    rationale = (run.get("rationale") or "").strip()
    if rationale:
        methodology_parts.append(rationale)
    low, high = run.get("low_recommendation"), run.get("high_recommendation")
    if low is not None or high is not None:
        methodology_parts.append(
            f"Range considered: low {low if low is not None else 'n/a'}, high {high if high is not None else 'n/a'}."
        )
    limitations = run.get("limitations") or []
    if limitations:
        methodology_parts.append("Limitations: " + "; ".join(str(item) for item in limitations))
    methodology = " ".join(part for part in methodology_parts if part)

    assumption: dict = {
        "assumptionId": generate_creos_ulid(),
        "name": catalog_spec.label,
        "category": catalog_spec.name,
        "valueType": value_type,
        "value": value,
        "sourceType": "modeled",
        "sourceModule": "marketsignal",
        "status": "proposed",
        "createdAt": ts,
        "updatedAt": ts,
    }
    if catalog_spec.unit:
        assumption["unit"] = catalog_spec.unit
    confidence = _map_confidence(run.get("confidence"))
    if confidence:
        assumption["confidence"] = confidence
    if methodology:
        assumption["methodology"] = methodology

    return {
        "schemaVersion": SCHEMA_VERSION,
        "handoffId": generate_creos_ulid(),
        "createdAt": ts,
        "sourceModule": "marketsignal",
        "targetModule": "underwrite",
        "sourceApplicationVersion": "test3-marketsignal",
        "property": _property_from_deal(deal),
        "assumptions": [assumption],
        "observations": [],
        "provenance": [],
        "sources": [],
    }
