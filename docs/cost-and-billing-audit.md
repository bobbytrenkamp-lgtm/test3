# Cost and billing audit

Audit date: 2026-08-04. “Possibility of charges” covers this repository’s configured use, not hypothetical unrelated products from a provider.

| Component | Purpose | Provider | Account required | Payment method required | Usage limit | Possibility of charges | Local alternative | Approved/rejected | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Python 3.11+ | Local runtime | Python Software Foundation | No | No | Local resources | None | N/A | Approved | PSF-2.0; open source, local |
| SQLite | Local metadata DB | Public domain / Python stdlib | No | No | Local disk | None | Flat files | Approved | Public domain; no service |
| Browser HTML/CSS/JS | Analyst UI/PDF display | Local browser | No | No | Local resources | None | N/A | Approved | No hosted dependency |
| Git/GitHub public repo | Source collaboration | GitHub | Owner already has account | No new method | Repository plan limits | Workflow does not enable billing; owner must keep repository public/free | Local Git | Approved with constraint | Existing repository functionality only |
| GitHub Actions CI | Tests and guards | GitHub | Existing account | No new method | Public standard runners per GitHub terms | No paid feature configured; disable if repo becomes private/limits change | Run scripts locally | Approved with constraint | CI uses public-repo standard workflow only; no deployment |
| GitHub Pages | Optional static docs/demo | GitHub | Existing account | No | GitHub plan limits | No custom domain or paid feature configured | Local static server | Approved but inactive | Full app is not hosted; do not deploy private workflow |
| Ollama | Optional local model | Ollama open source | No | No | Local hardware | None | Deterministic engine | Approved but inactive | MIT; loopback endpoints only |
| Tesseract OCR | Optional local OCR | Community/Google-origin project | No | No | Local hardware | None | Manual review | Approved future option | Apache-2.0; local executable only |
| OpenAI/Anthropic/Gemini | Hosted AI | Hosted providers | Yes | Potentially | Metered | Yes | Ollama/deterministic | Rejected | Billable APIs prohibited |
| AWS/Azure/GCP/Cloudflare runtime | Hosting/storage/compute | Cloud providers | Yes | Often | Metered/free allowance | Yes | Local app/static Pages | Rejected | Free tiers can become billable |
| Supabase/Firebase/hosted Postgres | Hosted auth/database | Hosted providers | Yes | Varies | Free allowance | Potential | SQLite | Rejected | Potentially billable/terms can change |
| Mapbox/ArcGIS hosted APIs | Maps/jurisdiction | Hosted providers | Yes/key | Varies | Metered | Local test1 snapshot | Rejected | Potential usage billing |
| PyMuPDF/pdfplumber/openpyxl/Pillow | Potential future parsing | Package maintainers | No | No | Local resources | None | Current stdlib parser/manual review | Not approved yet | Local/open-source but license/necessity/version audit required before addition |

Dependencies may change license or distribution terms later; every proposed version requires a fresh audit and local/static alternative review. No external service was added.

