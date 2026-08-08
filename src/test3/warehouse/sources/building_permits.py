from __future__ import annotations

import csv
import re

from .base import PublicDataRequest, PublicDataSource, RawSnapshot, canonical_row


FIELDS = {
    "total_units": ("units_authorized_total", "units"), "units_1": ("single_family_units_authorized", "units"),
    "units_2_to_4": ("multifamily_2_to_4_units_authorized", "units"),
    "units_5_plus": ("multifamily_5_plus_units_authorized", "units"), "total_permits": ("residential_permits_total", "permits"),
}


class CensusBuildingPermits(PublicDataSource):
    source_id, dataset_id, domain = "census_bps", "annual_county", "construction"
    allowed_hosts = ("www2.census.gov",)

    def discover(self, request: PublicDataRequest) -> list[str]:
        year = request.to_year or request.from_year
        if year is None or not 1980 <= year <= 2100:
            raise ValueError("Building Permits refresh requires one --to-year")
        return [f"https://www2.census.gov/econ/bps/County/co{year}a.txt"]

    def normalize(self, snapshot: RawSnapshot):
        text = snapshot.content_path.read_text(encoding="latin-1")
        year = str(snapshot.request_parameters["to_year"] or snapshot.request_parameters["from_year"])
        # A governed canonical CSV is also accepted for official manually downloaded snapshots.
        if text.lstrip().lower().startswith("state_fips,"):
            reader = csv.DictReader(text.splitlines())
            if not reader.fieldnames or not {"state_fips", "county_fips", *FIELDS}.issubset(reader.fieldnames):
                raise ValueError("Building Permits canonical source schema changed")
            for row_number, raw in enumerate(reader, 2):
                fips = raw["state_fips"].zfill(2) + raw["county_fips"].zfill(3)
                yield from self._values(snapshot, raw, row_number, fips, year)
            return
        # Official annual county files use two header rows, then structure-specific building/unit/value triplets.
        found = 0
        for row_number, values in enumerate(csv.reader(text.splitlines()), 1):
            if len(values) < 18 or not values[0].strip().isdigit() or not values[1].strip().isdigit() or not values[2].strip().isdigit():
                continue
            state, county = values[1].strip().zfill(2), values[2].strip().zfill(3)
            if state == "00" or county == "000":
                continue
            number = lambda index: int(values[index].strip() or 0)
            raw = {"total_permits": str(number(6) + number(9) + number(12) + number(15)),
                   "total_units": str(number(7) + number(10) + number(13) + number(16)),
                   "units_1": str(number(7)), "units_2_to_4": str(number(10) + number(13)),
                   "units_5_plus": str(number(16)), "source_line": ",".join(values)}
            found += 1
            yield from self._values(snapshot, raw, row_number, state + county, year)
        if found == 0:
            raise ValueError("Building Permits fixed-width schema changed or contains no county rows")

    def _values(self, snapshot, raw, row_number, fips, year):
        for field, (metric, unit) in FIELDS.items():
            value = raw.get(field, "").replace(",", "").strip()
            if value:
                yield canonical_row(snapshot, series=field, geography_type="county", geography_id=fips,
                                    observation_date=year, period_type="annual", metric=metric, value=value,
                                    unit=unit, source_row=row_number, state_fips=fips[:2], county_fips=fips, raw={"field": field, **raw})
