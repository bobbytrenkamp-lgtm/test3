from __future__ import annotations

import argparse
from pathlib import Path

from test3.assumptions.public_sources import PUBLIC_SERIES, build_market_panel_csv, parse_bls_csv, parse_fred_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a manually downloaded, free official series into a local test3 market panel.")
    parser.add_argument("provider", choices=("FRED", "BLS"))
    parser.add_argument("series_id")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--source-reference", required=True)
    parser.add_argument("--property-type", default="mixed_use")
    args = parser.parse_args()
    definition = next((item for item in PUBLIC_SERIES if item.provider == args.provider and item.series_id == args.series_id), None)
    if definition is None:
        parser.error("series_id is not in the audited public-series catalog")
    content = args.input.read_bytes()
    parse = parse_fred_csv if args.provider == "FRED" else parse_bls_csv
    rows = parse(content, definition.series_id, definition.metric, definition.unit)
    converted = build_market_panel_csv(rows, source=f"{definition.provider} {definition.series_id}", source_date=args.source_date, source_reference=args.source_reference, usage_rights="Official public data; review provider terms and attribution requirements", property_type=args.property_type)
    args.output.write_bytes(converted)
    print(f"Prepared {len(rows)} observations at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
