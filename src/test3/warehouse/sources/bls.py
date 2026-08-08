from __future__ import annotations

import csv
import json
from decimal import Decimal

from .base import PublicDataRequest, PublicDataSource, RawSnapshot, canonical_row


class BLSLAUS(PublicDataSource):
    source_id, dataset_id, domain = "bls_laus_ces", "laus_county", "labor"
    allowed_hosts = ("download.bls.gov", "api.bls.gov")
    SERIES_SUFFIXES = {"03": ("unemployment_rate", "percent"), "04": ("unemployment", "persons"),
                       "05": ("employment", "persons"), "06": ("labor_force", "persons")}
    CHUNKS = ("00-04", "05-09", "10-14", "15-19", "20-24", "25-29", "90-94", "95-99")
    STATE_FILES = {
        "01":"7.Alabama","02":"8.Alaska","04":"9.Arizona","05":"10.Arkansas","06":"11.California","08":"12.Colorado",
        "09":"13.Connecticut","10":"14.Delaware","11":"15.DC","12":"16.Florida","13":"17.Georgia","15":"18.Hawaii",
        "16":"19.Idaho","17":"20.Illinois","18":"21.Indiana","19":"22.Iowa","20":"23.Kansas","21":"24.Kentucky",
        "22":"25.Louisiana","23":"26.Maine","24":"27.Maryland","25":"28.Massachusetts","26":"29.Michigan",
        "27":"30.Minnesota","28":"31.Mississippi","29":"32.Missouri","30":"33.Montana","31":"34.Nebraska",
        "32":"35.Nevada","33":"36.NewHampshire","34":"37.NewJersey","35":"38.NewMexico","36":"39.NewYork",
        "37":"40.NorthCarolina","38":"41.NorthDakota","39":"42.Ohio","40":"43.Oklahoma","41":"44.Oregon",
        "42":"45.Pennsylvania","72":"46.PuertoRico","44":"47.RhodeIsland","45":"48.SouthCarolina",
        "46":"49.SouthDakota","47":"50.Tennessee","48":"51.Texas","49":"52.Utah","50":"53.Vermont",
        "51":"54.Virginia","53":"56.Washington","54":"57.WestVirginia","55":"58.Wisconsin","56":"59.Wyoming",
    }
    NATIONAL_SERIES = {"LNS12000000": ("employment", "thousands_persons"),
                       "LNS11000000": ("labor_force", "thousands_persons"),
                       "LNS13000000": ("unemployment", "thousands_persons"),
                       "LNS14000000": ("unemployment_rate", "percent")}

    def discover(self, request: PublicDataRequest) -> list[str]:
        series = request.parameters.get("series")
        if series:
            if series not in self.NATIONAL_SERIES: raise ValueError("unsupported governed BLS national series")
            return [f"https://api.bls.gov/publicAPI/v1/timeseries/data/{series}"]
        state = request.parameters.get("state")
        if state:
            if state not in self.STATE_FILES: raise ValueError("unsupported BLS state FIPS")
            return [f"https://download.bls.gov/pub/time.series/la/la.data.{self.STATE_FILES[state]}"]
        chunk = request.parameters.get("chunk", "00-04")
        if chunk not in self.CHUNKS:
            raise ValueError("unsupported BLS bounded download chunk")
        return [f"https://download.bls.gov/pub/time.series/la/la.data.0.CurrentU{chunk}"]

    def normalize(self, snapshot: RawSnapshot):
        if "api.bls.gov" in snapshot.final_url:
            payload = json.loads(snapshot.content_path.read_text(encoding="utf-8-sig"))
            series_values = payload.get("Results", {}).get("series", []) if isinstance(payload, dict) else []
            if payload.get("status") != "REQUEST_SUCCEEDED" or len(series_values) != 1:
                raise ValueError("BLS public API response failed or changed schema")
            series_id = series_values[0].get("seriesID")
            if series_id not in self.NATIONAL_SERIES: raise ValueError("BLS returned an unexpected series")
            metric, unit = self.NATIONAL_SERIES[series_id]
            for row_number, raw in enumerate(series_values[0].get("data", []), 1):
                if raw.get("period") == "M13": continue
                month = int(str(raw["period"])[1:]); year = int(raw["year"])
                value = Decimal(str(raw["value"])) * 1000 if unit == "thousands_persons" else Decimal(str(raw["value"]))
                canonical_unit = "persons" if unit == "thousands_persons" else unit
                yield canonical_row(snapshot, series=series_id, geography_type="national", geography_id="US",
                                    observation_date=f"{year:04d}-{month:02d}", period_type="monthly", metric=metric,
                                    value=value, unit=canonical_unit, source_row=row_number, raw=raw,
                                    methodology="BLS CPS national series; published thousands converted to persons by deterministic x1000; seasonal adjustment retained by series ID.")
            return
        with snapshot.content_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            required = {"series_id", "year", "period", "value"}
            if not reader.fieldnames or not required.issubset({x.strip() for x in reader.fieldnames}):
                raise ValueError("BLS LAUS schema changed")
            for row_number, source in enumerate(reader, 2):
                raw = {str(key).strip(): str(value).strip() for key, value in source.items() if key is not None}
                if raw["period"] == "M13":
                    continue
                year = int(raw["year"])
                start, end = snapshot.request_parameters.get("from_year"), snapshot.request_parameters.get("to_year")
                if start and year < start or end and year > end:
                    continue
                series_id = raw["series_id"]
                match = self.SERIES_SUFFIXES.get(series_id[-2:])
                if not match or len(series_id) < 18 or not series_id.startswith("LAUCN"):
                    continue
                fips = series_id[5:10]
                month = int(raw["period"][1:])
                metric, unit = match
                yield canonical_row(snapshot, series=series_id, geography_type="county", geography_id=fips,
                                    observation_date=f"{year:04d}-{month:02d}", period_type="monthly", metric=metric,
                                    value=raw["value"], unit=unit, source_row=row_number, state_fips=fips[:2],
                                    county_fips=fips, raw=raw, methodology="BLS LAUS county series; preliminary/revised status remains in raw evidence.")
