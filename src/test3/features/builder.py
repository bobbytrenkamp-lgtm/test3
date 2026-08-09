from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import uuid

import duckdb

from test3.warehouse.duckdb_engine import sql_literal
from test3.warehouse.manifests import active_manifests, canonical_json
from test3.warehouse.storage import WarehousePaths

from .manifests import FEATURE_MANIFEST_VERSION, feature_file_entry, verify_feature_manifest, write_feature_manifest
from .quality import profile_feature_files
from .registry import FEATURE_REGISTRY, FeatureSpec, registry_fingerprint, specs_for


BUILDER_VERSION = "1.4.0"
LINEAGE_SCHEMA = """
lineage_id VARCHAR NOT NULL, feature_name VARCHAR NOT NULL, geography_type VARCHAR NOT NULL,
geography_id VARCHAR NOT NULL, state_fips VARCHAR, county_fips VARCHAR, cbsa VARCHAR,
period_start DATE NOT NULL, period_type VARCHAR NOT NULL, value DOUBLE NOT NULL, unit VARCHAR NOT NULL,
transformation VARCHAR NOT NULL, feature_version VARCHAR NOT NULL,
input_observation_ids_json VARCHAR NOT NULL, input_feature_lineage_ids_json VARCHAR NOT NULL,
input_manifest_hashes_json VARCHAR NOT NULL, available_at DATE NOT NULL, quality_level VARCHAR NOT NULL
"""


@dataclass(frozen=True)
class FeatureBuildResult:
    table_name: str
    feature_table_version: str
    status: str
    panel_path: Path
    lineage_path: Path
    manifest_path: Path
    row_count: int
    feature_value_count: int
    manifest_hash: str


def _table_name(geography: str, frequency: str) -> str:
    if geography not in {"county", "cbsa"}:
        raise ValueError("Milestone 3A supports county and CBSA feature tables")
    if frequency not in {"annual", "quarterly"}:
        raise ValueError("Milestone 3A supports annual and quarterly feature tables")
    return f"{geography}_{'year' if frequency == 'annual' else 'quarter'}"


def _interval(frequency: str, periods: int) -> str:
    return f"INTERVAL '{periods} year'" if frequency == "annual" else f"INTERVAL '{periods * 3} month'"


def _source_specs(frequency: str, geography: str) -> tuple[FeatureSpec, ...]:
    return tuple(spec for spec in specs_for(frequency, geography) if spec.transformation == "source_last_observation")


def _required_sources(frequency: str, geography: str) -> set[str]:
    sources = {source for spec in specs_for(frequency, geography) for source in spec.source_ids}
    if geography == "cbsa":
        sources.add("census_cbsa_crosswalk")
    return sources


def _upstream_source_ids(feature_name: str, seen: set[str] | None = None) -> set[str]:
    visited = set() if seen is None else seen
    if feature_name in visited:
        raise ValueError(f"feature registry contains a dependency cycle at {feature_name}")
    visited.add(feature_name)
    spec = FEATURE_REGISTRY[feature_name]
    result = set(spec.source_ids)
    for parent in spec.input_features:
        result.update(_upstream_source_ids(parent, visited.copy()))
    return result


def _requires_cbsa_crosswalk(feature_name: str) -> bool:
    spec = FEATURE_REGISTRY[feature_name]
    return spec.cbsa_aggregation == "sum" or any(_requires_cbsa_crosswalk(parent) for parent in spec.input_features)


def _feature_definitions(frequency: str, geography: str, manifests: list[dict]) -> list[dict]:
    output = []
    for spec in specs_for(frequency, geography):
        sources = _upstream_source_ids(spec.name)
        if geography == "cbsa" and _requires_cbsa_crosswalk(spec.name):
            sources.add("census_cbsa_crosswalk")
        versions = [{"source_id": item["source_id"], "dataset_id": item["dataset_id"],
                     "source_version": item["source_version"], "manifest_hash": item["manifest_hash"]}
                    for item in manifests if item["source_id"] in sources]
        output.append({**asdict(spec), "input_dataset_versions": sorted(versions, key=lambda item: (item["source_id"], item["dataset_id"], item["source_version"]))})
    return output


