# CREOS universal entity IDs

This application is presented to CREOS Enterprise users as **CREOS
MarketSignal** — one of three modules (alongside CREOS SiteIntel and
CREOS Underwrite) in the CREOS commercial real estate platform. This
document is a pointer, not a new system: it exists so this repository,
`test1` (SiteIntel), and `test2` (Underwrite) converge on the same
entity ID scheme as they start sharing data, instead of each inventing
one independently.

The authoritative definition lives in the CREOS Enterprise repository:
[`test4/src/domain/ids.ts`](https://github.com/bobbytrenkamp-lgtm/test4/blob/main/src/domain/ids.ts)
and [`test4/docs/ARCHITECTURE.md`](https://github.com/bobbytrenkamp-lgtm/test4/blob/main/docs/ARCHITECTURE.md#entity-architecture-superseded-id-format--read-this).

> **Correction (Phase 4):** the table below previously showed
> `CREOS-PROP-000001`-style sequential display IDs as the *real*
> identifier. That was wrong and is now superseded in test4's own
> architecture doc — sequential counters collide across independently
> operated apps. The **real** identifier is a 26-character ULID
> (collision-safe, sortable by creation time); `CREOS-PROP-XXXXX`
> (last 5 characters of the ULID, not a running count) is only a
> human-facing display form derived from it.

## Summary

| Entity     | Real ID     | Display ID form   | Relevant to this app because...        |
| ---------- | ------------ | -------------------- | ---------------------------------------- |
| `Property` | 26-char ULID | `CREOS-PROP-XXXXX`   | Diligence evidence and location research here attach to a property shared with SiteIntel and Underwrite. |
| `Deal`     | 26-char ULID | `CREOS-DEAL-XXXXX`   | Underwriting export packages produced here correspond to a CREOS `Deal`. |
| `Market`   | 26-char ULID | `CREOS-MKT-XXXXX`    | Governed market data and forecasts here *are* CREOS `Market` records. |

## Status

**Utility available; consumed by the Phase 6 Underwrite handoff export.**
`src/test3/creos_ids.py` (Phase 4) implements the generator/validator
side of this scheme — a hand-ported, test-verified copy of test4's own
spec-compliant algorithm (see that module's docstring and
`tests/test_creos_ids.py`, which re-checks the same known-timestamp
vectors test4 verified independently against the ULID spec, 28/28
passing). This repository's own identifiers remain the sole source of
truth for everything this app does internally — no schema/warehouse
table changed, no existing ID was touched or replaced.

**Correction (Phase 6):** this section previously claimed a real handoff
was "inseparable from Phase 7/8 (shared authentication and a shared
CREOS data layer)." That was wrong — `test4/docs/HANDOFF_DESIGN.md`'s
recommended transport is zero-backend JSON export/import, which needs
neither. As of Phase 6, `src/test3/creos_handoff.py` calls
`generate_creos_ulid()`/`creos_display_id()` to mint the `handoffId`
and each `assumptionId`/`propertyId` in a real `creos-handoff-v1`
payload — the first real consumer of this utility. It's wired into the
assumption-intelligence screen's per-run actions
(`web/app.js`'s `.run-handoff` button, `POST
/api/assumption-runs/{id}/handoff`), which downloads a file a user can
import into CREOS Underwrite's assumption-import screen, the same way
test1 (SiteIntel)'s equivalent Phase 5 export already does. See that
module's docstring for the real translation-layer decisions this pass
found (no stable per-market identity exists in this app, so `market` is
never populated — see decision #1).
