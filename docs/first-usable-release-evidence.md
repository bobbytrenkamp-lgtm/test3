# First usable release evidence

Evidence date: 2026-08-04. `HttpSecurityTests.test_complete_first_usable_release_over_authenticated_http` runs a real loopback `ThreadingHTTPServer` against a fresh temporary data directory and the three committed fictional CSV fixtures. It uses the same session cookie, CSRF, permissions, API routes, service, SQLite schema and immutable artifact code as the application.

The test signs in; creates a fictional office deal; uploads an OM, rent roll and T-12; verifies all three classifications; retrieves each exact source byte-for-byte; approves one source-linked extracted cell from each document; creates and approves canonical typed inputs; runs reconciliation and requires at least ten findings; resolves one with notes; generates version-1 test2 and 18-section memo artifacts; reads export history; verifies material audit actions; and finishes with operational integrity `ok` and `networkRequests: 0`.

The fixtures and expected categories/values are hand-authored fictional data. The acceptance does not claim semantic row extraction or test2 entity coverage beyond the documented adapter: governed manual assumptions supply the scalar cross-document values, while the three uploaded cell records prove classification, source retrieval and review. Those remaining P1 coverage gaps stay explicit in the institutional audit.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.
