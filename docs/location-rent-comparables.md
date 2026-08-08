# Location rent comparables and area context

Test3 can rank user-owned comparable rents around a subject coordinate and describe proximity to locally supplied points of interest. All processing is local and deterministic. The feature does not scrape listings, geocode addresses, call a map service, score schools, assess crime/safety, or label a neighborhood as good or bad.

Subject coordinates should come from reviewed Test1 output or another documented local source. Comparable CSVs require `address, latitude, longitude, property_type, asking_rent, rent_unit, observed_date, source_reference`; optional `units` and `year_built` improve similarity. POI CSVs require `name, category, latitude, longitude, source_reference`. Supported categories are school, shopping center, grocery, downtown, transit, park and hospital.

Comparable ranking uses a transparent available-factor score: distance 50%, unit-count similarity 25%, and year-built similarity 25%. Missing optional features are omitted and remaining weights are renormalized. Only like-property types inside the selected radius qualify. Rent benchmarks are withheld when rent units differ.

Area statements compare the nearest imported POI in each category with explicit analyst thresholds. Missing POI coverage is reported as missing, never as proof that an amenity does not exist. Proximity is not a measurement of school quality, safety, desirability, causality, or investment performance.

Potential zero-cost source preparation:

- Test1 normalized coordinates and local geography outputs.
- User-owned brokerage/exported comp files with licensing notes.
- Manually downloaded public NCES school files.
- A locally downloaded OpenStreetMap regional extract processed offline, subject to OpenStreetMap attribution and ODbL requirements.

No large source dataset is committed to Git. Every analysis records source file hashes and an audit event, but results remain research evidence and never overwrite underwriting assumptions.
