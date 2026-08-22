"""Tests for test3.creos_handoff (Phase 6: MarketSignal -> Underwrite
handoff export — see that module's docstring for the design decisions
this exercises).

Uses stdlib unittest (not pytest) to match this repository's actual CI
invocation (`python -m unittest discover -s tests`, see
.github/workflows/ci.yml) — pytest is not an installed dependency here.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test3.assumptions.catalog import BY_NAME
from test3.creos_handoff import SCHEMA_VERSION, build_assumption_run_handoff
from test3.creos_ids import is_valid_creos_ulid
from test3.service import Service

NOW = "2026-08-19T12:00:00.000Z"

# Same fixture panel used by tests/test_assumption_intelligence.py's
# end-to-end test -- reused here rather than reinvented, since it's
# already a real, valid market panel this app's own pipeline accepts.
PANEL = b"""period,market_id,market_name,property_type,source,source_date,source_reference,usage_rights,county_fips,state_fips,rent_growth_12m,expense_growth,property_tax_growth,insurance_growth,vacancy_rate,effective_rent,renewal_probability,downtime_months,tenant_improvements,leasing_commission_rate,transaction_cap_rate,discount_rate,debt_interest_rate,construction_cost_growth,lease_up_units_per_month,lease_comp_count
2025-01-01,BAL,Baltimore,office,Analyst panel,2025-02-01,local://panel,Internal use,24510,24,0.025,0.030,0.040,0.060,0.12,31.0,0.65,9,45,0.05,0.065,0.09,0.06,0.04,2,12
2025-04-01,BAL,Baltimore,office,Analyst panel,2025-05-01,local://panel,Internal use,24510,24,0.030,0.035,0.045,0.070,0.11,32.0,0.67,8,47,0.05,0.067,0.095,0.062,0.045,2.2,14
2025-07-01,BAL,Baltimore,office,Analyst panel,2025-08-01,local://panel,Internal use,24510,24,0.035,0.040,0.050,0.080,0.10,33.0,0.70,7,50,0.055,0.070,0.10,0.065,0.05,2.5,16
"""


def fixture_run(**overrides) -> dict:
    run = {
        "id": "run-1",
        "deal_id": "deal-1",
        "assumption_type": "vacancy",
        "low_recommendation": "0.06",
        "base_recommendation": "0.08",
        "high_recommendation": "0.11",
        "confidence": "moderate",
        "method": "hierarchical_fallback",
        "fallback_level": "market_panel",
        "rationale": "Derived from 14 verified market observations within the submarket.",
        "sample_count": 14,
        "data_window": "2024-01 to 2026-06",
        "limitations": ["Sample size below the high-confidence threshold."],
    }
    run.update(overrides)
    return run


def fixture_deal(**overrides) -> dict:
    deal = {"id": "deal-1", "name": "Riverside Industrial Portfolio", "address": "1200 Dock St", "property_type": "industrial"}
    deal.update(overrides)
    return deal


class BuildAssumptionRunHandoffTests(unittest.TestCase):
    def test_schema_version_and_module_identity(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(payload["sourceModule"], "marketsignal")
        self.assertEqual(payload["targetModule"], "underwrite")
        self.assertTrue(is_valid_creos_ulid(payload["handoffId"]))

    def test_property_identity_minted_from_deal_name_no_structured_address(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertTrue(is_valid_creos_ulid(payload["property"]["identity"]["propertyId"]))
        self.assertEqual(payload["property"]["identity"]["propertyName"], "Riverside Industrial Portfolio")
        self.assertNotIn("address", payload["property"]["identity"])

    def test_property_type_maps_when_recognized(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(property_type="industrial"), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["property"]["classification"]["propertyType"], "industrial")
        self.assertNotIn("subtype", payload["property"]["classification"])

    def test_property_type_falls_back_to_other_with_subtype_when_unrecognized(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(property_type="cold storage"), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["property"]["classification"]["propertyType"], "other")
        self.assertEqual(payload["property"]["classification"]["subtype"], "cold storage")

    def test_no_market_object_is_ever_sent(self):
        # See creos_handoff.py's module docstring decision #1: this app has
        # no stable per-market identity, and fabricating one would
        # misrepresent identity continuity that doesn't exist.
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertNotIn("market", payload)

    def test_assumption_uses_base_recommendation_as_the_value(self):
        payload = build_assumption_run_handoff(run=fixture_run(base_recommendation="0.085"), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        assumption = payload["assumptions"][0]
        self.assertEqual(assumption["valueType"], "number")
        self.assertAlmostEqual(assumption["value"], 0.085)

    def test_assumption_name_is_human_label_category_is_canonical_catalog_key(self):
        payload = build_assumption_run_handoff(run=fixture_run(assumption_type="exit_cap_rate"), deal=fixture_deal(), catalog_spec=BY_NAME["exit_cap_rate"], now=NOW)
        assumption = payload["assumptions"][0]
        self.assertEqual(assumption["name"], "Exit capitalization rate")
        self.assertEqual(assumption["category"], "exit_cap_rate")

    def test_assumption_source_type_is_always_modeled(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["assumptions"][0]["sourceType"], "modeled")

    def test_assumption_status_is_always_proposed_regardless_of_this_apps_own_decision_state(self):
        # No "decided" flag exists on a raw assumption_runs row in this
        # app's own schema (decisions live in a separate table) -- this
        # test documents that build_assumption_run_handoff doesn't accept
        # or need one: the governance rule always forces 'proposed'.
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["assumptions"][0]["status"], "proposed")

    def test_builder_defaults_observations_provenance_and_sources_to_empty(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["observations"], [])
        self.assertEqual(payload["provenance"], [])
        self.assertEqual(payload["sources"], [])

    def test_assumption_id_is_a_valid_creos_ulid(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertTrue(is_valid_creos_ulid(payload["assumptions"][0]["assumptionId"]))

    def test_confidence_mapping_table(self):
        cases = {"high": "high", "moderate": "medium", "low": "low", "unavailable": None}
        for source, expected in cases.items():
            payload = build_assumption_run_handoff(run=fixture_run(confidence=source), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
            assumption = payload["assumptions"][0]
            if expected is None:
                self.assertNotIn("confidence", assumption, f"confidence={source!r} should be omitted, not fabricated")
            else:
                self.assertEqual(assumption["confidence"], expected)

    def test_methodology_preserves_rationale_range_and_limitations(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        methodology = payload["assumptions"][0]["methodology"]
        self.assertIn("hierarchical_fallback", methodology)
        self.assertIn("14 verified market observations", methodology)
        self.assertIn("low 0.06", methodology)
        self.assertIn("high 0.11", methodology)
        self.assertIn("Sample size below the high-confidence threshold.", methodology)

    def test_unit_passed_through_from_catalog_spec(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        self.assertEqual(payload["assumptions"][0]["unit"], BY_NAME["vacancy"].unit)

    def test_raises_without_a_base_recommendation(self):
        with self.assertRaises(ValueError):
            build_assumption_run_handoff(run=fixture_run(base_recommendation=None), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)

    def test_non_numeric_base_recommendation_is_sent_as_a_string_not_dropped(self):
        payload = build_assumption_run_handoff(run=fixture_run(base_recommendation="see rationale"), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"], now=NOW)
        assumption = payload["assumptions"][0]
        self.assertEqual(assumption["valueType"], "string")
        self.assertEqual(assumption["value"], "see rationale")

    def test_payload_is_json_serializable(self):
        payload = build_assumption_run_handoff(run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["exit_cap_rate"], now=NOW)
        json.dumps(payload)  # must not raise

    def test_rejects_dangling_provenance_reference(self):
        with self.assertRaisesRegex(ValueError, "provenance is missing"):
            build_assumption_run_handoff(
                run=fixture_run(), deal=fixture_deal(), catalog_spec=BY_NAME["vacancy"],
                now=NOW, provenance_id="01K36BRRY0HX5Z7861K7QX47M9",
            )

    def test_every_catalog_entry_produces_a_valid_handoff(self):
        # All 15 assumption types in the catalog, not just the ones with a
        # direct real underwriting target -- this export doesn't know or
        # care which of its own facts the receiving side will treat as a
        # real target vs. informational-only (that decision belongs to the
        # receiver, per creos_handoff.py's module docstring decision #4).
        for name, spec in BY_NAME.items():
            with self.subTest(assumption_type=name):
                payload = build_assumption_run_handoff(run=fixture_run(assumption_type=name), deal=fixture_deal(), catalog_spec=spec, now=NOW)
                self.assertEqual(len(payload["assumptions"]), 1)
                self.assertEqual(payload["assumptions"][0]["category"], name)


class AssumptionRunHandoffServiceIntegrationTests(unittest.TestCase):
    """End to end through the real Service/DB layer, not just the pure
    builder -- mirrors tests/test_assumption_intelligence.py's own
    market-panel setup (test_market_panel_run_decision_and_test2_sidecar)
    rather than reinventing a fixture flow."""

    def test_generates_a_valid_handoff_for_a_real_assumption_run(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            service.import_market_panel(
                user["organization_id"], user["id"], deal_id, "panel.csv", PANEL,
                {"source_name": "Analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01",
                 "licensing_notes": "Analyst-owned internal data", "freshness_state": "current"},
            )
            run = service.run_assumption_intelligence(user["organization_id"], user["id"], deal_id, "vacancy", {"market_id": "BAL"})
            self.assertEqual(run["status"], "candidate")

            payload = service.create_assumption_run_handoff(user["organization_id"], user["id"], run["id"])

            self.assertEqual(payload["schemaVersion"], SCHEMA_VERSION)
            self.assertEqual(payload["sourceModule"], "marketsignal")
            self.assertEqual(len(payload["assumptions"]), 1)
            self.assertEqual(payload["assumptions"][0]["category"], "vacancy")
            self.assertEqual(payload["assumptions"][0]["status"], "proposed")
            self.assertTrue(is_valid_creos_ulid(payload["handoffId"]))
            self.assertEqual(len(payload["sources"]), 1)
            self.assertEqual(payload["sources"][0]["sourceName"], "Analyst panel")
            self.assertEqual(payload["sources"][0]["sourceType"], "licensed_data")
            self.assertEqual(len(payload["provenance"]), 1)
            assumption = payload["assumptions"][0]
            self.assertEqual(assumption["sourceId"], payload["sources"][0]["sourceId"])
            self.assertEqual(assumption["provenanceId"], payload["provenance"][0]["provenanceId"])
            json.dumps(payload)  # must be JSON-serializable end to end, not just from the pure builder

    def test_raises_lookup_error_for_an_unknown_run_id(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            with self.assertRaises(LookupError):
                service.create_assumption_run_handoff(user["organization_id"], user["id"], "not-a-real-run-id")

    def test_generating_a_handoff_does_not_mutate_the_immutable_run(self):
        # assumption_runs has real DB triggers refusing UPDATE/DELETE --
        # this proves create_assumption_run_handoff is genuinely read-only,
        # not just documented as such.
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            service.import_market_panel(
                user["organization_id"], user["id"], deal_id, "panel.csv", PANEL,
                {"source_name": "Analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01",
                 "licensing_notes": "Analyst-owned internal data", "freshness_state": "current"},
            )
            run = service.run_assumption_intelligence(user["organization_id"], user["id"], deal_id, "exit_cap_rate", {"market_id": "BAL"})
            before = service.create_assumption_run_handoff(user["organization_id"], user["id"], run["id"])
            after = service.create_assumption_run_handoff(user["organization_id"], user["id"], run["id"])
            self.assertEqual(before, after)

    def test_same_deal_has_one_property_identity_across_distinct_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            service.import_market_panel(
                user["organization_id"], user["id"], deal_id, "panel.csv", PANEL,
                {"source_name": "Analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01",
                 "licensing_notes": "Analyst-owned internal data", "freshness_state": "current"},
            )
            first = service.run_assumption_intelligence(user["organization_id"], user["id"], deal_id, "vacancy", {"market_id": "BAL"})
            second = service.run_assumption_intelligence(user["organization_id"], user["id"], deal_id, "exit_cap_rate", {"market_id": "BAL"})
            first_payload = service.create_assumption_run_handoff(user["organization_id"], user["id"], first["id"])
            second_payload = service.create_assumption_run_handoff(user["organization_id"], user["id"], second["id"])
            self.assertEqual(first_payload["property"]["identity"]["propertyId"], second_payload["property"]["identity"]["propertyId"])
            self.assertNotEqual(first_payload["handoffId"], second_payload["handoffId"])
            self.assertNotEqual(first_payload["assumptions"][0]["assumptionId"], second_payload["assumptions"][0]["assumptionId"])
            self.assertEqual(first_payload["sources"][0]["sourceId"], second_payload["sources"][0]["sourceId"])

    def test_creos_identity_links_are_immutable_and_integrity_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            service.import_market_panel(
                user["organization_id"], user["id"], deal_id, "panel.csv", PANEL,
                {"source_name": "Analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01",
                 "licensing_notes": "Analyst-owned internal data", "freshness_state": "current"},
            )
            run = service.run_assumption_intelligence(user["organization_id"], user["id"], deal_id, "vacancy", {"market_id": "BAL"})
            service.create_assumption_run_handoff(user["organization_id"], user["id"], run["id"])
            with service.db.connect() as connection:
                count = connection.execute("SELECT COUNT(*) FROM creos_entity_links WHERE organization_id=?", (user["organization_id"],)).fetchone()[0]
                self.assertEqual(count, 6)
                with self.assertRaises(Exception):
                    connection.execute("UPDATE creos_entity_links SET creos_ulid='00000000000000000000000000'")
            report = service.operational_integrity(user["organization_id"])
            self.assertTrue(report["ok"])
            self.assertEqual(report["creosIdentity"], {"count": 6, "mismatches": 0})


if __name__ == "__main__":
    unittest.main()
