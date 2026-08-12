from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
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
from test3.features.builder import build_feature_table
from test3.features.panel import FeaturePanel
from test3.cre_data.importer import cre_status, import_cre_file
from test3.cre_data.mappings import ImportMappingTemplate, load_mapping, save_mapping
from test3.cre_data.geography import MarketDefinition, save_market_definition
from test3.cre_data.schema import parse_cre_file
from test3.cre_data.sources import source_catalog
from test3.cre_data.sources import discovery_catalog
from test3.cre_data.audit import coverage_matrix, series_quality_scorecard, target_data_audit, target_readiness_funnel
from test3.cre_data.report_inbox import save_report_discovery
from test3.cre_data.report_tables import ReportMappingProfile, save_report_profile
from test3.cre_data.verification import available_as_of, verify_observations
from test3.cre_data.sources.sec_maa import write_review_csv
from test3.cre_data.review import approve_cre_review


PUBLIC_SOURCES = ("census", "bls", "bea", "fred", "building_permits", "crosswalk", "hud", "hvs")


def _parser():
    parser = argparse.ArgumentParser(prog="test3-data", description="Local, non-billable Test3 warehouse controls")
    parser.add_argument("--data-root", default="data")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("init", "create warehouse directories"), ("catalog", "emit governed sources"),
                            ("status", "verify versions and refresh history"), ("summary", "bounded DuckDB summary"),
                            ("coverage", "actual coverage by metric and geography")):
        commands.add_parser(name, help=help_text)
    features = commands.add_parser("build-features", help="build an immutable governed feature table")
    features.add_argument("--geography", choices=("county", "cbsa"), required=True)
    features.add_argument("--frequency", choices=("annual", "quarterly"), required=True)
    feature_status = commands.add_parser("feature-status", help="verify immutable feature-table versions")
    feature_status.add_argument("--table", choices=("county_year", "county_quarter", "cbsa_year", "cbsa_quarter"))
    refresh = commands.add_parser("refresh", help="download, preserve, normalize, validate and publish official data")
    refresh.add_argument("--source", choices=(*PUBLIC_SOURCES, "all"), required=True)
    refresh.add_argument("--from-year", type=int); refresh.add_argument("--to-year", type=int)
    refresh.add_argument("--geography", choices=("state", "county", "place")); refresh.add_argument("--dry-run", action="store_true")
    refresh.add_argument("--series", help="governed FRED series ID"); refresh.add_argument("--table", help="governed BEA table ID")
    refresh.add_argument("--variable", help="governed Census ACS variable ID")
    refresh.add_argument("--chunk", help="governed BLS series-suffix chunk")
    refresh.add_argument("--state", help="two-digit state FIPS for a bounded BLS state file")
    refresh.add_argument("--annual-county", action="store_true", help="use the official BLS annual county workbook")
    refresh.add_argument("--local-file", help="operator-downloaded official file for a source that blocks automation")
    refresh.add_argument("--source-url", help="exact allowed official HTTPS URL for --local-file evidence")
    refresh.add_argument("--vintage", default="2023", help="governed geography vintage")
    lineage = commands.add_parser("lineage", help="trace one observation to raw evidence and manifest")
    lineage.add_argument("observation_id")
    import_cre = commands.add_parser("import-cre", help="validate and publish versioned local CRE history (CSV/XLSX/Parquet)")
    import_cre.add_argument("--input", required=True); import_cre.add_argument("--dataset", required=True)
    import_cre.add_argument("--version", required=True); import_cre.add_argument("--evaluated-at")
    import_cre.add_argument("--mapping", help="saved immutable import-mapping JSON")
    import_cre.add_argument("--analyst-reviewed", action="store_true", help="explicitly accept file-declared analyst_verified rows")
    verify_cre = commands.add_parser("verify-cre", help="verify a local CRE target CSV/XLSX/Parquet without publishing it")
    verify_cre.add_argument("--input", required=True); verify_cre.add_argument("--evaluated-at"); verify_cre.add_argument("--forecast-origin")
    verify_cre.add_argument("--mapping", help="saved immutable import-mapping JSON")
    verify_cre.add_argument("--analyst-reviewed", action="store_true", help="explicitly accept file-declared analyst_verified rows")
    commands.add_parser("cre-status", help="report verified CRE target coverage and data-quality findings")
    commands.add_parser("cre-source-catalog", help="report governed institutional-target/proxy/context source classifications")
    commands.add_parser("cre-source-discovery", help="rank serious lawful CRE outcome source candidates")
    commands.add_parser("cre-target-audit", help="machine-readable audit of installed institutional targets and proxies")
    funnel = commands.add_parser("cre-target-funnel", help="show conservative target-readiness exclusion stages")
    funnel.add_argument("--property-type"); funnel.add_argument("--metric")
    matrix = commands.add_parser("cre-coverage-matrix", help="show actual market-by-period target coverage")
    matrix.add_argument("--property-type", required=True); matrix.add_argument("--metric", required=True)
    quality = commands.add_parser("cre-series-quality", help="show auditable active-vintage source-series quality components")
    quality.add_argument("--property-type"); quality.add_argument("--metric")
    discover = commands.add_parser("discover-cre-reports", help="fingerprint and group local, lawfully obtained CRE reports")
    discover.add_argument("--inbox", help="defaults to <data-root>/cre_reports/inbox")
    maa = commands.add_parser("parse-maa-sec-snapshots", help="parse official SEC MAA browser snapshots into an analyst-review CSV")
    maa.add_argument("--input-folder", required=True); maa.add_argument("--output", required=True)
    publish_maa = commands.add_parser("publish-maa-sec-candidates", help="publish unverified MAA SEC observations for analyst review")
    publish_maa.add_argument("--input", required=True); publish_maa.add_argument("--version", required=True)
    approve_review = commands.add_parser("approve-cre-review", help="create a hash-bound analyst-approved CRE review file")
    approve_review.add_argument("--input", required=True); approve_review.add_argument("--attestation", required=True)
    approve_review.add_argument("--output", required=True)
    bulk = commands.add_parser("import-cre-bulk", help="import multiple authorized CRE history files independently")
    bulk.add_argument("--input-folder", required=True); bulk.add_argument("--dataset-prefix", required=True)
    bulk.add_argument("--version-prefix", required=True); bulk.add_argument("--mapping")
    bulk.add_argument("--evaluated-at"); bulk.add_argument("--analyst-reviewed", action="store_true")
    save_cre_mapping = commands.add_parser("save-cre-mapping", help="validate and save a reusable local CRE import mapping")
    save_cre_mapping.add_argument("--definition", required=True, help="JSON mapping definition")
    save_market = commands.add_parser("save-market-definition", help="validate and save a versioned CRE market geography")
    save_market.add_argument("--definition", required=True, help="JSON market definition")
    save_profile = commands.add_parser("save-cre-report-profile", help="save an exact-schema recurring report mapping profile")
    save_profile.add_argument("--definition", required=True, help="JSON report profile definition")
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
    elif args.command == "import-cre":
        source = Path(args.input)
        output = asdict(import_cre_file(paths, source.read_bytes(), suffix=source.suffix,
                                        mapping=load_mapping(args.mapping) if args.mapping else None,
                                        dataset_id=args.dataset, source_version=args.version,
                                        evaluated_at=args.evaluated_at, analyst_review_confirmed=args.analyst_reviewed))
    elif args.command == "verify-cre":
        source = Path(args.input)
        records, errors, metadata = parse_cre_file(source.read_bytes(), suffix=source.suffix,
                                                   mapping=load_mapping(args.mapping) if args.mapping else None)
        checked = verify_observations(records, evaluated_at=args.evaluated_at, analyst_review_confirmed=args.analyst_reviewed)
        output = {"file": metadata, "invalid_rows": errors, "verification": checked,
                  "as_of_filter": available_as_of(checked["observations"], args.forecast_origin) if args.forecast_origin else None}
    elif args.command == "cre-status": output = cre_status(paths)
    elif args.command == "cre-source-catalog": output = source_catalog()
    elif args.command == "cre-source-discovery": output = discovery_catalog()
    elif args.command == "cre-target-audit": output = target_data_audit(paths)
    elif args.command == "cre-target-funnel": output = target_readiness_funnel(paths, property_type=args.property_type, metric=args.metric)
    elif args.command == "cre-coverage-matrix": output = coverage_matrix(paths, property_type=args.property_type, metric=args.metric)
    elif args.command == "cre-series-quality": output = series_quality_scorecard(paths, property_type=args.property_type, metric=args.metric)
    elif args.command == "discover-cre-reports":
        output = save_report_discovery(args.inbox or (Path(args.data_root) / "cre_reports" / "inbox"))
    elif args.command == "parse-maa-sec-snapshots":
        output = write_review_csv(args.input_folder, args.output)
    elif args.command == "publish-maa-sec-candidates":
        source = Path(args.input)
        output = asdict(import_cre_file(paths, source.read_bytes(), suffix=source.suffix,
                                        dataset_id="sec-maa-same-store-market-quarter",
                                        source_version=args.version, source_id="sec_maa",
                                        analyst_review_confirmed=False))
    elif args.command == "approve-cre-review":
        output = approve_cre_review(args.input, args.attestation, args.output)
    elif args.command == "import-cre-bulk":
        folder = Path(args.input_folder).resolve()
        if not folder.is_dir(): raise ValueError("bulk import folder does not exist")
        mapping = load_mapping(args.mapping) if args.mapping else None
        output = []
        for source in sorted(folder.iterdir()):
            if not source.is_file() or source.is_symlink() or source.suffix.lower() not in {".csv", ".xlsx", ".parquet"}:
                continue
            safe_stem = "".join(character.lower() if character.isalnum() else "-" for character in source.stem).strip("-")
            try:
                content = source.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()
                result = import_cre_file(paths, content, suffix=source.suffix, mapping=mapping,
                                         dataset_id=f"{args.dataset_prefix}-{safe_stem}",
                                         source_version=f"{args.version_prefix}-{content_hash[:12]}",
                                         evaluated_at=args.evaluated_at, analyst_review_confirmed=args.analyst_reviewed)
                output.append({"file": source.name, "status": "published", **asdict(result)})
            except (OSError, ValueError, FileExistsError) as exc:
                output.append({"file": source.name, "status": "failed", "error": str(exc)})
    elif args.command == "save-cre-mapping":
        payload = json.loads(Path(args.definition).read_text(encoding="utf-8"))
        payload["expected_columns"] = tuple(payload["expected_columns"])
        output = {"path": str(save_mapping(paths, ImportMappingTemplate(**payload))), "status": "saved"}
    elif args.command == "save-market-definition":
        payload = json.loads(Path(args.definition).read_text(encoding="utf-8"))
        payload["counties"] = tuple(payload["counties"])
        output = {"path": str(save_market_definition(paths, MarketDefinition(**payload))), "status": "saved"}
    elif args.command == "save-cre-report-profile":
        payload = json.loads(Path(args.definition).read_text(encoding="utf-8"))
        payload["expected_labels"] = tuple(payload["expected_labels"])
        payload["mappings"] = {key: tuple(value) for key, value in payload["mappings"].items()}
        output = {"path": str(save_report_profile(paths, ReportMappingProfile(**payload))), "status": "saved"}
    elif args.command == "build-features": output = asdict(build_feature_table(paths, geography=args.geography, frequency=args.frequency))
    elif args.command == "feature-status":
        tables = (args.table,) if args.table else ("county_year", "county_quarter", "cbsa_year", "cbsa_quarter")
        output = {table: FeaturePanel(paths, table).versions() for table in tables}
    else:
        targets = PUBLIC_SOURCES if args.source == "all" else (args.source,)
        output, failures = [], 0
        for source in targets:
            if source == "hud":
                end, start = args.to_year or datetime.now().year, args.from_year or 1983
            elif source == "hvs":
                end, start = args.to_year or datetime.now().year, args.from_year or 1956
            elif source in ("bea", "crosswalk", "fred"):
                end, start = args.to_year, args.from_year
            else:
                end = args.to_year or datetime.now().year - 1
                start = args.from_year or end
            if source == "fred": parameter_sets = [{"series": args.series}] if args.series else [{"series": item} for item in SERIES]
            elif source == "census": parameter_sets = [{"variable": args.variable}] if args.variable else [{"variable": item} for item in ACS_VARIABLES]
            elif source == "bls": parameter_sets = ([{"annual_county": "true", "local_file": args.local_file,
                                                         "source_url": args.source_url}] if args.local_file or args.annual_county else
                                                       [{"state": args.state}] if args.state else
                                                       [{"series": args.series}] if args.series else
                                                       [{"qcew_year": str(end)}])
            elif source == "bea": parameter_sets = [{"table": args.table}] if args.table else [{"table": item} for item in ("CAINC1", "CAGDP1")]
            elif source == "crosswalk": parameter_sets = [{"vintage": args.vintage}]
            elif source == "hud": parameter_sets = [{}]
            elif source == "hvs": parameter_sets = ([{"series": args.series}] if args.series else
                                                       [{"series": "rental_vacancy_rate"}, {"series": "median_asking_rent_vacant_units"}])
            else: parameter_sets = [{}]
            years = range(start, end + 1) if source in ("census", "building_permits") else (None,)
            for year in years:
                for parameters in parameter_sets:
                    request = PublicDataRequest("auto", year if year else start, year if year else end,
                                                args.geography, parameters)
                    try:
                        output.append(refresh_source(paths, source, request, dry_run=args.dry_run))
                    except Exception as exc:
                        failures += 1
                        output.append({"source": source, "status": "failed", "request": request.serializable(), "error": str(exc)})
    failed = ((args.command == "refresh" and failures) or
              (args.command == "import-cre-bulk" and any(item["status"] == "failed" for item in output)))
    print(json.dumps(output, indent=2, default=str, sort_keys=True)); return 1 if failed else 0


if __name__ == "__main__": raise SystemExit(main())
