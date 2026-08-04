# test1 local snapshot integration contract

Test3 optionally reads an existing, local test1 `data/` directory. Set `TEST3_TEST1_DATA_DIR` to that directory and restart the loopback service. Test3 performs no clone, download, geocoding, URL validation or other network request. No account, credential, payment method, free allowance or hosted service is involved.

## Accepted source contract

Required files are test1's actual `platform_metadata.json` (`_schema=platform_metadata_v1`) and `map_data.json` (`counties` object). The adapter also understands the current public shapes of `political_risk.json`, `water_stress.json`, `tax_incentives.json`, `facilities_index.json`, and `state_regulations.json`. Optional malformed datasets fail the complete snapshot explicitly rather than being silently ignored.

Every loaded file has a 16 MiB limit, the selected bundle has a 40 MiB limit, duplicate JSON keys are rejected, and file byte counts/SHA-256 hashes enter the output integrity manifest. The normalized contract version is `test1-local-data-directory/1.0`.

## Input and authority boundary

Matching requires a reviewer-approved, exactly five-digit `county_fips` value. Pending/rejected values and the free-form deal address do not drive a match. Test3 deliberately does not infer a county from an address because doing so accurately would require a governed local GIS dataset or a potentially billable hosted geocoder.

## Output semantics

Matched output may include county policy, political risk, approximate water stress, tax incentives, a bounded facility summary, state regulation, source citations, per-file integrity, source dates, calculated snapshot age, coverage and upstream limitations. `networkRequests` is always zero. Missing datasets remain `null`/empty and never become favorable, verified or zero observations.

Top-level `verified` is true only if test1's county record says `pipeline_verified=true` and the main snapshot date is no more than 90 days old. Test1's current records commonly set that flag false, so a rich multi-dataset match can correctly remain unverified. Approximate/stale dataset dates, including water context, remain visible. Analysts must re-check cited primary sources before decisions.

## Independent compatibility evidence

On 2026-08-04 the adapter loaded the read-only public test1 data directory at commit `aa8ab7069c669f33c5961d80b588eee54113738e`. A fictional Loudoun County (`51107`) input matched seven actual datasets with zero network requests, two policy citations, five political-risk citations, 129 facilities and explicit 2024 water-data freshness. The result remained conservatively unverified.

Test1 currently has no repository license file. Test3 therefore redistributes no test1 code or data and declares no package dependency; it implements an original reader for files the user already possesses locally. Any future redistribution requires an explicit compatible data/software license audit.
