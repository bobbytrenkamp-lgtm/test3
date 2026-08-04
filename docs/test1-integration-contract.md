# test1 integration contract

The optional adapter accepts address, latitude/longitude, county FIPS, state, municipality and parcel ID. It reads a user-supplied local snapshot and may return restrictions, zoning, scores, water/economic/infrastructure context, proximity, incentives, citations, freshness and coverage.

Every output distinguishes verified, sample, incomplete, missing and derived data. Without a snapshot the adapter returns `status=unavailable`, `coverage=missing` and no results. It performs no network request and is never a hard dependency.

