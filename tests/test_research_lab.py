from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test3.research.lab import research_lab_report
from test3.service import Service


class ResearchLabTests(unittest.TestCase):
    def test_empty_lab_is_honest_and_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            service = Service(Path(root)); service.seed()
            with service.db.connect() as connection:
                user = connection.execute("SELECT * FROM users LIMIT 1").fetchone()
            report = research_lab_report(Path(root), service.db, user["organization_id"])
            self.assertEqual(report["warehouse"]["rows"], 0)
            self.assertFalse(report["readiness"]["has_verified_cre_targets"])
            self.assertFalse(report["readiness"]["has_validated_real_model"])
            self.assertEqual(report["model_summary"]["validated_real"], 0)
            self.assertTrue(report["target_readiness"])
            self.assertTrue(all(item["status"] == "not_ready" for item in report["target_readiness"]))
            self.assertLessEqual(len(report["coverage"]), 500)
            self.assertEqual({item["table"] for item in report["feature_tables"]},
                             {"county_year", "county_quarter", "cbsa_year", "cbsa_quarter"})


if __name__ == "__main__":
    unittest.main()
