# Location rent comparables and area context

Test3 can rank user-owned comparable rents around a subject coordinate and describe proximity to locally supplied points of interest. All processing is local and deterministic. The feature does not scrape listings, geocode addresses, call a map service, score schools, assess crime/safety, or label a neighborhood as good or bad.

Subject coordinates should come from reviewed Test1 output or another documented local source. Comparable CSVs require `address, latitude, longitude, property_type, asking_rent, rent_unit, observed_date, source_reference`; optional `units` and `year_built` improve similarity. The legacy location-analysis POI route accepts `name, category, latitude, longitude, source_reference`.

The Property Opportunity Engine uses a stricter effective-dated local evidence contract: `name, category, latitude, longitude, evidence_date, source_reference`, with optional `effective_from` and `effective_to`. Governed categories are school, shopping center, grocery, downtown, transit, park, healthcare, and employment center. Future, stale, expired, not-yet-effective, invalid, and unsupported rows are excluded and counted. Each source also requires a source name, rights status, and licensing note; the service records the exact local-file SHA-256.

Comparable ranking uses a transparent available-factor score: distance 50%, unit-count similarity 25%, and year-built similarity 25%. Missing optional features are omitted and remaining weights are renormalized. Only like-property types inside the selected radius qualify. Rent benchmarks are withheld when rent units differ.

Area statements compare the nearest imported POI in each category with explicit analyst thresholds. Missing POI coverage is reported as missing, never as proof that an amenity does not exist. Proximity is not a measurement of school quality, safety, desirability, causality, or investment performance.

Distances are Haversine straight-line distances. They are not drive, walk, transit, or accessibility times. Test3 does not claim a route exists. A reviewer-approved county FIPS may also activate the existing local Test1 snapshot adapter; an unapproved FIPS is refused, and Test1 context remains read-only evidence with its source dates and integrity hashes.

The opportunity workflow explicitly prohibits using school quality, crime/safety, protected-class demographics, or subjective neighborhood desirability in scoring or recommendations. A school record means only that a named facility appeared in the imported coverage at the measured distance.

Potential zero-cost source preparation:

- Test1 normalized coordinates and local geography outputs.
- User-owned brokerage/exported comp files with licensing notes.
- Manually downloaded public NCES school files.
- A locally downloaded OpenStreetMap regional extract processed offline, subject to OpenStreetMap attribution and ODbL requirements.

No large source dataset is committed to Git. Every analysis records source file hashes and an audit event, but results remain research evidence and never overwrite underwriting assumptions.
