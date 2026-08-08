# Output contract

Return these top-level fields and no others:

- `schema_version`: `test3-skill-candidates/1.0`
- `candidate_only`: `true`
- `document_sha256`: the supplied 64-character lowercase hash
- `skill_name`: `test3-cre-candidate-extraction`
- `generated_at`: UTC ISO-8601 timestamp
- `candidates`: zero or more candidate objects
- `limitations`: array of concise strings

Every candidate must contain exactly:

- `candidate_id`: unique string
- `candidate_type`: `market_observation`, `deal_fact`, `lease_fact`, or `debt_term`
- `field_name`: conservative snake_case field name
- `raw_value`: source text
- `normalized_value`: normalized string or null
- `unit`: string or null
- `currency`: ISO currency code or null
- `source_page`: one-based integer
- `source_excerpt`: short verbatim evidence excerpt
- `confidence`: number from 0 through 1 describing extraction reliability
- `methodology_notes`: transformation explanation or limitation
