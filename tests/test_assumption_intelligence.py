from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test3.service import Service


PANEL = b"""period,market_id,market_name,property_type,source,source_date,source_reference,usage_rights,county_fips,state_fips,rent_growth_12m,lease_comp_count\n2025-01-01,BAL,Baltimore,office,Analyst panel,2025-02-01,local://panel,Internal use,24510,24,0.025,12\n2025-04-01,BAL,Baltimore,office,Analyst panel,2025-05-01,local://panel,Internal use,24510,24,0.030,14\n2025-07-01,BAL,Baltimore,office,Analyst panel,2025-08-01,local://panel,Internal use,24510,24,0.035,16\n"""


class AssumptionIntelligenceTests(unittest.TestCase):
    def test_market_panel_run_decision_and_test2_sidecar(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Path(folder))
            user = service.seed()
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


if __name__ == "__main__":
    unittest.main()
