"""Opt-in realistic local Opportunity Finder scale benchmark.

The fixture is fictional, created in a temporary directory, and deleted when
the process exits. It exercises evidence-version and screening-run joins; it
is not evidence and never enters the application warehouse.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
import time

from test3.db import now
from test3.service import Service


TIERS = ("HIGH_PRIORITY_REVIEW", "WORTH_REVIEWING", "LOW_PRIORITY", "INSUFFICIENT_EVIDENCE")
MARKETS = ("Raleigh", "Charlotte", "Nashville", "Richmond", "Atlanta")
PROPERTY_TYPES = ("multifamily", "industrial", "office", "retail")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def result_json(index: int) -> tuple[str, str]:
    value = {
        "screeningTier": TIERS[index % len(TIERS)],
        "evidenceCompleteness": "0.7142857142857142857142857143",
        "evidenceFreshnessDays": 30 + index % 500,
        "evidenceFreshnessDetail": {"oldestEvidenceAgeDays": 30 + index % 500,
                                    "signalEvidenceMaxAgeDays": 30 + index % 500},
        "derivedMetrics": {"rentGapPct": "0.10" if index % 2 == 0 else "0.02",
                           "basisDiscountPct": "0.08", "noiUpside": "100000.00",
                           "noiUpsideRatio": "0.10", "capRateSpreadBps": "50",
                           "vacancyDelta": "0.02"},
        "reasons": [], "warnings": [],
        "validatedOpportunityScore": {"status": "NO_VALIDATED_OPPORTUNITY_SCORE"},
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return encoded, digest(encoded)


def populate(service: Service, user: dict, count: int) -> dict:
    organization, created = user["organization_id"], now()
    candidates, versions, runs = [], [], []
    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    current_cutoff, outdated_cutoff, unscreened_cutoff = int(count * .3), int(count * .5), int(count * .7)
    for index in range(count):
        candidate_id = f"benchmark-candidate-{index:06d}"
        candidates.append((candidate_id, organization, None, user["id"],
                           PROPERTY_TYPES[index % len(PROPERTY_TYPES)], f"Apartments {index:06d}",
                           f"{index} Benchmark Parkway", None, MARKETS[index % len(MARKETS)], None,
                           "candidate", "manual", created))
        first_version = f"benchmark-version-{index:06d}-1"
        first_content = '{"inputs":{"analysis_as_of":"2026-06-30"}}'
        versions.append((first_version, organization, candidate_id, 1, "benchmark/1", "2026-06-30",
                         first_content, digest(first_content + candidate_id), user["id"], created))
        screened_version = first_version
        if current_cutoff <= index < outdated_cutoff or index >= unscreened_cutoff:
            second_version = f"benchmark-version-{index:06d}-2"
            second_content = '{"inputs":{"analysis_as_of":"2026-07-31"}}'
            versions.append((second_version, organization, candidate_id, 2, "benchmark/1", "2026-07-31",
                             second_content, digest(second_content + candidate_id), user["id"], created))
            if index >= unscreened_cutoff:
                screened_version = second_version
            if index % 100 == 0:
                third_version = f"benchmark-version-{index:06d}-3"
                third_content = '{"inputs":{"analysis_as_of":"2026-08-15"}}'
                versions.append((third_version, organization, candidate_id, 3, "benchmark/1", "2026-08-15",
                                 third_content, digest(third_content + candidate_id), user["id"], created))
                if index >= unscreened_cutoff:
                    screened_version = third_version
        if index < outdated_cutoff or index >= unscreened_cutoff:
            tier, (encoded, result_hash) = TIERS[index % len(TIERS)], result_json(index)
            evaluated = (base_time + timedelta(seconds=index)).isoformat()
            runs.append((f"benchmark-run-{index:06d}", organization, candidate_id, screened_version,
                         "benchmark-policy", "1.0.0", "a" * 64, "b" * 64, "c" * 64, tier,
                         encoded, result_hash, user["id"], evaluated, evaluated))
    with service.db.connect() as connection:
        connection.executemany("INSERT INTO opportunity_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", candidates)
        connection.executemany("INSERT INTO opportunity_candidate_versions VALUES(?,?,?,?,?,?,?,?,?,?)", versions)
        connection.executemany("INSERT INTO opportunity_screening_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", runs)
    return {"candidates": len(candidates), "versions": len(versions), "screening_runs": len(runs)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=int, default=10_000)
    args = parser.parse_args()
    if args.candidates < 100 or args.candidates > 100_000:
        raise SystemExit("--candidates must be between 100 and 100,000")
    with tempfile.TemporaryDirectory(prefix="test3-finder-benchmark-") as temporary:
        service = Service(Path(temporary)); user = service.seed()
        population = populate(service, user, args.candidates)
        queries = [
            {"limit": 25}, {"limit": 25, "sort": "screening_tier"},
            {"limit": 25, "screening_currency_status": "CURRENT"},
            {"limit": 25, "screening_currency_status": "OUTDATED_EVIDENCE"},
            {"limit": 25, "screening_tier": "HIGH_PRIORITY_REVIEW"},
            {"limit": 25, "market": "Raleigh"}, {"limit": 25, "q": "Apartments"},
            {"limit": 25, "rent_gap_min": "0.075"}, {"limit": 25, "basis_discount_min": "0.075"},
        ] + [{"limit": 25, "offset": min(offset, max(0, args.candidates - 25))}
             for offset in (0, 1_000, 5_000, 9_000)]
        timings = []
        for query in queries:
            started = time.perf_counter()
            result = service.list_opportunity_candidates(user["organization_id"], query)
            timings.append({"query": query, "seconds": round(time.perf_counter() - started, 6),
                            "total": result["pagination"]["total"],
                            "returned": result["pagination"]["returned"]})
        plans = service.opportunity_candidate_query_plan(user["organization_id"])
        print(json.dumps({"fictionalLocalFixture": population, "queryCount": len(timings),
                          "medianSeconds": round(statistics.median(item["seconds"] for item in timings), 6),
                          "maximumSeconds": max(item["seconds"] for item in timings),
                          "timings": timings, "queryPlan": plans}, indent=2))


if __name__ == "__main__":
    main()
