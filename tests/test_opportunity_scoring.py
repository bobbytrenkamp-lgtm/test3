from __future__ import annotations

import unittest

from test3.opportunity.scoring import DEFAULT_POLICY, current_score_status, promotion_decision, score_dataset_readiness


def _row(**changes) -> dict:
    row = {
        "observation_id": "fictional-1",
        "property_id": "fictional-property-1",
        "market_id": "fictional-market-1",
        "period": "2025-Q1",
        "property_type": "multifamily",
        "forecast_origin": "2025-01-01",
        "feature_available_at": "2024-12-31",
        "outcome_realized_at": "2026-01-01",
        "outcome_released_at": "2026-02-01",
        "outcome": "realized_total_return",
        "outcome_value": "0.10",
        "data_status": "fictional_synthetic",
        "analyst_verified": True,
        "rights_documented": True,
        "source_hash": "a" * 64,
        "feature_hash": "b" * 64,
    }
    row.update(changes)
    return row


class OpportunityScoringGovernanceTests(unittest.TestCase):
    def test_current_product_state_is_honest_and_produces_no_score(self):
        status = current_score_status()
        self.assertEqual(status["status"], "NO_VALIDATED_OPPORTUNITY_SCORE")
        self.assertFalse(status["scoreProduced"])
        self.assertFalse(status["eligibleForControllingUnderwriting"])
        self.assertTrue(status["analystApprovalRequired"])
        self.assertIn("candidate_backtest_not_ready", status["reasons"])

    def test_synthetic_outcomes_can_never_satisfy_readiness(self):
        rows = [_row(observation_id=f"fictional-{index}", property_id=f"fictional-property-{index}")
                for index in range(500)]
        readiness = score_dataset_readiness(rows)
        self.assertEqual(readiness["eligibleObservations"], 0)
        self.assertEqual(readiness["rejected"]["non_real_data"], 500)
        self.assertFalse(readiness["readyForCandidateBacktest"])

    def test_leakage_and_duplicate_outcomes_fail_before_backtesting(self):
        leaked = _row(data_status="real", feature_available_at="2025-01-02")
        duplicate = dict(leaked)
        duplicate["observation_id"] = "fictional-duplicate"
        readiness = score_dataset_readiness([leaked, duplicate])
        self.assertEqual(readiness["eligibleObservations"], 0)
        self.assertEqual(readiness["rejected"]["future_feature_leakage"], 1)
        self.assertEqual(readiness["rejected"]["duplicate_property_origin_outcome"], 1)

    def test_promotion_requires_baseline_holdouts_stability_and_lineage(self):
        readiness = {"readyForCandidateBacktest": True, "blockers": []}
        validation = {
            "dataStatus": "real",
            "oosPredictions": 200,
            "timeHoldoutStatus": "passed",
            "geographyHoldoutStatus": "passed",
            "baselineImprovement": 0,
            "stabilityStatus": "failed",
            "pythonCrossCheckStatus": "failed",
            "rCrossCheckStatus": "not_available_policy_permitted",
            "modelResultHash": "not-a-hash",
            "sourceHashes": [],
        }
        result = promotion_decision(readiness, validation)
        self.assertEqual(result["status"], "NO_VALIDATED_OPPORTUNITY_SCORE")
        self.assertIn("best_baseline_not_beaten", result["reasons"])
        self.assertIn("stability_not_passed", result["reasons"])
        self.assertIn("independent_python_check_not_passed", result["reasons"])
        self.assertIn("validation_lineage_incomplete", result["reasons"])
        self.assertEqual(len(DEFAULT_POLICY.content_hash), 64)


if __name__ == "__main__":
    unittest.main()