def _manifest_source(connection: duckdb.DuckDBPyConnection, manifests: list[dict]) -> None:
    connection.execute("CREATE TEMP TABLE manifest_map(source_id VARCHAR,source_dataset VARCHAR,source_version VARCHAR,manifest_hash VARCHAR)")
    connection.executemany("INSERT INTO manifest_map VALUES(?,?,?,?)", [
        (item["source_id"], item["dataset_id"], item["source_version"], item["manifest_hash"]) for item in manifests
    ])
    files = [str(path) for item in manifests for path in item["resolved_files"]]
    source = "read_parquet([" + ",".join(sql_literal(item) for item in files) + "], union_by_name=true)"
    connection.execute(f"""CREATE TEMP VIEW source_observations AS
        SELECT observations.*,manifest_map.manifest_hash AS source_manifest_hash
        FROM {source} observations JOIN manifest_map
          ON observations.source_id=manifest_map.source_id
         AND observations.source_dataset=manifest_map.source_dataset
         AND observations.source_version=manifest_map.source_version""")


def _where(spec: FeatureSpec) -> str:
    sources = ",".join(sql_literal(item) for item in spec.source_ids)
    result = f"metric={sql_literal(spec.input_metrics[0])} AND source_id IN ({sources}) AND geography_type='county' AND period_type='annual'"
    if spec.property_subtype:
        result += f" AND property_subtype={sql_literal(spec.property_subtype)}"
    return result


def _insert_source_feature(connection: duckdb.DuckDBPyConnection, spec: FeatureSpec, frequency: str) -> None:
    where = _where(spec)
    conflicts = connection.execute(f"""SELECT count(*) FROM (
        SELECT geography_id,year(observation_date),count(DISTINCT
            CAST(value AS VARCHAR) || '|' || unit || '|' || source_series || '|' || source_dataset || '|' || source_version) variants
        FROM source_observations WHERE {where} GROUP BY geography_id,year(observation_date) HAVING variants>1)""").fetchone()[0]
    if conflicts:
        raise ValueError(f"ambiguous source observations for governed feature {spec.name}: {conflicts} conflicting duplicate keys")
    if frequency == "annual":
        period = "make_date(observation_year,1,1)"
        expansion = ""
        transformation = "source_last_observation; original_frequency=annual"
    else:
        period = "make_date(observation_year,quarter_month,1)"
        expansion = "CROSS JOIN (VALUES (1),(4),(7),(10)) quarters(quarter_month)"
        transformation = "annual_carry_forward; original_frequency=annual; no interpolation"
    name, unit = sql_literal(spec.name), sql_literal(spec.unit)
    version, transform = sql_literal(spec.version), sql_literal(transformation)
    connection.execute(f"""INSERT INTO feature_values
        SELECT sha256({name} || '|' || geography_id || '|' || CAST({period} AS VARCHAR) || '|' || observation_ids),
               {name},'county',geography_id,state_fips,county_fips,cbsa,{period},
               {sql_literal(frequency)},feature_value,{unit},
               {transform} || CASE WHEN duplicate_count>1 THEN '; exact_duplicate_collapse=' || CAST(duplicate_count AS VARCHAR) ELSE '' END,
               {version},observation_ids,'[]',manifest_hashes,available_at,quality_level
        FROM (SELECT geography_id,any_value(state_fips) state_fips,any_value(county_fips) county_fips,
                     any_value(cbsa) cbsa,year(observation_date) observation_year,any_value(CAST(value AS DOUBLE)) feature_value,
                     CAST(to_json(list(observation_id ORDER BY observation_id)) AS VARCHAR) observation_ids,
                     CAST(to_json(list(DISTINCT source_manifest_hash ORDER BY source_manifest_hash)) AS VARCHAR) manifest_hashes,
                     count(*) duplicate_count,max(as_of_date) available_at,
                     CASE WHEN count(*) FILTER (WHERE quality_level='low')>0 THEN 'low'
                          WHEN count(*) FILTER (WHERE quality_level='moderate')>0 THEN 'moderate' ELSE 'high' END quality_level
              FROM source_observations WHERE {where} GROUP BY geography_id,year(observation_date)) grouped
        {expansion}""")


