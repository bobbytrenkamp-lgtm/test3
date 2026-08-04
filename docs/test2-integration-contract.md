# test2 integration contract

Envelope `test3-underwriting-package/2.0` retains test3 provenance, approvals, unresolved findings and mapping diagnostics. Its `test2PortableModel` member is either `null` or a test2-native portable document:

```json
{"format":"cre-platform-model","formatVersion":1,"exportedAt":"…","engineVersion":"0.1.0","model":{}}
```

The nested `model` follows test2's `ModelInput` contract. Test3 emits it only when these reviewer-approved values exist and validate: `property_name`, `forecast_start_date`, `forecast_months`, and `discount_rate`. The deal's user-entered property type must also be in test2's supported enum. A missing or invalid mandatory value makes `mappingDiagnostics.importReady` false, records precise blockers, and leaves `test2PortableModel` null. Test3 never supplies a convenient zero or fabricated underwriting assumption.

Approved optional fields currently mapped are rentable square feet, unit count and asking price. Decimal values remain decimal strings, dates use `YYYY-MM-DD`, and discount rates are decimal fractions. Rejected and pending candidates are excluded from both the model and supporting-source list.

This version deliberately breaks the misleading `test3-to-test2/1.0` shape, which resembled but did not implement test2's portable model. Compatibility is tested against the public test2 domain model used by `bobbytrenkamp-lgtm/test2`; test3 does not depend on, deploy, or invoke test2 at runtime.

## Independent compatibility evidence

On 2026-08-04, a fictional model with the exact generated structure was passed to test2's own `packages/domain-models/src/model-input.ts::parseModelInput`. It parsed successfully and test2 applied its documented vacancy and equity defaults. The validation used a disposable shallow clone at test2 version `0.1.0`; no code or dependencies from that clone enter test3.

Test2's package installation also demonstrated its minimum-release-age policy by rejecting twelve newly published lockfile entries. That policy was not disabled or bypassed. The already materialized, lockfile-selected `zod` package and TypeScript loader were sufficient to execute the parser. This result proves the current minimal model shape, not every future test2 version; contract drift remains a release-time check.

