# test1 local snapshot integration contract

Test3 optionally reads an existing, local test1 `data/` directory. Set `TEST3_TEST1_DATA_DIR` to that directory and restart the loopback service. Test3 performs no clone, download, geocoding, URL validation or other network request. No account, credential, payment method, free allowance or hosted service is involved.

## Accepted source contract

Required files are test1's actual `platform_metadata.json` (`_schema=platform_metadata_v1`) and `map_data.json` (`counties` object). The adapter also understands the current public shapes of `political_risk.json`, `water_stress.json`, `tax_incentives.json`, `facilities_index.json`, `state_regulations.json`, and up to 100 normalized `zoning/normalized/*.json` jurisdiction files. Optional malformed datasets fail the complete snapshot explicitly rather than being silently ignored.

Every loaded file has a 16 MiB limit, the selected bundle has a 40 MiB limit, duplicate JSON keys and duplicate zoning county FIPS are rejected, and file byte counts/SHA-256 hashes enter the output integrity manifest. The normalized contract version is `test1-local-data-directory/1.1`; enrichment remains backward compatible with normalized 1.0 snapshots.

## Input and authority boundary

Matching requires a reviewer-approved, exactly five-digit `county_fips` value. Pending/rejected values and the free-form deal address do not drive a match. Test3 deliberately does not infer a county from an address because doing so accurately would require a governed local GIS dataset or a potentially billable hosted geocoder.

## Output semantics

Matched output may include county policy, political risk, approximate water stress, tax incentives, a bounded facility summary, state regulation, source citations, per-file integrity, source dates, calculated snapshot age, coverage and upstream limitations. `networkRequests` is always zero. Missing datasets remain `null`/empty and never become favorable, verified or zero observations.

When normalized zoning files are present, output additionally includes jurisdiction coverage and verification metadata, official sources, upstream limitations, and at most 100 bounded district summaries. It always reports `parcelDistrictKnown=false` and `decisionUse=preliminary_research_only`; it does not infer parcel zoning, overlay applicability, proffers, variances, or current ordinance effect. Manual-review flags from dimensional standards remain visible.

Top-level `verified` is true only if test1's county record says `pipeline_verified=true` and the main snapshot date is no more than 90 days old. Test1's current records commonly set that flag false, so a rich multi-dataset match can correctly remain unverified. Approximate/stale dataset dates, including water context, remain visible. Analysts must re-check cited primary sources before decisions.

## Independent compatibility evidence

On 2026-08-07 the contract was re-audited against read-only public test1 commit `8203267d4cb663e5f9efb0f81dc63862b70d5b77`. The repository now includes normalized zoning jurisdiction/district schemas and an explicitly low-confidence Loudoun pilot. Test3 adopted only an original bounded reader and preserves the pilot's preliminary-research and manual-verification limitations. Earlier full-directory compatibility evidence at commit `aa8ab7069c669f33c5961d80b588eee54113738e` matched seven actual datasets with zero network requests and remained conservatively unverified.

Test1 currently has no repository license file. Test3 therefore redistributes no test1 code or data and declares no package dependency; it implements an original reader for files the user already possesses locally. Any future redistribution requires an explicit compatible data/software license audit.
