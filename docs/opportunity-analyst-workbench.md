# Opportunity analyst workbench

Property opportunity runs are immutable research artifacts. Review never changes a run. It creates a separate append-only `opportunity_decisions` record bound to the exact artifact SHA-256 and the prior organization decision hash.

Only the reviewer and administrator roles have the `opportunity.review` permission. The creator of a run cannot approve that same run. Approval requires an independent reviewer, a specific rationale, and explicit acknowledgement that the evidence, stated source rights, limitations, and advisory-only Test2 boundary were reviewed. The application verifies the embedded and persisted artifact hashes and blocks approval when comparable minimums, source-rights documentation, or unit consistency fail.

Available decisions are:

- `approved`: approves the evidence package for governed downstream consideration; it is not an appraisal, score, forecast, or Test2 instruction.
- `rejected`: records why the evidence must not be relied upon.
- `changes_requested`: records one or more bounded JSON Pointer paths, proposed values, and rationales. It does not edit the artifact; the analyst must create a new run.

The deal API returns the full decision history and a derived latest review state. The workbench presents evidence, sources, economic screens, location evidence, quality components, score status, limitations, and prior decisions separately. It never displays a fabricated score and never applies an assumption to Test2.

Schema version 7 and backup format 7.0 include opportunity decisions. Update/delete triggers, operational re-hashing, referential checks, and the organization-wide decision chain make mutation or detached approval visible.

## Institutional limitations

The local separation-of-duties control distinguishes user IDs and roles; it is not enterprise identity proofing. The operator remains responsible for provisioning independent named users, protecting the local device and backups, and establishing retention and review policies. Source-rights acknowledgement records an analyst decision and is not legal advice.

