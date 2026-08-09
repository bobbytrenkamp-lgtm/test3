# Geographic crosswalks

`test3-data refresh --source crosswalk --vintage 2023` downloads the official Census-hosted OMB Bulletin 23-01 delineation workbook and publishes one canonical `county_cbsa_membership` observation per listed county component. The 2023 contract uses the July 21, 2023 effective date and retains county FIPS, state FIPS, CBSA code, raw row evidence, source hash, manifest, and normalizer version.

`lookup_county_cbsa(paths, county_fips, on_date)` selects only a delineation effective on the requested date. Relationships are not treated as permanent, and later vintages can coexist. A county absent from the delineation remains unassigned; Test3 does not invent a CBSA.

HUD county subdivisions are retained as ten-digit state/county/subdivision identifiers and linked to their five-digit county FIPS. Test3 never collapses them into duplicate county observations. It also does not infer a county from a permit-issuing place or free-text city. Test1 remains authoritative for project, parcel, zoning, and policy geography.
