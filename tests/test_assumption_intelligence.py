from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test3.service import Service
from test3.adapters import test2_export
from test3.assumptions.analysis import lead_lag_matrix, stress_scenarios, time_series_diagnostics
from test3.assumptions.public_sources import PUBLIC_SERIES, build_market_panel_csv, parse_bls_csv, parse_fred_csv
from test3.assumptions.observations import parse_market_panel, rows_to_observations


PANEL = b"""period,market_id,market_name,property_type,source,source_date,source_reference,usage_rights,county_fips,state_fips,rent_growth_12m,expense_growth,property_tax_growth,insurance_growth,vacancy_rate,effective_rent,renewal_probability,downtime_months,tenant_improvements,leasing_commission_rate,transaction_cap_rate,discount_rate,debt_interest_rate,construction_cost_growth,lease_up_units_per_month,lease_comp_count\n2025-01-01,BAL,Baltimore,office,Analyst panel,2025-02-01,local://panel,Internal use,24510,24,0.025,0.030,0.040,0.060,0.12,31.0,0.65,9,45,0.05,0.065,0.09,0.06,0.04,2,12\n2025-04-01,BAL,Baltimore,office,Analyst panel,2025-05-01,local://panel,Internal use,24510,24,0.030,0.035,0.045,0.070,0.11,32.0,0.67,8,47,0.05,0.067,0.095,0.062,0.045,2.2,14\n2025-07-01,BAL,Baltimore,office,Analyst panel,2025-08-01,local://panel,Internal use,24510,24,0.035,0.040,0.050,0.080,0.10,33.0,0.70,7,50,0.055,0.070,0.10,0.065,0.05,2.5,16\n"""


