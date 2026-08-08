from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from datetime import datetime

from .catalog import SOURCE_CATALOG
from .duckdb_engine import WarehouseEngine
from .lineage import observation_lineage
from .refresh import manifest_status, refresh_source
from .reporting import coverage_report
from .sources import PublicDataRequest
from .sources.fred import SERIES
from .sources.census import ACS_VARIABLES
from .sources.bls import BLSLAUS
from .storage import WarehousePaths


PUBLIC_SOURCES = ("census", "bls", "bea", "fred", "building_permits")


def _parser():
    parser = argparse.ArgumentParser(prog="test3-data", description="Local, non-billable Test3 warehouse controls")
    parser.add_argument("--data-root", default="data")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("init", "create warehouse directories"), ("catalog", "emit governed sources"),
                            ("status", "verify versions and refresh history"), ("summary", "bounded DuckDB summary"),
                            ("coverage", "actual coverage by metric and geography")):
        commands.add_parser(name, help=help_text)
    refresh = commands.add_parser("refresh", help="download, preserve, normalize, validate and publish official data")
    refresh.add_argument("--source", choices=(*PUBLIC_SOURCES, "all"), required=True)
    refresh.add_argument("--from-year", type=int); refresh.add_argument("--to-year", type=int)
    refresh.add_argument("--geography", choices=("state", "county", "place")); refresh.add_argument("--dry-run", action="store_true")
    refresh.add_argument("--series", help="governed FRED series ID"); refresh.add_argument("--table", help="governed BEA table ID")
    refresh.add_argument("--variable", help="governed Census ACS variable ID")
    refresh.add_argument("--chunk", help="governed BLS series-suffix chunk")
    refresh.add_argument("--state", help="two-digit state FIPS for a bounded BLS state file")
    lineage = commands.add_parser("lineage", help="trace one observation to raw evidence and manifest")
    lineage.add_argument("observation_id")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    paths = WarehousePaths.from_data_root(Path(args.data_root))
    if args.command == "init": paths.initialize(); output = {"warehouse": str(paths.root), "status": "initialized"}
    elif args.command == "catalog": output = [asdict(SOURCE_CATALOG[key]) for key in sorted(SOURCE_CATALOG)]
    elif args.command == "status": output = manifest_status(paths)
    elif args.command == "summary": output = WarehouseEngine(paths).summary()
    elif args.command == "coverage": output = coverage_report(paths)
    elif args.command == "lineage": output = observation_lineage(paths, args.observation_id)
    else:
        targets = PUBLIC_SOURCES if args.source == "all" else (args.source,)
        output = []
        for source in targets:
            end = args.to_year or datetime.now().year - 1
            start = args.from_year or end
            if source == "fred": parameter_sets = [{"series": args.series}] if args.series else [{"series": item} for item in SERIES]
            elif source == "census": parameter_sets = [{"variable": args.variable}] if args.variable else [{"variable": item} for item in ACS_VARIABLES]
            elif source == "bls": parameter_sets = ([{"state": args.state}] if args.state else
                                                       [{"series": args.series}] if args.series else
                                                       [{"series": item} for item in BLSLAUS.NATIONAL_SERIES])
            elif source == "bea": parameter_sets = [{"table": args.table}] if args.table else [{"table": item} for item in ("CAINC1", "CAGDP1")]
            else: parameter_sets = [{}]
            years = range(start, end + 1) if source in ("census", "building_permits") else (None,)
            for year in years:
                for parameters in parameter_sets:
                    request = PublicDataRequest("auto", year if year else args.from_year, year if year else args.to_year,
                                                args.geography, parameters)
                    output.append(refresh_source(paths, source, request, dry_run=args.dry_run))
    print(json.dumps(output, indent=2, default=str, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
