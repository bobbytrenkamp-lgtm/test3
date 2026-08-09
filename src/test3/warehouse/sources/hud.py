from __future__ import annotations

import csv
import re

from .base import PublicDataRequest, PublicDataSource, RawSnapshot, canonical_row


class HUDFairMarketRents(PublicDataSource):
    """HUD's credential-free 1983-present Fair Market Rent history file."""

    source_id, dataset_id, domain = "hud_public", "fair_market_rents_history", "rent"
    allowed_hosts = ("www.huduser.gov", "huduser.gov")
    HISTORY_URL = "https://www.huduser.gov/portal/datasets/FMR/FMR_All_1983_2026.csv"
    BEDROOMS = {"0": "studio", "1": "one_bedroom", "2": "two_bedroom", "3": "three_bedroom", "4": "four_bedroom"}

    def discover(self, request: PublicDataRequest) -> list[str]:
        return [self.HISTORY_URL]

    @staticmethod
    def _year(two_digit: str) -> int:
        value = int(two_digit)
        return 1900 + value if value >= 83 else 2000 + value

    def normalize(self, snapshot: RawSnapshot):
        with snapshot.content_path.open(encoding="cp1252", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or ())
            required = {"fips", "state", "county", "cousub", "name"}
            if not required.issubset(fields):
                raise ValueError("HUD FMR history schema changed")
            rent_fields = []
            for field in reader.fieldnames or ():
                if match := re.fullmatch(r"fmr(\d{2})_([0-4])", field):
                    rent_fields.append((field, self._year(match.group(1)), match.group(2)))
            if not rent_fields:
                raise ValueError("HUD FMR history contains no governed bedroom rent fields")
            for row_number, raw in enumerate(reader, 2):
                state = str(raw.get("state") or "").zfill(2)
                county = str(raw.get("county") or "").zfill(3)
                subdivision = str(raw.get("cousub") or "").zfill(5)
                if not (state.isdigit() and county.isdigit() and subdivision.isdigit()
                        and len(state) == 2 and len(county) == 3 and len(subdivision) == 5):
                    continue
                county_fips = state + county
                is_subdivision = subdivision != "99999"
                geography_id = county_fips + subdivision if is_subdivision else county_fips
                geography_type = "county_subdivision" if is_subdivision else "county"
                for field, year, bedroom in rent_fields:
                    start, end = snapshot.request_parameters.get("from_year"), snapshot.request_parameters.get("to_year")
                    if start and year < start or end and year > end:
                        continue
                    value = str(raw.get(field) or "").replace("$", "").replace(",", "").strip()
                    if not value or value.upper() in {"NA", "N/A", "N.A."}:
                        continue
                    source_area = str(raw.get(f"msa{year % 100:02d}") or raw.get("fips") or geography_id)
                    evidence = {
                        "field": field, "value": raw.get(field), "area_code": source_area,
                        "area_name": raw.get(f"areaname{year % 100:02d}") or raw.get("name"),
                        "state_fips": state, "county_fips": county_fips,
                        "county_subdivision_fips": subdivision if is_subdivision else None,
                    }
                    yield canonical_row(
                        snapshot, series=f"HUD_FMR_FY{year}_{source_area}_{bedroom}BR",
                        geography_type=geography_type, geography_id=geography_id,
                        observation_date=str(year), period_type="annual", metric="fair_market_rent",
                        value=value, unit="USD_per_month", source_row=row_number, state_fips=state,
                        county_fips=county_fips, raw=evidence, quality_level="high",
                        methodology=("HUD fiscal-year Fair Market Rent: estimated 40th-percentile monthly gross rent "
                                     "for a standard-quality unit. County subdivisions remain distinct and are never collapsed to counties."),
                    ) | {"property_type": "multifamily", "property_subtype": self.BEDROOMS[bedroom]}
