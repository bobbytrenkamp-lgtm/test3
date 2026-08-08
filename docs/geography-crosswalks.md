# Geographic crosswalks

Test3 validates state/county FIPS and CBSA codes as stable identifiers. `CountyCrosswalk` stores county/state names, optional CBSA membership, vintage and effective dates. Relationships are not treated as permanent; later feature construction must select the vintage effective for the observation period.

Test3 does not infer a county from a permit-issuing place or free-text city. Test1 remains authoritative for normalized project geography. Official delineation files can populate this versioned contract without changing the canonical observation store.
