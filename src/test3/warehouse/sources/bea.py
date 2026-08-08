from __future__ import annotations

import csv
import io
import re
import zipfile

from .base import PublicDataRequest, PublicDataSource, RawSnapshot, canonical_row


TABLES = {
    "CAINC1": {"1": ("personal_income", "thousands_USD_current"), "2": ("population", "persons"),
                "3": ("personal_income_per_capita", "USD_current")},
    "CAGDP1": {"1": ("gdp", "thousands_USD_current")},
}


class BEARegional(PublicDataSource):
    source_id, dataset_id, domain = "bea_regional", "regional_accounts", "income"
    allowed_hosts = ("apps.bea.gov",)

    def discover(self, request: PublicDataRequest) -> list[str]:
        table = request.parameters.get("table", "CAINC1")
        if table not in TABLES:
            raise ValueError("BEA table must be CAINC1 or CAGDP1")
        return [f"https://apps.bea.gov/regional/zip/{table}.zip"]

    def normalize(self, snapshot: RawSnapshot):
        table = snapshot.request_parameters["parameters"].get("table", "CAINC1")
        with zipfile.ZipFile(snapshot.content_path) as archive:
            members = [name for name in archive.namelist() if name.upper().endswith(".CSV") and "ALL_AREAS" in name.upper()]
            if len(members) != 1:
                raise ValueError("BEA archive must contain exactly one all-areas table CSV")
            reader = csv.DictReader(io.TextIOWrapper(archive.open(members[0]), encoding="cp1252", newline=""))
            required = {"GeoFIPS", "LineCode", "Unit"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("BEA regional schema changed")
            for row_number, raw in enumerate(reader, 2):
                mapping = TABLES[table].get(str(raw["LineCode"]).strip())
                fips = re.sub(r"\D", "", raw["GeoFIPS"])
                if not mapping or len(fips) not in (2, 5):
                    continue
                metric, governed_unit = mapping
                for period, value in raw.items():
                    if not period.isdigit() or len(period) != 4:
                        continue
                    year = int(period)
                    start, end = snapshot.request_parameters.get("from_year"), snapshot.request_parameters.get("to_year")
                    if start and year < start or end and year > end or value.strip() in ("", "(NA)", "(D)"):
                        continue
                    cleaned = value.replace(",", "").strip()
                    is_state = len(fips) == 2 or (len(fips) == 5 and fips.endswith("000"))
                    geo_type, geo_id = ("state", fips[:2]) if is_state else ("county", fips)
                    yield canonical_row(snapshot, series=f"{table}:{raw['LineCode']}", geography_type=geo_type,
                                        geography_id=geo_id, observation_date=period, period_type="annual", metric=metric,
                                        value=cleaned, unit=governed_unit, source_row=row_number,
                                        state_fips=fips[:2], county_fips=fips if len(fips) == 5 and not is_state else None, raw={"period": period, **raw},
                                        methodology=f"BEA regional table {table}; original unit={raw['Unit']}; scaling preserved in canonical unit.")
