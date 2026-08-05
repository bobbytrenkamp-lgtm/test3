# Assumption data source catalog

Test3 never downloads these sources at runtime. An analyst downloads a static file, confirms usage rights, and imports it locally. Every import records source, version, as-of date, reference, licensing notes, and SHA-256. Provider terms must be rechecked before each new acquisition workflow.

| Domain | Preferred evidence | Safe acquisition path | Account/key | Billing risk | Test3 metrics |
|---|---|---|---|---|---|
| Market fundamentals | Analyst-licensed market/submarket extracts, appraisal support, broker research with documented rights | Local CSV only | Depends on analyst source | Reject any feed capable of charges | rent, rent growth, vacancy, availability, absorption, inventory, deliveries, pipeline |
| Leasing | Executed leases, approved comp packages, property rent rolls | Local CSV only | No Test3 account | None in Test3 | renewal probability, downtime, TI, LC, lease-up pace, comp count |
| Operations | T-12s, historical statements, tax bills, insurance quotes, utility statements | Local CSV/document evidence | No | None | expense, tax, insurance, utility, payroll, repairs per area and growth |
| Transactions/capital | Analyst-controlled sale and debt comp packages | Local CSV only | No Test3 account | None | cap rate, transaction count, discount rate, debt rate |
| Labor/inflation | BLS published series | Manual file download or unregistered API v1 outside Test3; BLS states v1 requires no registration but has lower limits ([BLS](https://www.bls.gov/developers/home.htm)) | No for v1 | No payment mechanism documented; rate limits apply | employment growth, inflation, construction-cost growth inputs |
| Demographics/business | Census published tables | Manual static download; API keys are optional below documented thresholds ([Census](https://www.census.gov/content/dam/Census/data/developers/api-user-guide/api-guide.pdf)) | No for bounded manual use | No payment mechanism documented; query limits apply | population, income, households, permits |
| Macro/rates | FRED published series | Manual CSV download; do not configure the key-requiring FRED API ([FRED](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)) | No for manual download | No Test3 billing path | Treasury rate, inflation, unemployment, bank CRE indicators |
| Energy/utilities | EIA bulk files | Manual bulk download only; EIA states bulk downloads do not require a key ([EIA](https://www.eia.gov/opendata/v1/register.php)) | No for bulk files | No payment mechanism documented | utility-cost context |

Rejected: paid brokerage feeds, hosted databases, geocoding/map APIs, metered AI/OCR, cloud storage, and any “free tier” that can generate overage charges.
