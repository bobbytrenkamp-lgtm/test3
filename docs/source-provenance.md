# CRE source provenance and verification

Every historical CRE row retains its source name, exact local/public identifier, source period, observation period, release date when known, retrieval timestamp, methodology code, source vintage, licensing note, redistribution status, original row hash, and source row number.

The verification engine checks:

- governed geography, property type, metric, methodology, unit, and numeric range;
- duplicate observations within a source vintage;
- conflicting independent sources without averaging them;
- revised values across source vintages;
- changing methodologies and frequencies;
- missing monthly, quarterly, or annual periods;
- sudden adjacent-period changes requiring review;
- stale retrievals; and
- whether evidence was available at a historical forecast origin.

Confidence is a documented weighted quality score, not a statistical confidence interval. Components are source-class reliability, methodology clarity, independent-source agreement, retrieval recency, metadata completeness, explicit analyst verification, and series consistency.

A CSV cannot make itself model-eligible by setting `verification_status=analyst_verified`. The importing operator must also pass `--analyst-reviewed`. This is an explicit local review assertion, not proof that the source is accurate.

Conflicting observations remain separate. `reconcile_observations()` requires an explicit ordered source-priority policy, selects one verified observation, records alternatives, and sets `averaged=false`.
