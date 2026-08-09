from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import duckdb

from .datasets import prepare_panel
from .lags import evaluate_candidate_lags
from .modeling import train_panel_candidate


MAX_INPUT_ROWS = 2_000_000


def _records(path: str) -> list[dict]:
    source = Path(path).resolve()
    if not source.is_file() or source.suffix.lower() not in {".csv", ".parquet"}:
        raise ValueError("research input must be an existing CSV or Parquet file")
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as stream:
            rows = []
            for row in csv.DictReader(stream):
                if len(rows) >= MAX_INPUT_ROWS:
                    raise ValueError(f"research input exceeds the {MAX_INPUT_ROWS:,}-row command limit")
                rows.append(row)
    else:
        with duckdb.connect(":memory:") as connection:
            result = connection.execute("SELECT * FROM read_parquet(?) LIMIT ?", [str(source), MAX_INPUT_ROWS + 1])
            names = [item[0] for item in result.description]
            rows = [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    if len(rows) > MAX_INPUT_ROWS:
        raise ValueError(f"research input exceeds the {MAX_INPUT_ROWS:,}-row command limit")
    if not rows:
        raise ValueError("research input is empty")
    return rows


def _features(value: str) -> tuple[str, ...]:
    result = tuple(item.strip() for item in value.split(",") if item.strip())
    if not result:
        raise ValueError("--features must contain at least one column")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local, reproducible Test3 panel research")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("train", "lags"):
        item = subparsers.add_parser(command)
        item.add_argument("--input", required=True)
        item.add_argument("--target", required=True)
        item.add_argument("--entity", default="market_id")
        item.add_argument("--time", default="period")
        item.add_argument("--property-type")
        item.add_argument("--minimum-training-periods", type=int, default=4)
    train = subparsers.choices["train"]
    train.add_argument("--features", required=True, help="Comma-separated governed feature columns")
    train.add_argument("--data-status", choices=("research", "fictional_synthetic", "real"), default="research")
    train.add_argument("--source-manifest-hash", action="append", default=[])
    train.add_argument("--no-entity-effects", action="store_true")
    train.add_argument("--no-time-effects", action="store_true")
    lags = subparsers.choices["lags"]
    lags.add_argument("--feature", required=True)
    lags.add_argument("--lags", default="0,1,2,4,6,8")
    args = parser.parse_args(argv)
    rows = _records(args.input)
    if args.command == "train":
        panel = prepare_panel(rows, target=args.target, features=_features(args.features), entity_column=args.entity,
                              time_column=args.time, required_property_type=args.property_type)
        result = train_panel_candidate(panel, entity_fixed_effects=not args.no_entity_effects,
                                       time_fixed_effects=not args.no_time_effects,
                                       minimum_training_periods=args.minimum_training_periods,
                                       data_status=args.data_status,
                                       source_manifest_hashes=tuple(args.source_manifest_hash))
    else:
        lag_values = tuple(int(value.strip()) for value in args.lags.split(",") if value.strip())
        result = evaluate_candidate_lags(rows, target=args.target, feature=args.feature, lags=lag_values,
                                         minimum_training_periods=args.minimum_training_periods,
                                         entity_column=args.entity, time_column=args.time,
                                         required_property_type=args.property_type)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
