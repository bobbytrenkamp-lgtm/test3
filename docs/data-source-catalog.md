# Governed data-source catalog

Source definitions live centrally in `test3.warehouse.catalog`. Each records identity, metrics, geographic and temporal scope, earliest availability, refresh method, licensing/redistribution notes, key/account/payment requirements, transformation rules and quality caveats.

The five Tier 1 sources have credential-free official HTTPS adapters: Census ACS, BLS LAUS, BEA Regional downloadable tables, Federal Reserve public CSV series, and Census Building Permits. The catalog remains the billing, licensing, geography, frequency and transformation control point; adapters do not define policy independently. HUD remains a governed manual-file source until its distribution contract is automated safely.

User-provided CRE data defaults to unknown redistribution rights and must retain its own licensing notes.
