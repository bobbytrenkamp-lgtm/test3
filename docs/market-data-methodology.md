# Market data methodology

Test3 imports analyst-controlled UTF-8 CSV files locally. It preserves the original bytes by UUID, records SHA-256, source/version/as-of/licensing metadata, and normalizes each supported metric into immutable observations without filling missing values. Invalid rows are reported with row numbers and original-row hashes. The original panel remains the source of truth.

Market rent growth uses the narrowest available match in this order: submarket+subtype, market+subtype, market+property type, CBSA+property type, state-FIPS+property type, national+property type. Broader fallbacks are disclosed and cap confidence. The range uses observed quartiles; the base uses the median unless an eligible validated real model is available. Every result is candidate-only.
