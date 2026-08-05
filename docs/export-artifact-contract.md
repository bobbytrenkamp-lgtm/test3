# Export artifact contract

Every test1, test2 or memo generation creates a new append-only `export_artifacts` row. Versions are monotonically assigned per deal and export kind inside an immediate SQLite transaction. The database rejects artifact updates and deletes.

The stored content is canonical compact JSON with a SHA-256 digest. The approval snapshot is a separately canonicalized list of the exact approved entity IDs, types, fields, normalized values, decision IDs, document/version/source hashes, reviewer IDs and review timestamps used at generation; it has its own SHA-256 digest. Metadata records the artifact ID, deal, kind, version, output schema/contract, actor and UTC creation time. Generation also appends a hash-chained audit event keyed to the artifact.

`POST /api/deals/{dealId}/export/{kind}` returns `{artifact, content}`. `GET /api/deals/{dealId}/exports` returns organization-scoped history, and `GET /api/exports/{artifactId}` re-verifies both hashes before returning metadata, approval snapshot and content. Cross-organization lookups fail as not found. Operational integrity and backup format 4.0 cover the artifact table and hashes.

Artifacts are local SQLite records and create no network request. They may contain sensitive diligence information and are covered by the same access, backup and media-retention controls as the deal database.
