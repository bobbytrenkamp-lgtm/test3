from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from test3.opportunity.screening import (
    OpportunityScreeningInput,
    OpportunityScreeningPolicy,
    OpportunityScreeningTier,
    calculate_screening_metrics,
    screen_opportunity,
)


HASHES = {dimension: (character * 64,) for dimension, character in zip(
    ("rent", "basis", "noi", "cap_rate", "vacancy", "comparables", "location"),
    "abcdef1",
)}
DATES = {dimension: date(2026, 6, 1) for dimension in HASHES}
EVALUATED_AT = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _input(**changes) -> OpportunityScreeningInput:
    values = {
        "candidate_id": "fictional-candidate-1",
        "property_type": "multifamily",
        "analysis_as_of": date(2026, 6, 30),
        "subject_rent": Decimal("1800"),
        "market_rent": Decimal("2000"),
        "rent_unit": "USD/unit/month",
        "acquisition_basis": Decimal("90000000"),
        "comparable_sale_basis": Decimal("100000000"),
        "basis_unit": "USD/property",
        "current_noi": Decimal("5000000"),
        "stabilized_noi": Decimal("5500000"),
        "subject_cap_rate": Decimal("0.0575"),
        "market_cap_rate": Decimal("0.05"),
        "subject_vacancy": Decimal("0.08"),
        "market_vacancy": Decimal("0.05"),
        "rent_comp_count": 6,
        "sale_comp_count": 4,
        "location_evidence_complete": True,
        "renovation_budget_verified": True,
        "insurance_evidence_date": date(2026, 5, 1),
        "evidence_hashes": HASHES,
        "evidence_dates": DATES,
    }
    values.update(changes)
    return OpportunityScreeningInput(**values)


