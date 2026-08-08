# Governed data-source catalog

Source definitions live centrally in `test3.warehouse.catalog`. Each records identity, metrics, geographic and temporal scope, earliest availability, refresh method, licensing/redistribution notes, key/account/payment requirements, transformation rules and quality caveats.

Milestone 1 registers Census ACS, BLS LAUS/CES, BEA regional accounts, public FRED series, HUD public datasets, Census Building Permits, local Test1 exports and user-owned imports. The catalog activates no network requests. Initial refreshes are bounded local-file workflows; source-specific downloaders belong to Milestone 2 and must pass the zero-cost audit independently.

User-provided CRE data defaults to unknown redistribution rights and must retain its own licensing notes.