def _create_crosswalk(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("""CREATE TEMP TABLE current_crosswalk AS
        SELECT county_fips,cbsa,observation_id,source_manifest_hash,observation_date,as_of_date,source_version
        FROM source_observations
        WHERE metric='county_cbsa_membership' AND geography_type='county' AND cbsa IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY county_fips ORDER BY observation_date DESC,source_version DESC)=1""")


def _aggregate_cbsa(connection: duckdb.DuckDBPyConnection, frequency: str) -> None:
    _create_crosswalk(connection)
    for spec in _source_specs(frequency, "cbsa"):
        if spec.cbsa_aggregation != "sum":
            continue
        feature = sql_literal(spec.name)
        transformation = sql_literal("source_backed_county_to_cbsa_sum; explicit current OMB vintage; no inferred market boundary")
        connection.execute(f"""INSERT INTO feature_values
            SELECT sha256({feature} || '|' || crosswalk.cbsa || '|' || CAST(values_.period_start AS VARCHAR) || '|' ||
                          string_agg(values_.lineage_id,'' ORDER BY values_.lineage_id)),
                   {feature},'cbsa',crosswalk.cbsa,NULL,NULL,crosswalk.cbsa,values_.period_start,{sql_literal(frequency)},
                   sum(values_.value),{sql_literal(spec.unit)},{transformation},{sql_literal(spec.version)},
                   CAST(to_json(list(DISTINCT crosswalk.observation_id ORDER BY crosswalk.observation_id)) AS VARCHAR),
                   CAST(to_json(list(values_.lineage_id ORDER BY values_.lineage_id)) AS VARCHAR),
                   CAST(to_json(list(DISTINCT crosswalk.source_manifest_hash ORDER BY crosswalk.source_manifest_hash)) AS VARCHAR),
                   greatest(max(values_.available_at),max(crosswalk.as_of_date)),
                   CASE WHEN count(*) FILTER (WHERE values_.quality_level='low')>0 THEN 'low'
                        WHEN count(*) FILTER (WHERE values_.quality_level='moderate')>0 THEN 'moderate' ELSE 'high' END
            FROM feature_values values_ JOIN current_crosswalk crosswalk USING(county_fips)
            WHERE values_.geography_type='county' AND values_.feature_name={feature}
            GROUP BY crosswalk.cbsa,values_.period_start""")


def _insert_macro(connection: duckdb.DuckDBPyConnection, spec: FeatureSpec, geography: str, frequency: str) -> None:
    period = "make_date(year(observation_date),1,1)" if frequency == "annual" else "date_trunc('quarter',observation_date)::DATE"
    metric, sources = sql_literal(spec.input_metrics[0]), ",".join(sql_literal(item) for item in spec.source_ids)
    temp = "macro_" + spec.name
    if spec.transformation == "period_mean_broadcast":
        connection.execute(f"""CREATE TEMP TABLE {temp} AS SELECT {period} AS period_start,avg(CAST(value AS DOUBLE)) AS feature_value,
            CAST(to_json(list(observation_id ORDER BY observation_date,observation_id)) AS VARCHAR) observation_ids,
            CAST(to_json(list(DISTINCT source_manifest_hash ORDER BY source_manifest_hash)) AS VARCHAR) manifest_hashes,
            max(as_of_date) available_at,
            CASE WHEN count(*) FILTER (WHERE quality_level='low')>0 THEN 'low'
                 WHEN count(*) FILTER (WHERE quality_level='moderate')>0 THEN 'moderate' ELSE 'high' END quality_level
            FROM source_observations WHERE metric={metric} AND source_id IN ({sources}) GROUP BY 1""")
    else:
        connection.execute(f"""CREATE TEMP TABLE {temp} AS SELECT {period} AS period_start,
            arg_max(CAST(value AS DOUBLE),observation_date) AS feature_value,
            CAST(to_json(list_value(arg_max(observation_id,observation_date))) AS VARCHAR) observation_ids,
            CAST(to_json(list_value(arg_max(source_manifest_hash,observation_date))) AS VARCHAR) manifest_hashes,
            arg_max(as_of_date,observation_date) available_at,arg_max(quality_level,observation_date) quality_level
            FROM source_observations WHERE metric={metric} AND source_id IN ({sources}) GROUP BY 1""")
    name = sql_literal(spec.name)
    connection.execute(f"""INSERT INTO feature_values
        SELECT sha256({name} || '|US|' || CAST(macro.period_start AS VARCHAR) || '|' || macro.observation_ids),
               {name},'national','US',NULL,NULL,NULL,macro.period_start,{sql_literal(frequency)},macro.feature_value,
               {sql_literal(spec.unit)},{sql_literal(spec.transformation + '; original-frequency national aggregation')},
               {sql_literal(spec.version)},macro.observation_ids,'[]',macro.manifest_hashes,macro.available_at,macro.quality_level
        FROM {temp} macro""")
    connection.execute(f"""INSERT INTO feature_values
        SELECT sha256({name} || '|' || spine.geography_id || '|' || CAST(national.period_start AS VARCHAR) || '|' || national.lineage_id),
               {name},{sql_literal(geography)},spine.geography_id,spine.state_fips,spine.county_fips,spine.cbsa,
               national.period_start,{sql_literal(frequency)},national.value,{sql_literal(spec.unit)},
               {sql_literal('national_broadcast; explicit geography-period spine; value is not a local observation')},
               {sql_literal(spec.version)},'[]',CAST(to_json(list_value(national.lineage_id)) AS VARCHAR),'[]',national.available_at,national.quality_level
        FROM feature_values national JOIN (SELECT DISTINCT geography_id,state_fips,county_fips,cbsa,period_start
                                           FROM feature_values WHERE geography_type={sql_literal(geography)}) spine USING(period_start)
        WHERE national.geography_type='national' AND national.feature_name={name}""")


def _insert_derived(connection: duckdb.DuckDBPyConnection, spec: FeatureSpec, geography: str, frequency: str) -> None:
    current_name, output_name = sql_literal(spec.input_features[0]), sql_literal(spec.name)
    if spec.transformation == "ratio_per_1000":
        right = sql_literal(spec.input_features[1])
        formula = "left_.value / right_.value * 1000.0"
        condition = "right_.value<>0"
        join = f"JOIN feature_values right_ ON left_.geography_type=right_.geography_type AND left_.geography_id=right_.geography_id AND left_.period_start=right_.period_start AND right_.feature_name={right}"
        inputs = "CAST(to_json(list_value(left_.lineage_id,right_.lineage_id)) AS VARCHAR)"
        transformation = "ratio_per_1000; exact matching period; no missing-value substitution"
        quality = "CASE WHEN left_.quality_level='low' OR right_.quality_level='low' THEN 'low' WHEN left_.quality_level='moderate' OR right_.quality_level='moderate' THEN 'moderate' ELSE 'high' END"
    else:
        if spec.transformation in {"growth", "difference"}:
            lag = 1 if frequency == "annual" else 4
        elif spec.transformation == "cagr":
            lag = spec.lag_periods if frequency == "annual" else spec.lag_periods * 4
        else:
            raise ValueError(f"unsupported derived transformation: {spec.transformation}")
        join = f"JOIN feature_values prior ON current_.geography_type=prior.geography_type AND current_.geography_id=prior.geography_id AND prior.period_start=current_.period_start-{_interval(frequency, lag)} AND prior.feature_name={current_name}"
        condition = "prior.value<>0"
        if spec.transformation == "growth": formula = "current_.value/prior.value-1.0"
        elif spec.transformation == "cagr":
            formula = f"power(current_.value/prior.value,1.0/{spec.lag_periods})-1.0"; condition += " AND current_.value/prior.value>0"
        else: formula = "current_.value-prior.value"; condition = "TRUE"
        inputs = "CAST(to_json(list_value(prior.lineage_id,current_.lineage_id)) AS VARCHAR)"
        transformation = f"{spec.transformation}; exact lag={lag} {frequency} period(s); missing periods omitted"
        quality = "CASE WHEN current_.quality_level='low' OR prior.quality_level='low' THEN 'low' WHEN current_.quality_level='moderate' OR prior.quality_level='moderate' THEN 'moderate' ELSE 'high' END"
    left_alias = "left_" if spec.transformation == "ratio_per_1000" else "current_"
    connection.execute(f"""INSERT INTO feature_values
        SELECT sha256({output_name} || '|' || {left_alias}.geography_id || '|' || CAST({left_alias}.period_start AS VARCHAR) || '|' || {inputs}),
               {output_name},{left_alias}.geography_type,{left_alias}.geography_id,{left_alias}.state_fips,{left_alias}.county_fips,{left_alias}.cbsa,
               {left_alias}.period_start,{sql_literal(frequency)},{formula},{sql_literal(spec.unit)},
               {sql_literal(transformation)},{sql_literal(spec.version)},'[]',{inputs},'[]',
               greatest({left_alias}.available_at,{('right_.available_at' if spec.transformation == 'ratio_per_1000' else 'prior.available_at')}),{quality}
        FROM feature_values {left_alias} {join}
        WHERE {left_alias}.geography_type={sql_literal(geography)} AND {left_alias}.feature_name={current_name} AND {condition}""")


def _insert_lag(connection: duckdb.DuckDBPyConnection, spec: FeatureSpec, geography: str, frequency: str) -> None:
    input_name, output_name = sql_literal(spec.input_features[0]), sql_literal(spec.name)
    interval = _interval(frequency, spec.lag_periods)
    connection.execute(f"""INSERT INTO feature_values
        SELECT sha256({output_name} || '|' || spine.geography_id || '|' || CAST(spine.period_start AS VARCHAR) || '|' || prior.lineage_id),
               {output_name},{sql_literal(geography)},spine.geography_id,spine.state_fips,spine.county_fips,spine.cbsa,
               spine.period_start,{sql_literal(frequency)},prior.value,{sql_literal(spec.unit)},
               {sql_literal(f'lag; exact lag={spec.lag_periods} {frequency} period(s); missing periods omitted')},
               {sql_literal(spec.version)},'[]',CAST(to_json(list_value(prior.lineage_id)) AS VARCHAR),'[]',prior.available_at,prior.quality_level
        FROM (SELECT DISTINCT geography_id,state_fips,county_fips,cbsa,period_start FROM feature_values
              WHERE geography_type={sql_literal(geography)}) spine
        JOIN feature_values prior ON prior.geography_type={sql_literal(geography)} AND prior.geography_id=spine.geography_id
             AND prior.feature_name={input_name} AND prior.period_start=spine.period_start-{interval}""")


def build_feature_table(paths: WarehousePaths, *, geography: str, frequency: str) -> FeatureBuildResult:
    table_name = _table_name(geography, frequency)
    paths.initialize()
    required = _required_sources(frequency, geography)
    manifests = [item for item in active_manifests(paths) if item["source_id"] in required]
    if not manifests:
        raise ValueError("no active governed warehouse observations are available for feature construction")
    version_payload = {"builder_version": BUILDER_VERSION, "feature_registry_hash": registry_fingerprint(),
                       "frequency": frequency, "geography": geography,
                       "input_manifest_hashes": sorted(item["manifest_hash"] for item in manifests)}
    version = hashlib.sha256(canonical_json(version_payload).encode()).hexdigest()[:24]
    final_dir = paths.contained(Path("features") / table_name / f"version={version}")
    manifest_path = final_dir / "feature_manifest.json"
    if manifest_path.exists():
        manifest = verify_feature_manifest(manifest_path)
        return FeatureBuildResult(table_name, version, "unchanged", final_dir / "panel.parquet", final_dir / "lineage.parquet",
                                  manifest_path, manifest["quality"]["panel_rows"], manifest["quality"]["feature_values"], manifest["manifest_hash"])
    if final_dir.exists():
        raise ValueError(f"incomplete feature version exists and requires operator review: {final_dir}")
    parent = final_dir.parent; parent.mkdir(parents=True, exist_ok=True)
    staging = paths.contained(parent.relative_to(paths.root) / f".staging-{uuid.uuid4().hex}")
    staging.mkdir()
    panel_tmp, lineage_tmp = staging / "panel.parquet", staging / "lineage.parquet"
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("SET enable_progress_bar=false")
        _manifest_source(connection, manifests)
        connection.execute(f"CREATE TEMP TABLE feature_values({LINEAGE_SCHEMA},UNIQUE(geography_type,geography_id,period_start,feature_name),UNIQUE(lineage_id))")
        for spec in _source_specs(frequency, geography):
            _insert_source_feature(connection, spec, frequency)
        if geography == "cbsa":
            _aggregate_cbsa(connection, frequency)
        for spec in specs_for(frequency, geography):
            if spec.transformation in {"period_mean_broadcast", "period_end_broadcast"}:
                _insert_macro(connection, spec, geography, frequency)
        for spec in specs_for(frequency, geography):
            if spec.transformation in {"growth", "cagr", "difference", "ratio_per_1000"}:
                _insert_derived(connection, spec, geography, frequency)
        for spec in specs_for(frequency, geography):
            if spec.transformation == "lag":
                _insert_lag(connection, spec, geography, frequency)
        features = [spec.name for spec in specs_for(frequency, geography)]
        pivot = ",".join(f"max(CASE WHEN feature_name={sql_literal(name)} THEN value END) AS {name}" for name in features)
        availability = ",".join(f"max(CASE WHEN feature_name={sql_literal(name)} THEN available_at END) AS {name}__available_at" for name in features)
        connection.execute(f"""COPY (SELECT geography_type,geography_id,max(state_fips) state_fips,
            max(county_fips) county_fips,max(cbsa) cbsa,period_start,year(period_start) AS "year",
            CASE WHEN {sql_literal(frequency)}='quarterly' THEN quarter(period_start) END AS "quarter",{pivot},{availability}
            FROM feature_values WHERE geography_type={sql_literal(geography)}
            GROUP BY geography_type,geography_id,period_start ORDER BY geography_id,period_start)
            TO {sql_literal(str(panel_tmp))} (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 100000)""")
        connection.execute(f"COPY (SELECT * FROM feature_values ORDER BY geography_id,period_start,feature_name) TO {sql_literal(str(lineage_tmp))} (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 100000)")
        quality = profile_feature_files(panel_tmp, lineage_tmp, frequency=frequency)
        created = datetime.now(timezone.utc).isoformat()
        payload = {"manifest_version": FEATURE_MANIFEST_VERSION, "feature_table_version": version,
                   "feature_schema_version": "1.0.0", "table_name": table_name, "geography_type": geography,
                   "frequency": frequency, "created_at": created, "builder_version": BUILDER_VERSION,
                   "feature_registry_hash": registry_fingerprint(), "features": features,
                   "availability_columns": [name + "__available_at" for name in features],
                   "feature_definitions": _feature_definitions(frequency, geography, manifests),
                   "input_manifest_hashes": version_payload["input_manifest_hashes"], "quality": quality,
                   "files": [feature_file_entry(panel_tmp), feature_file_entry(lineage_tmp)],
                   "limitations": (["CBSA values use the latest active, source-backed OMB county membership vintage; historical boundaries are not reconstructed."] if geography == "cbsa" else [])}
        write_feature_manifest(staging / "feature_manifest.json", payload)
        os.replace(staging, final_dir)
        manifest = verify_feature_manifest(manifest_path)
        return FeatureBuildResult(table_name, version, "succeeded", final_dir / "panel.parquet", final_dir / "lineage.parquet",
                                  manifest_path, quality["panel_rows"], quality["feature_values"], manifest["manifest_hash"])
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    finally:
        connection.close()
