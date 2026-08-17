# CREOS universal entity IDs

This application is presented to CREOS Enterprise users as **CREOS
MarketSignal** — one of three modules (alongside CREOS SiteIntel and
CREOS Underwrite) in the CREOS commercial real estate platform. This
document is a pointer, not a new system: it exists so this repository,
`test1` (SiteIntel), and `test2` (Underwrite) converge on the same
entity ID scheme as they start sharing data, instead of each inventing
one independently.

The authoritative definition lives in the CREOS Enterprise repository:
[`test4/docs/ARCHITECTURE.md`](https://github.com/bobbytrenkamp-lgtm/test4/blob/main/docs/ARCHITECTURE.md#future-entity-architecture).

## Summary

| Entity     | Future ID format     | Relevant to this app because...        |
| ---------- | --------------------- | ---------------------------------------- |
| `Property` | `CREOS-PROP-000001`   | Diligence evidence and location research here attach to a property shared with SiteIntel and Underwrite. |
| `Deal`     | `CREOS-DEAL-000001`   | Underwriting export packages produced here correspond to a CREOS `Deal`. |
| `Market`   | `CREOS-MKT-XXXXX`     | Governed market data and forecasts here *are* CREOS `Market` records. |

## Status

**Not implemented.** This repository's own identifiers remain the
source of truth today, and this app's local-first, no-external-
transmission model (see `docs/security-model.md`) means adopting a
shared ID scheme is inseparable from Phase 7/8 (shared authentication
and a shared CREOS data layer) in the CREOS Integration Roadmap
([`test4/docs/INTEGRATION_ROADMAP.md`](https://github.com/bobbytrenkamp-lgtm/test4/blob/main/docs/INTEGRATION_ROADMAP.md)),
neither of which is scheduled. This document changes no schema, API,
or data flow.
