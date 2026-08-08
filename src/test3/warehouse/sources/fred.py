from __future__ import annotations

import csv
from datetime import date

from .base import PublicDataRequest, PublicDataSource, RawSnapshot, canonical_row


SERIES = {
    "DFF": ("fed_funds_rate", "percent", "daily"), "SOFR": ("sofr", "percent", "daily"),
    "DGS2": ("treasury_2y", "percent", "daily"), "DGS5": ("treasury_5y", "percent", "daily"),
    "DGS10": ("treasury_10y", "percent", "daily"), "DGS30": ("treasury_30y", "percent", "daily"),
    "MORTGAGE30US": ("mortgage_rate", "percent", "weekly"), "CPIAUCSL": ("cpi", "index_1982_1984_100", "monthly"),
}


class FredPublic(PublicDataSource):
    source_id, dataset_id, domain = "fred_public", "macro_series", "capital_markets"
    allowed_hosts = ("fred.stlouisfed.org", "www.federalreserve.gov")

    def discover(self, request: PublicDataRequest) -> list[str]:
        series = request.parameters.get("series", "DGS10")
        if series not in SERIES:
            raise ValueError(f"unsupported governed macro series: {series}")
        if series == "DGS10":
            return ["https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bcb44e57fb57efbe90002369321bfb3f&lastObs=&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package"]
        return [f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"]

    def normalize(self, snapshot: RawSnapshot):
        series = snapshot.request_parameters["parameters"].get("series", "DGS10")
        metric, unit, frequency = SERIES[series]
        with snapshot.content_path.open(encoding="utf-8-sig", newline="") as stream:
            if "federalreserve.gov" in snapshot.final_url:
                rows = list(csv.reader(stream))
                header_index = next((index for index, row in enumerate(rows) if row and row[0].strip() == "Time Period"), None)
                if header_index is None or len(rows[header_index]) < 2:
                    raise ValueError("Federal Reserve H.15 CSV schema changed")
                for row_number, raw in enumerate(rows[header_index + 1:], header_index + 2):
                    if len(raw) < 2 or raw[1].strip() in ("", "ND"):
                        continue
                    observed = date.fromisoformat(raw[0].strip()).isoformat()
                    yield canonical_row(snapshot, series=series, geography_type="national", geography_id="US",
                                        observation_date=observed, period_type=frequency, metric=metric, value=raw[1].strip(),
                                        unit=unit, source_row=row_number, raw=raw,
                                        methodology="Original-frequency Federal Reserve Board H.15 series; no aggregation or interpolation.")
                return
            reader = csv.DictReader(stream)
            date_field = "observation_date" if reader.fieldnames and "observation_date" in reader.fieldnames else "DATE"
            if not reader.fieldnames or date_field not in reader.fieldnames or series not in reader.fieldnames:
                raise ValueError("Federal Reserve CSV schema changed")
            for row_number, raw in enumerate(reader, 2):
                value = raw[series].strip()
                if value in ("", "."):
                    continue
                observed = date.fromisoformat(raw[date_field]).isoformat()
                yield canonical_row(snapshot, series=series, geography_type="national", geography_id="US",
                                    observation_date=observed, period_type=frequency, metric=metric, value=value,
                                    unit=unit, source_row=row_number, raw=raw,
                                    methodology="Original-frequency public Federal Reserve series; no aggregation or interpolation.")
