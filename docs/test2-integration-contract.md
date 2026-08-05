# test2 integration contract

Envelope `test3-underwriting-package/2.0` retains test3 provenance, approvals, unresolved findings and mapping diagnostics. Its `test2PortableModel` member is either `null` or a test2-native portable document:

```json
{"format":"cre-platform-model","formatVersion":1,"exportedAt":"…","engineVersion":"0.1.0","model":{}}
```

The nested `model` follows test2's `ModelInput` contract. Test3 emits it only when these reviewer-approved values exist and validate: `property_name`, `forecast_start_date`, `forecast_months`, and `discount_rate`. The deal's user-entered property type must also be in test2's supported enum. A missing or invalid mandatory value makes `mappingDiagnostics.importReady` false, records precise blockers, and leaves `test2PortableModel` null. Test3 never supplies a convenient zero or fabricated underwriting assumption.

Approved optional scalar fields mapped are rentable square feet, unit count and asking price. Fully approved semantic rows additionally map to test2 spaces, tenants, leases, fixed-annual operating expenses and debt facilities when every required value is present and its enum is accepted by test2. Decimal values remain finite decimal strings, dates use `YYYY-MM-DD`, and rates are decimal fractions. Rejected, pending, incomplete and unsupported rows are excluded and individually explained in `mappingDiagnostics.semanticEntities`; test3 never invents a rent basis, lease status, debt type, rate type, funding date, initial funding or other underwriting assumption.

The bounded row mappings are rent-roll and lease-schedule rows to one stable-ID space, tenant and lease; explicitly expense-classified operating-account rows with an annual total to one `fixed_annual` expense; and complete debt-term rows to one debt facility. Revenue accounts, rent steps, recoveries, options, capital items, buildings and scenarios remain unmapped. A skipped optional row does not invalidate an otherwise valid base property model, but its diagnostic prevents silent coverage claims.

This version deliberately breaks the misleading `test3-to-test2/1.0` shape, which resembled but did not implement test2's portable model. Compatibility is tested against the public test2 domain model used by `bobbytrenkamp-lgtm/test2`; test3 does not depend on, deploy, or invoke test2 at runtime.

## Independent compatibility evidence

On 2026-08-04, both the minimal model and an expanded fictional model with one space, tenant, lease, fixed-annual expense and fixed-rate acquisition debt facility were passed to test2's own `packages/domain-models/src/model-input.ts::parseModelInput`. Both parsed successfully. The expanded validation used audited test2 commit `9a0581efa10751726f067e2e6b3bea76f4c99b0b` and package version `0.1.0`; no test2 code or dependencies enter test3.

The validation used an already materialized, lockfile-selected local `zod` package and TypeScript loader. No dependency was downloaded and the repository has no runtime test2 dependency. This proves only the listed shapes at the audited commit; contract drift remains a release-time check.

