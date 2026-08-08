# Analytical data lineage

Use `test3-data lineage OBSERVATION_ID` to bind a public observation to source series, raw snapshot metadata and SHA-256, retrieval time, source row, normalizer version, quality status, Parquet file and immutable manifest.

Lineage follows `raw source reference -> raw row hash -> canonical transformation version -> normalized row hash -> observation id -> Parquet content hash -> immutable manifest hash`.

The raw reference must locate the original file/series/row within the owner's authorized source. A deterministic normalized hash detects changed transformations. Dataset manifests bind the schema version, governed source definition, observation window, row count and every persisted file hash. These controls make a displayed analytical value traceable without committing source datasets to Git.

Document-extracted values remain review candidates. A future warehouse bridge may publish them only after the existing analyst-approval workflow; extraction tools never directly create trusted observations.
