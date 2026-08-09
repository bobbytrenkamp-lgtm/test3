# Governed data-source catalog

Source definitions live centrally in `test3.warehouse.catalog`. Each records identity, metrics, geographic and temporal scope, earliest availability, refresh method, licensing/redistribution notes, account and payment requirements, transformation rules, and quality caveats.

Automated official-source adapters cover Census ACS, Census CPS/HVS, BLS LAUS/QCEW, BEA Regional accounts, Federal Reserve public and CRE credit series, Census Building Permits, Census/OMB CBSA delineations, and HUD Fair Market Rent history. BLS and Federal Reserve files also have a validated local official-file route because public infrastructure may reject automated retrieval. The catalog remains the billing, licensing, geography, frequency, and transformation control point; adapters do not define policy independently.

CPS/HVS vacancy and asking-rent observations are residential context, not institutional market targets. Federal Reserve SLOOS and bank-balance-sheet series are national credit predictors. HUD/USPS vacancy data is excluded from automatic acquisition because HUD limits access to registered governmental and nonprofit users under a sublicense.

User-provided CRE data defaults to unknown redistribution rights and must retain its own licensing notes. No public-source adapter requests a key, credential, payment method, or billable service.

An immutable manifest records the exact source-catalog fingerprint used when it was built. A reviewed source-definition revision may add the prior fingerprint to `LEGACY_SOURCE_FINGERPRINTS`; unrecognized drift still fails integrity verification. This preserves historical versions without silently accepting arbitrary catalog changes.