class OpportunityFinderScreeningTests(unittest.TestCase):
    def test_high_priority_is_explainable_deterministic_and_not_a_score(self):
        first = screen_opportunity(_input(), evaluated_at=EVALUATED_AT)
        second = screen_opportunity(_input(), evaluated_at=EVALUATED_AT)
        self.assertEqual(first, second)
        self.assertEqual(first.screening_tier, OpportunityScreeningTier.HIGH_PRIORITY_REVIEW)
        self.assertEqual(first.evidence_completeness, Decimal("1.0000"))
        self.assertEqual(first.evidence_freshness_days, 29)
        self.assertEqual(len(first.input_snapshot_hash), 64)
        self.assertEqual(len(first.evidence_hash), 64)
        self.assertEqual(len(first.result_hash), 64)
        self.assertIn("SUBJECT_RENT_BELOW_MARKET", {item.code for item in first.reasons})
        self.assertIn("BASIS_BELOW_COMPARABLES", {item.code for item in first.reasons})
        payload = first.to_dict()
        self.assertEqual(payload["validatedOpportunityScore"]["status"], "NO_VALIDATED_OPPORTUNITY_SCORE")
        self.assertFalse(payload["automaticUnderwritingApply"])
        self.assertIn("not_investment_recommendation", payload["screeningTierMeaning"])

    def test_missing_values_remain_missing_and_cannot_receive_supported_tier(self):
        value = OpportunityScreeningInput(
            candidate_id="missing-evidence",
            property_type="multifamily",
            analysis_as_of=date(2026, 6, 30),
        )
        metrics = calculate_screening_metrics(value)
        self.assertTrue(all(item is None for item in metrics.values()))
        result = screen_opportunity(value, evaluated_at=EVALUATED_AT)
        self.assertEqual(result.screening_tier, OpportunityScreeningTier.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.evidence_completeness, Decimal("0.0000"))
        self.assertIsNone(result.evidence_freshness_days)
        self.assertEqual(result.reasons, ())
        self.assertIn("INSUFFICIENT_EVIDENCE_FOR_SCREENING", {item.code for item in result.warnings})

    def test_values_without_lineage_do_not_count_as_complete(self):
        result = screen_opportunity(_input(evidence_hashes={}), evaluated_at=EVALUATED_AT)
        self.assertEqual(result.screening_tier, OpportunityScreeningTier.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.evidence_completeness, Decimal("0.0000"))
        self.assertIn("EVIDENCE_LINEAGE_MISSING", {item.code for item in result.warnings})

    def test_high_priority_requires_governed_comparable_lineage(self):
        hashes = {key: value for key, value in HASHES.items() if key != "comparables"}
        result = screen_opportunity(_input(evidence_hashes=hashes), evaluated_at=EVALUATED_AT)
        self.assertNotEqual(result.screening_tier, OpportunityScreeningTier.HIGH_PRIORITY_REVIEW)
        self.assertIn("EVIDENCE_LINEAGE_MISSING", {item.code for item in result.warnings})

    def test_clean_but_unexceptional_evidence_is_low_priority(self):
        result = screen_opportunity(_input(
            subject_rent=Decimal("2000"),
            acquisition_basis=Decimal("100000000"),
            stabilized_noi=Decimal("5000000"),
            subject_cap_rate=Decimal("0.05"),
            subject_vacancy=Decimal("0.05"),
        ), evaluated_at=EVALUATED_AT)
        self.assertEqual(result.screening_tier, OpportunityScreeningTier.LOW_PRIORITY)
        self.assertEqual([item.code for item in result.reasons], ["COMPARABLE_SUPPORT"])

    def test_moderate_supported_signal_is_worth_reviewing(self):
        result = screen_opportunity(_input(
            subject_rent=Decimal("1880"),
            acquisition_basis=Decimal("100000000"),
            stabilized_noi=Decimal("5000000"),
            subject_cap_rate=Decimal("0.05"),
            subject_vacancy=Decimal("0.05"),
        ), evaluated_at=EVALUATED_AT)
        self.assertEqual(result.screening_tier, OpportunityScreeningTier.WORTH_REVIEWING)

    def test_stale_evidence_cannot_be_high_priority(self):
        old_dates = {dimension: date(2024, 1, 1) for dimension in DATES}
        result = screen_opportunity(_input(evidence_dates=old_dates), evaluated_at=EVALUATED_AT)
        self.assertEqual(result.screening_tier, OpportunityScreeningTier.LOW_PRIORITY)
        self.assertIn("STALE_EVIDENCE", {item.code for item in result.warnings})

    def test_hashes_are_stable_across_mapping_order(self):
        reverse_hashes = dict(reversed(list(HASHES.items())))
        reverse_dates = dict(reversed(list(DATES.items())))
        first = screen_opportunity(_input(), evaluated_at=EVALUATED_AT)
        second = screen_opportunity(_input(evidence_hashes=reverse_hashes, evidence_dates=reverse_dates), evaluated_at=EVALUATED_AT)
        self.assertEqual(first.input_snapshot_hash, second.input_snapshot_hash)
        self.assertEqual(first.evidence_hash, second.evidence_hash)
        self.assertEqual(first.result_hash, second.result_hash)

    def test_policy_is_versioned_and_content_hashed(self):
        first = OpportunityScreeningPolicy()
        second = OpportunityScreeningPolicy(version="1.0.1")
        self.assertNotEqual(first.content_hash, second.content_hash)
        self.assertNotEqual(
            screen_opportunity(_input(), policy=first, evaluated_at=EVALUATED_AT).input_snapshot_hash,
            screen_opportunity(_input(), policy=second, evaluated_at=EVALUATED_AT).input_snapshot_hash,
        )

    def test_future_or_invalid_evidence_is_rejected(self):
        future_dates = {**DATES, "rent": date(2026, 7, 1)}
        with self.assertRaisesRegex(ValueError, "dated after"):
            screen_opportunity(_input(evidence_dates=future_dates), evaluated_at=EVALUATED_AT)
        invalid_hashes = {**HASHES, "rent": ("not-a-hash",)}
        with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
            screen_opportunity(_input(evidence_hashes=invalid_hashes), evaluated_at=EVALUATED_AT)

    def test_financial_metrics_are_exact_across_large_deal_scales(self):
        for comparable_basis in (
            Decimal("100000"), Decimal("10000000"), Decimal("100000000"),
            Decimal("1000000000"), Decimal("10000000000"),
        ):
            with self.subTest(comparable_basis=comparable_basis):
                metrics = calculate_screening_metrics(_input(
                    acquisition_basis=comparable_basis * Decimal("0.9"),
                    comparable_sale_basis=comparable_basis,
                    current_noi=comparable_basis * Decimal("0.05"),
                    stabilized_noi=comparable_basis * Decimal("0.055"),
                ))
                self.assertEqual(metrics["basisDiscountPct"], Decimal("0.1"))
                self.assertEqual(metrics["noiUpside"], comparable_basis * Decimal("0.005"))
                self.assertEqual(metrics["noiUpsideRatio"], Decimal("0.1"))

    def test_partial_pairs_are_not_coerced_to_zero_or_fabricated(self):
        metrics = calculate_screening_metrics(_input(
            market_rent=None,
            comparable_sale_basis=None,
            stabilized_noi=None,
            market_cap_rate=None,
            market_vacancy=None,
        ))
        self.assertTrue(all(item is None for item in metrics.values()))


if __name__ == "__main__":
    unittest.main()
