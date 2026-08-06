from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal


def revision_conflicts(observations: list[dict]) -> list[dict]:
    """Expose differing vintages/sources for the same logical observation key."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in observations:
        key = (row["metric"], row["observation_date"], row["geography_type"], row["geography_id"], row.get("property_type"), row.get("property_subtype"))
        grouped[key].append(row)
    output = []
    for key, rows in sorted(grouped.items()):
        values = sorted({Decimal(str(row["value"])) for row in rows})
        snapshots = sorted({row["snapshot_id"] for row in rows})
        sources = sorted({row["source_label"] for row in rows})
        if len(snapshots) < 2:
            continue
        minimum, maximum = values[0], values[-1]
        output.append({"metric": key[0], "observationDate": key[1], "geographyType": key[2], "geographyId": key[3], "propertyType": key[4], "propertySubtype": key[5], "snapshotCount": len(snapshots), "sourceCount": len(sources), "sources": sources, "distinctValueCount": len(values), "minimum": format(minimum, "f"), "maximum": format(maximum, "f"), "absoluteSpread": format(maximum - minimum, "f"), "relativeSpread": format((maximum - minimum) / abs(minimum), "f") if minimum else None, "conflict": len(values) > 1, "warning": "A conflict may be a legitimate revision, methodology difference, or data error; analyst review is required."})
    return output


def cadence_findings(observations: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[str]] = defaultdict(list)
    for row in observations:
        grouped[(row["metric"], row.get("property_type") or "all", row["geography_type"], row["geography_id"])].append(row["observation_date"])
    output = []
    for key, raw_dates in sorted(grouped.items()):
        dates = sorted({date.fromisoformat(value) for value in raw_dates})
        if len(dates) < 3:
            continue
        gaps = [(right - left).days for left, right in zip(dates, dates[1:])]
        ordered = sorted(gaps); typical = ordered[(len(ordered) - 1) // 2]
        flagged = [{"after": dates[index].isoformat(), "before": dates[index + 1].isoformat(), "days": gap} for index, gap in enumerate(gaps) if typical and gap > typical * 1.75]
        output.append({"metric": key[0], "propertyType": key[1], "geographyType": key[2], "geographyId": key[3], "periodCount": len(dates), "typicalGapDays": typical, "minimumGapDays": min(gaps), "maximumGapDays": max(gaps), "irregular": len(set(gaps)) > 1, "largeGaps": flagged, "warning": "Calendar-gap diagnostic only; consult source frequency and release calendar."})
    return output


def source_scorecards(observations: list[dict], snapshots: list[dict]) -> list[dict]:
    by_snapshot: dict[str, list[dict]] = defaultdict(list)
    for row in observations:
        by_snapshot[row["snapshot_id"]].append(row)
    output = []
    for snapshot in sorted(snapshots, key=lambda item: (item["source_name"], item["imported_at"], item["id"])):
        rows = by_snapshot.get(snapshot["id"], [])
        quality = Counter(row["quality_level"] for row in rows)
        invalid = sum(bool(json.loads(row["validation_errors_json"])) for row in rows)
        output.append({"snapshotId": snapshot["id"], "sourceName": snapshot["source_name"], "sourceVersion": snapshot["source_version"], "asOfDate": snapshot["as_of_date"], "importedAt": snapshot["imported_at"], "freshnessState": snapshot["freshness_state"], "validationState": snapshot["validation_state"], "observationCount": len(rows), "metricCount": len({row["metric"] for row in rows}), "geographyCount": len({(row["geography_type"], row["geography_id"]) for row in rows}), "propertyTypeCount": len({row["property_type"] for row in rows if row.get("property_type")}), "qualityCounts": dict(sorted(quality.items())), "invalidObservationCount": invalid, "contentSha256": snapshot["content_sha256"], "licensingNotes": snapshot["licensing_notes"], "warning": "Coverage and validation indicators are not an endorsement of source accuracy."})
    return output


def research_manifest(observations: list[dict], snapshots: list[dict]) -> dict:
    snapshot_entries = [{"id": item["id"], "sourceName": item["source_name"], "sourceVersion": item["source_version"], "asOfDate": item["as_of_date"], "contentSha256": item["content_sha256"], "schemaVersion": item["schema_version"], "validationState": item["validation_state"]} for item in sorted(snapshots, key=lambda item: item["id"])]
    observation_entries = [{"snapshotId": item["snapshot_id"], "metric": item["metric"], "date": item["observation_date"], "geographyType": item["geography_type"], "geographyId": item["geography_id"], "propertyType": item.get("property_type"), "value": item["value"], "rowHash": item["original_row_hash"]} for item in sorted(observations, key=lambda item: (item["snapshot_id"], item["metric"], item["observation_date"], item["id"]))]
    payload = {"schemaVersion": "test3-research-manifest/1.0", "snapshotCount": len(snapshot_entries), "observationCount": len(observation_entries), "snapshots": snapshot_entries, "observations": observation_entries}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {**payload, "manifestSha256": hashlib.sha256(canonical).hexdigest(), "generatedLocally": True}
