# test2 integration contract

Envelope `test3-to-test2/1.0` contains export/version metadata, source deal ID, source document hashes, approval timestamps, unresolved findings, diagnostics, test2 compatibility version and mapped sections for property, buildings, spaces, tenants, leases, rent steps, escalations, recoveries, market leasing, expenses, capital, debt, acquisition and supporting sources.

Only records with `review_status=approved` are mapped by default. Missing required mappings become warnings, not zero values. Numeric values remain decimal strings where possible.

Current status: contract-generated and independently tested with fictional data. Direct compatibility is not claimed because this package has not yet been executed through a test2 import fixture. The next contract version must be additive or explicitly version-breaking.

