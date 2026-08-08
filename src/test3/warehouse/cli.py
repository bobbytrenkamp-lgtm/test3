from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .catalog import SOURCE_CATALOG
from .duckdb_engine import WarehouseEngine
from .refresh import manifest_status
from .storage import WarehousePaths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test3-data", description="Local, non-billable Test3 warehouse controls")
    parser.add_argument("--data-root", default="data")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create the local warehouse directory structure")
    commands.add_parser("catalog", help="emit the governed source catalog as JSON")
    commands.add_parser("status", help="emit immutable dataset manifest status as JSON")
    commands.add_parser("summary", help="query a bounded warehouse summary with DuckDB")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = WarehousePaths.from_data_root(Path(args.data_root))
    if args.command == "init":
        paths.initialize()
        output = {"warehouse": str(paths.root), "status": "initialized"}
    elif args.command == "catalog":
        output = [asdict(SOURCE_CATALOG[key]) for key in sorted(SOURCE_CATALOG)]
    elif args.command == "status":
        output = manifest_status(paths)
    else:
        output = WarehouseEngine(paths).summary()
    print(json.dumps(output, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
