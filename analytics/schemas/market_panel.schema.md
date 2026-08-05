# Market panel CSV contract 1.0

Required UTF-8 headers: `period`, `market_id`, `market_name`, `property_type`, `source`, `source_date`, `source_reference`, `usage_rights`. Dates use `YYYY-MM-DD`; rates are decimal fractions; `county_fips`, when present, is exactly five digits. At least one supported metric is required per row. Formulas, duplicate headers, non-finite numbers, files over 16 MiB, and more than 100,000 rows are rejected. Missing values remain missing.
