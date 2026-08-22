from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from test3.db import now
from test3.service import Service


TIERS = ("HIGH_PRIORITY_REVIEW", "WORTH_REVIEWING", "LOW_PRIORITY", "INSUFFICIENT_EVIDENCE")
MARKETS = ("Raleigh", "Charlotte", "Nashville", "Richmond")
PROPERTY_TYPES = ("multifamily", "industrial", "office", "retail")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _result(tier: str, index: int) -> tuple[str, str]:
    value = {
        "screeningTier": tier,
        "evidenceCompleteness": "0.7142857142857142857142857143",
        "evidenceFreshnessDays": 30 + index % 400,
        "evidenceFreshnessDetail": {"oldestEvidenceAgeDays": 30 + index % 400,
                                    "signalEvidenceMaxAgeDays": 30 + index % 400},
        "derivedMetrics": {"rentGapPct": "0.10" if index % 2 == 0 else "0.02",
                           "basisDiscountPct": "0.08", "noiUpside": "100000.00",
                           "noiUpsideRatio": "0.10", "capRateSpreadBps": "50",
                           "vacancyDelta": "0.02"},
        "reasons": [{"code": "SCALE_FIXTURE", "statement": "Governed scale fixture.",
                     "dimension": "rent"}],
        "warnings": [],
        "validatedOpportunityScore": {"status": "NO_VALIDATED_OPPORTUNITY_SCORE"},
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return encoded, _digest(encoded)


class OpportunityFinderRealisticScaleTests(unittest.TestCase):
    def test_relational_scale_queries_remain_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = Service(Path(temporary)); user = service.seed(); organization = user["organization_id"]
            created = now(); candidates, versions, runs = [], [], []
            base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
            for index in range(1_200):
                candidate_id = f"scale-candidate-{index:05d}"
                candidates.append((candidate_id, organization, None, user["id"],
                                   PROPERTY_TYPES[index % len(PROPERTY_TYPES)], f"Apartments {index:05d}",
                                   f"{index} Scale Avenue", None, MARKETS[index % len(MARKETS)], None,
                                   "candidate", "manual", created))
                version_one = f"scale-version-{index:05d}-1"
                content_one = json.dumps({"inputs": {"analysis_as_of": "2026-06-30"}}, separators=(",", ":"))
                versions.append((version_one, organization, candidate_id, 1, "scale/1", "2026-06-30",
                                 content_one, _digest(content_one + candidate_id), user["id"], created))
                screened_version = version_one
                if 400 <= index < 700 or index >= 900:
                    version_two = f"scale-version-{index:05d}-2"
                    content_two = json.dumps({"inputs": {"analysis_as_of": "2026-07-31"}}, separators=(",", ":"))
                    versions.append((version_two, organization, candidate_id, 2, "scale/1", "2026-07-31",
                                     content_two, _digest(content_two + candidate_id), user["id"], created))
                    if index >= 900:
                        screened_version = version_two
                    if index % 100 == 0:
                        version_three = f"scale-version-{index:05d}-3"
                        content_three = json.dumps({"inputs": {"analysis_as_of": "2026-08-15"}}, separators=(",", ":"))
                        versions.append((version_three, organization, candidate_id, 3, "scale/1", "2026-08-15",
                                         content_three, _digest(content_three + candidate_id), user["id"], created))
                        if index >= 900:
                            screened_version = version_three
                if index < 700 or index >= 900:
                    tier = TIERS[index % len(TIERS)]; result_json, result_hash = _result(tier, index)
                    evaluated = (base_time + timedelta(seconds=index)).isoformat()
                    runs.append((f"scale-run-{index:05d}-1", organization, candidate_id, screened_version,
                                 "scale-policy", "1.0.0", "a" * 64, "b" * 64, "c" * 64, tier,
                                 result_json, result_hash, user["id"], evaluated, evaluated))
                    if index >= 900 and index % 50 == 0:
                        later = (base_time + timedelta(seconds=index + 10_000)).isoformat()
                        runs.append((f"scale-run-{index:05d}-2", organization, candidate_id, screened_version,
                                     "scale-policy", "1.0.0", "a" * 64, "b" * 64, "c" * 64, tier,
                                     result_json, result_hash, user["id"], later, later))
            with service.db.connect() as connection:
                connection.executemany("INSERT INTO opportunity_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", candidates)
                connection.executemany("INSERT INTO opportunity_candidate_versions VALUES(?,?,?,?,?,?,?,?,?,?)", versions)
                connection.executemany("INSERT INTO opportunity_screening_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", runs)
            queries = [
                {"limit": 25}, {"limit": 25, "sort": "screening_tier"},
                {"limit": 25, "screening_currency_status": "CURRENT"},
                {"limit": 25, "screening_currency_status": "OUTDATED_EVIDENCE"},
                {"limit": 25, "screening_tier": "HIGH_PRIORITY_REVIEW"},
                {"limit": 25, "market": "Raleigh"}, {"limit": 25, "q": "Apartments"},
                {"limit": 25, "rent_gap_min": "0.075"},
                {"limit": 25, "basis_discount_min": "0.075"},
                {"limit": 25, "offset": 500}, {"limit": 25, "offset": 1_100},
            ]
            started = time.perf_counter()
            results = [service.list_opportunity_candidates(organization, query) for query in queries]
            elapsed = time.perf_counter() - started
            self.assertEqual(results[0]["pagination"], {"limit": 25, "offset": 0, "returned": 25, "total": 1_200})
            self.assertEqual(results[2]["pagination"]["total"], 700)
            self.assertEqual(results[3]["pagination"]["total"], 300)
            self.assertEqual(service.list_opportunity_candidates(
                organization, {"screening_currency_status": "NOT_SCREENED"})["pagination"]["total"], 200)
            self.assertEqual(results[-1]["pagination"]["returned"], 25)
            self.assertTrue(all(service.list_opportunity_candidates(
                organization, {"screening_tier": tier, "limit": 1})["pagination"]["total"] > 0
                                for tier in TIERS))
            self.assertLess(elapsed, 15.0)


if __name__ == "__main__":
    unittest.main()
