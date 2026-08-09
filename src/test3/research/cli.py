from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import duckdb

from .datasets import prepare_panel
from .lags import evaluate_candidate_lags
from .modeling import train_panel_candidate
from .specifications import MODEL_SPECIFICATIONS
from .target_panel import build_target_panel, target_readiness, target_readiness_for_specification
from test3.warehouse.storage import WarehousePaths


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
    readiness = subparsers.add_parser("target-readiness", help="report real CRE target eligibility without fabricating readiness")
    readiness.add_argument("--data-root", default="data")
    readiness.add_argument("--model-specification", choices=tuple(sorted(MODEL_SPECIFICATIONS)))
    target_panel = subparsers.add_parser("build-target-panel", help="join approved CRE targets to immutable feature panels")
    target_panel.add_argument("--data-root", default="data")
    target_panel.add_argument("--property-type", required=True, choices=("multifamily", "industrial", "office", "retail"))
    target_panel.add_argument("--target", required=True)
    target_panel.add_argument("--frequency", choices=("annual", "quarterly"), default="quarterly")
    reproduce = subparsers.add_parser("reproduce", help="recalculate a saved model result and compare its governed hash")
    reproduce.add_argument("--artifact", required=True)
    reproduce.add_argument("--input", required=True)
    reproduce.add_argument("--entity", default="market_id")
    reproduce.add_argument("--time", default="period")
    reproduce.add_argument("--property-type")
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
    train.add_argument("--model-mode", choices=("ad_hoc_research", "governed_candidate", "validated_production"),
                       default="ad_hoc_research")
    train.add_argument("--model-specification", choices=tuple(sorted(MODEL_SPECIFICATIONS)))
    train.add_argument("--source-manifest-hash", action="append", default=[])
    train.add_argument("--target-dataset-hash", action="append", default=[])
    train.add_argument("--feature-table-hash")
    train.add_argument("--feature-registry-version")
    train.add_argument("--code-commit")
    train.add_argument("--output", help="optional local JSON result path")
    train.add_argument("--no-entity-effects", action="store_true")
    train.add_argument("--no-time-effects", action="store_true")
    lags = subparsers.choices["lags"]
    lags.add_argument("--feature", required=True)
    lags.add_argument("--lags", default="0,1,2,4,6,8")
    args = parser.parse_args(argv)
    if args.command == "target-readiness":
        paths = WarehousePaths.from_data_root(Path(args.data_root))
        output = (target_readiness_for_specification(paths, MODEL_SPECIFICATIONS[args.model_specification])
                  if args.model_specification else target_readiness(paths))
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    if args.command == "build-target-panel":
        try:
            result = build_target_panel(WarehousePaths.from_data_root(Path(args.data_root)), property_type=args.property_type,
                                        target=args.target, frequency=args.frequency)
        except (OSError, ValueError) as exc:
            print(json.dumps({"status": "not_ready", "property_type": args.property_type, "target": args.target,
                              "frequency": args.frequency, "error": str(exc)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps({key: str(value) if isinstance(value, Path) else value for key, value in result.__dict__.items()},
                         indent=2, sort_keys=True))
        return 0
    if args.command == "reproduce":
        artifact_path = Path(args.artifact).resolve()
        if not artifact_path.is_file() or artifact_path.suffix.lower() != ".json":
            raise ValueError("reproduction artifact must be an existing JSON file")
        saved = json.loads(artifact_path.read_text(encoding="utf-8"))
        rows = _records(args.input)
        features = tuple(saved.get("model", {}).get("features", ()))
        target = saved.get("model", {}).get("target")
        if not target or not features or not saved.get("model_result_hash"):
            raise ValueError("saved model result lacks target, features, or result hash")
        panel = prepare_panel(rows, target=target, features=features, entity_column=args.entity,
                              time_column=args.time, required_property_type=args.property_type)
        diagnostics = saved["model"]["diagnostics"]
        reproduced = train_panel_candidate(
            panel, entity_fixed_effects=bool(diagnostics.get("entity_fixed_effects")),
            time_fixed_effects=bool(diagnostics.get("time_fixed_effects")),
            covariance=saved["model"]["covariance_type"],
            minimum_training_periods=saved["walk_forward"]["minimum_training_periods"],
            data_status=saved["governance"]["data_status"],
            source_manifest_hashes=tuple(saved.get("source_manifest_hashes", ())),
            target_dataset_hashes=tuple(saved.get("target_dataset_hashes", ())),
            feature_table_hash=saved.get("feature_table_hash"),
            feature_registry_version=saved.get("feature_registry_version"),
            model_specification=(MODEL_SPECIFICATIONS.get((saved.get("model_specification") or {}).get("name"))),
            model_mode=saved.get("governance", {}).get("model_mode", "ad_hoc_research"),
            code_commit=saved.get("code_commit"),
        )
        matches = reproduced["model_result_hash"] == saved["model_result_hash"]
        print(json.dumps({"status": "passed" if matches else "failed", "matches": matches,
                          "expected_hash": saved["model_result_hash"], "actual_hash": reproduced["model_result_hash"]},
                         indent=2, sort_keys=True))
        return 0 if matches else 1
    rows = _records(args.input)
    if args.command == "train":
        specification = MODEL_SPECIFICATIONS.get(args.model_specification)
        if args.model_mode != "ad_hoc_research" and specification is None:
            raise ValueError("governed candidate and production modes require --model-specification")
        if args.data_status == "real" and args.model_mode == "validated_production" and specification is None:
            raise ValueError("real production validation requires --model-specification")
        panel = prepare_panel(rows, target=args.target, features=_features(args.features), entity_column=args.entity,
                              time_column=args.time, required_property_type=args.property_type)
        result = train_panel_candidate(panel, entity_fixed_effects=not args.no_entity_effects,
                                       time_fixed_effects=not args.no_time_effects,
                                       minimum_training_periods=args.minimum_training_periods,
                                       data_status=args.data_status,
                                       source_manifest_hashes=tuple(args.source_manifest_hash),
                                       target_dataset_hashes=tuple(args.target_dataset_hash),
                                       feature_table_hash=args.feature_table_hash,
                                       feature_registry_version=args.feature_registry_version,
                                       model_specification=specification, model_mode=args.model_mode,
                                       code_commit=args.code_commit)
    else:
        lag_values = tuple(int(value.strip()) for value in args.lags.split(",") if value.strip())
        result = evaluate_candidate_lags(rows, target=args.target, feature=args.feature, lags=lag_values,
                                         minimum_training_periods=args.minimum_training_periods,
                                         entity_column=args.entity, time_column=args.time,
                                         required_property_type=args.property_type)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    if getattr(args, "output", None):
        output = Path(args.output).resolve()
        if output.suffix.lower() != ".json" or output.exists():
            raise ValueError("--output must be a new .json file")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
