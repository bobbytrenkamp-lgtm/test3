# Investment-committee memo contract

The deterministic memo schema is `test3-ic-memo/2.0`. It is always labeled draft and not investment, legal or accounting advice. It contains all 18 required sections in a stable order: executive summary, property overview, sources received/missing, purchase assumptions, historical operations, pro forma assumptions, tenant/unit summary, lease rollover, debt terms, key discrepancies, material questions, location/jurisdiction context, major risks, potential mitigants, approved facts, unverified statements and source appendix.

Factual sections use approved values only. Each document-derived fact carries its document/version/page/excerpt hash and a local source URL; user-entered assumptions carry their rationale. Pending, rejected and superseded candidates appear only in the unverified section and never become factual prose. Empty sections say that approved information is missing instead of substituting zero or generated text.

Risks are limited to unresolved deterministic medium/high findings. Potential mitigants are explicitly labeled review steps, not established mitigants or recommendations. Received/missing source status compares the deal against the first-usable-release OM, rent-roll and T-12 set. The source appendix deduplicates approved-fact, received-document and discrepancy references.

Memo generation is deterministic and local. The complete memo and exact approval snapshot are persisted through the immutable export-artifact contract; no model or network service participates.
