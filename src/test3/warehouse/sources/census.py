from __future__ import annotations

import json
import csv

from .base import PublicDataRequest, PublicDataSource, RawSnapshot, canonical_row


ACS_VARIABLES = {
    "B01003_001E": ("population", "persons"), "B11001_001E": ("households", "households"),
    "B19013_001E": ("median_household_income", "USD_current"), "B19301_001E": ("per_capita_income", "USD_current"),
    "B25001_001E": ("housing_units", "units"), "B25002_002E": ("occupied_housing_units", "units"),
    "B25002_003E": ("vacant_housing_units", "units"), "B25010_001E": ("average_household_size", "persons_per_household"),
    "B23001_001E": ("working_age_population_universe", "persons"), "B15003_022E": ("bachelors_degree_population", "persons"),
}


class CensusACS(PublicDataSource):
    source_id, dataset_id, domain = "census_acs", "acs5_profile", "demographics"
    allowed_hosts = ("www2.census.gov",)

    def discover(self, request: PublicDataRequest) -> list[str]:
        year = request.to_year or request.from_year
        if year is None or not 2009 <= year <= 2100:
            raise ValueError("Census ACS refresh requires one --to-year (2009 or later)")
        geography = request.geography or "county"
        if geography not in {"state", "county", "place"}:
            raise ValueError("Census geography must be state, county, or place")
        variable = request.parameters.get("variable", "B01003_001E")
        if variable not in ACS_VARIABLES:
            raise ValueError("unsupported governed ACS variable")
        table = variable.split("_", 1)[0].lower()
        return [f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}/table-based-SF/data/5YRData/acsdt5y{year}-{table}.dat"]

    def normalize(self, snapshot: RawSnapshot):
        text = snapshot.content_path.read_text(encoding="utf-8-sig")
        # API-shaped JSON remains supported for validated legacy/manual snapshots.
        if text.lstrip().startswith("["):
            payload = json.loads(text)
            if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[0], list):
                raise ValueError("Census response must contain a header and data rows")
            headers, source_rows = payload[0], payload[1:]
            missing = set(ACS_VARIABLES) - set(headers)
            if missing: raise ValueError(f"Census schema changed; missing variables: {sorted(missing)}")
            iterator = (dict(zip(headers, values, strict=True)) for values in source_rows)
            api_shape = True
        else:
            reader = csv.DictReader(text.splitlines(), delimiter="|")
            variable = snapshot.request_parameters["parameters"].get("variable", "B01003_001E")
            estimate = variable.split("_")[0] + "_E" + variable.split("_")[1][:-1]
            if not reader.fieldnames or "GEO_ID" not in reader.fieldnames or estimate not in reader.fieldnames:
                raise ValueError("Census table-based summary-file schema changed")
            iterator, api_shape = reader, False
        year = str(snapshot.request_parameters["to_year"] or snapshot.request_parameters["from_year"])
        requested_geo = snapshot.request_parameters.get("geography") or "county"
        for row_number, raw in enumerate(iterator, 2):
            if api_shape:
                state, county = raw.get("state"), raw.get("county")
                if county is not None: geo_type, geo_id, county_fips = "county", state + county, state + county
                elif raw.get("place") is not None: geo_type, geo_id, county_fips = "place", state + raw["place"], None
                else: geo_type, geo_id, county_fips = "state", state, None
                variables = ACS_VARIABLES.items()
            else:
                prefixes = {"state": "0400000US", "county": "0500000US", "place": "1600000US"}
                geo = raw["GEO_ID"]
                if not geo.startswith(prefixes[requested_geo]): continue
                geo_id = geo.removeprefix(prefixes[requested_geo]); geo_type = requested_geo
                state, county_fips = geo_id[:2], geo_id if geo_type == "county" else None
                variable = snapshot.request_parameters["parameters"].get("variable", "B01003_001E")
                estimate = variable.split("_")[0] + "_E" + variable.split("_")[1][:-1]
                raw[variable] = raw[estimate]; variables = ((variable, ACS_VARIABLES[variable]),)
            for variable, (metric, unit) in variables:
                value = raw.get(variable)
                if value in (None, "", "null") or float(value) < -1e8:
                    continue
                yield canonical_row(snapshot, series=variable, geography_type=geo_type, geography_id=geo_id,
                                    observation_date=year, period_type="annual", metric=metric, value=value, unit=unit,
                                    source_row=row_number, state_fips=state, county_fips=county_fips,
                                    methodology="ACS 5-year estimate; estimate is not a single-year point measurement.", raw={"variable": variable, **raw})
