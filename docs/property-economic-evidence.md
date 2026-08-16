# Property economic evidence

The Property Opportunity Engine accepts a bounded, versioned local evidence package for acquisition basis, known operating costs, and financing terms. The package is a screening input, not a substitute for Test2 underwriting.

## Evidence contract

Each field requires:

- governed field name;
- value and exact governed unit;
- source type;
- source reference;
- licensing note;
- evidence as-of date;
- optional factual notes.

All inputs are stored as `candidate_unapproved`. The API cannot assert analyst approval for them. Future-dated evidence, duplicates, unsupported fields, incompatible units, non-finite values, negative amounts, and rates outside zero-to-one fail closed.

Financial fields embedded directly in the subject object are ignored. A source-linked `economic_inputs` package is required before Test3 will calculate basis or acquisition-wedge scenarios.

Supported initial fields cover purchase price, renovation budget, closing and holding costs, property taxes, insurance, utilities, other known operating costs, vacancy, concessions, loan amount, interest rate, amortization, and loan term.

## Calculations

The engine may calculate:

- a complete estimated basis only when all four basis components exist;
- known-basis subtotal and explicit missing components otherwise;
- basis and renovation cost per unit when subject units exist;
- loan-to-basis and equity requirement before reserves when basis is complete;
- known annual operating costs;
- known costs as a share of the descriptive gross-potential-rent proxy;
- a partial break-even occupancy for only the known costs;
- sale-comparable downside/base/upside wedges when the sale units and basis are complete.

No missing value becomes zero. An absent component remains absent and blocks any calculation that requires it. The engine does not calculate debt service, reserves, replacement costs, taxes on sale, detailed NOI, leveraged returns, waterfalls, or a controlling valuation.

## Test2 boundary

The output contains `ADVISORY_UNAPPROVED` Test2 candidate inputs and `automaticApply=false`. Test2 remains responsible for cash flows, financing, valuation, returns, and the analyst's controlling underwriting. A later approval milestone must preserve the evidence and decision chain before any handoff.