class AssumptionIntelligenceTests(unittest.TestCase):
    def test_public_series_catalog_and_offline_adapters(self):
        self.assertGreaterEqual(len(PUBLIC_SERIES), 25)
        fred = parse_fred_csv(b"DATE,DGS10\n2025-01-01,4.25\n2025-01-02,.\n", "DGS10", "treasury_rate", "decimal_fraction")
        self.assertEqual(fred[0]["value"], "0.0425")
        panel = build_market_panel_csv(fred, source="FRED DGS10", source_date="2025-01-02", source_reference="https://fred.stlouisfed.org/series/DGS10", usage_rights="Official public data", property_type="mixed_use")
        _, normalized, errors = parse_market_panel(panel)
        self.assertFalse(errors)
        observation = rows_to_observations("snapshot", "organization", normalized, "2025-01-02T00:00:00Z")[0]
        self.assertEqual((observation["geography_type"], observation["metric"]), ("country", "treasury_rate"))
        bls = parse_bls_csv(b"series_id,year,period,value\nCUUR0000SA0,2025,M01,317.7\nCUUR0000SA0,2025,M13,318.0\n", "CUUR0000SA0", "inflation_index", "index")
        self.assertEqual(bls, [{"period": "2025-01-01", "metric": "inflation_index", "value": "317.7", "unit": "index", "geography_type": "country", "geography_id": "US", "source_row": 2}])

    def test_institutional_descriptive_analytics(self):
        observations = []
        for index, period in enumerate(("2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01", "2025-04-01")):
            for metric, value in (("vacancy_rate", .10 + index * .01), ("rent_growth_12m", .04 - index * .005)):
                observations.append({"metric": metric, "value": str(value), "observation_date": period, "property_type": "office", "geography_type": "market", "geography_id": "BAL"})
        diagnostics = time_series_diagnostics(observations)
        self.assertEqual(len(diagnostics), 2)
        self.assertTrue(all(item["periodCount"] == 6 for item in diagnostics))
        self.assertEqual(len(stress_scenarios(observations)), 2)
        lead_lag = lead_lag_matrix(observations)
        self.assertEqual(len(lead_lag), 1)
        self.assertIn("not causal", lead_lag[0]["warning"])

    def test_market_panel_run_decision_and_test2_sidecar(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            self.assertGreaterEqual(len(service.bootstrap(user)["publicSeriesCatalog"]), 25)
            installed = service.install_model_artifact(user["organization_id"], user["id"], Path("analytics/outputs/fictional/model_artifact.json"))
            self.assertEqual(installed["dataStatus"], "fictional_synthetic")
            self.assertEqual(installed["validationState"], "rejected")
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            imported = service.import_market_panel(user["organization_id"], user["id"], deal_id, "panel.csv", PANEL, {"source_name": "Analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01", "licensing_notes": "Analyst-owned internal data", "freshness_state": "current"})
            self.assertEqual(imported["invalidRows"], 0)
            run = service.run_market_rent_growth(user["organization_id"], user["id"], deal_id, {"market_id": "BAL"})
            self.assertEqual(run["status"], "candidate")
            self.assertTrue(run["candidateOnly"])
            self.assertIsNone(run["modelEstimate"])
            decision = service.decide_assumption_run(user["organization_id"], user["id"], run["id"], "base", None, "Analyst selected the observed median after reviewing the evidence.", "Analyst panel 2025Q3")
            self.assertEqual(decision["status"], "approved")
            snapshot = service.deal(deal_id, user["organization_id"])
            self.assertEqual(len(snapshot["assumption_runs"]), 1)
            self.assertEqual(len(snapshot["assumption_decision_contexts"]), 1)
            self.assertGreater(snapshot["data_profile"]["coverageRatio"], 0.8)
            self.assertGreater(len(snapshot["benchmark_matrix"]), 10)
            self.assertTrue(snapshot["correlation_matrix"])
            self.assertGreater(len(snapshot["time_series_diagnostics"]), 10)
            self.assertGreater(len(snapshot["stress_scenarios"]), 10)
            for assumption_type in ("expense_growth", "property_tax_growth", "insurance_growth", "vacancy", "market_rent", "renewal_probability", "downtime", "tenant_improvements", "leasing_commissions", "exit_cap_rate", "discount_rate", "debt_interest_rate", "construction_cost_growth", "lease_up_pace"):
                candidate = service.run_assumption_intelligence(user["organization_id"], user["id"], deal_id, assumption_type, {"market_id": "BAL"})
                self.assertEqual(candidate["status"], "candidate", assumption_type)
            with self.assertRaisesRegex(ValueError, "already imported"):
                service.import_market_panel(user["organization_id"], user["id"], deal_id, "panel.csv", PANEL, {"source_name": "Analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01", "licensing_notes": "Analyst-owned internal data", "freshness_state": "current"})
            service.import_market_panel(user["organization_id"], user["id"], None, "enterprise-panel.csv", PANEL, {"source_name": "Enterprise analyst panel", "source_version": "2025Q3", "as_of_date": "2025-08-01", "licensing_notes": "Organization-wide analyst-owned data", "freshness_state": "current"})
            second = service.create_deal(user["organization_id"], user["id"], {"name": "Second office", "property_type": "office"})
            shared = service.run_assumption_intelligence(user["organization_id"], user["id"], second["id"], "expense_growth", {"market_id": "BAL"})
            self.assertEqual(shared["status"], "candidate")
            with service.db.connect() as connection:
                with self.assertRaises(Exception):
                    connection.execute("UPDATE assumption_runs SET rationale='changed' WHERE id=?", (run["id"],))

    def test_formula_and_bad_fips_are_row_level_errors(self):
        bad = PANEL.replace(b"24510,24,0.025", b"12A10,24,=1+1")
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
            with service.db.connect() as connection:
                deal_id = connection.execute("SELECT id FROM deals").fetchone()[0]
            result = service.import_market_panel(user["organization_id"], user["id"], deal_id, "panel.csv", bad, {"source_name": "Analyst panel", "source_version": "1", "as_of_date": "2025-08-01", "licensing_notes": "Analyst-owned", "freshness_state": "current"})
            self.assertEqual(result["invalidRows"], 1)

    def test_approved_growth_domains_map_to_separate_test2_curves(self):
        deal = {"id": "deal", "name": "Example", "property_type": "office"}
        approved = []
        for field, value in (("property_name", "Example"), ("forecast_start_date", "2026-01-01"), ("forecast_months", "120"), ("discount_rate", "0.09"), ("market_rent_growth", "0.03"), ("expense_growth", "0.025"), ("property_tax_growth", "0.04"), ("insurance_growth", "0.06"), ("construction_cost_growth", "0.035")):
            approved.append({"id": field, "field_name": field, "normalized_value": value, "review_status": "approved", "reviewed_at": "2026-01-01", "source_kind": "user_entered"})
        result = test2_export(deal, approved, [])
        curves = result["test2PortableModel"]["model"]["growthCurves"]
        self.assertEqual(len(curves), 5)
        self.assertEqual(len({curve["id"] for curve in curves}), 5)


if __name__ == "__main__":
    unittest.main()
