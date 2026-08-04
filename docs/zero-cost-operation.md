# Zero-cost operation

Authentication abuse controls and session revocation run entirely in local process memory/SQLite. They require no account, network service, monitoring provider or paid identity system. Secure-cookie mode is a local browser flag and does not provision TLS or any external resource.

The full app runs locally with Python, SQLite and exact-pinned open-source document packages. Package installation is free and local. No account, payment method, API key, domain, cloud resource, hosted database, storage, OCR, AI inference or monitoring is required.

Optional Ollama/Tesseract are locally installed open-source software and must remain loopback/local. GitHub may store source and run CI for this public repository; the workflow does not enable paid features or deploy cloud runtime resources. The full private-document workflow is not deployed.

Optional test1 enrichment reads only a user-configured local static data directory. It requires no test1 account, API, geocoder, payment method or network request and cannot incur an overage. If no directory or approved county FIPS exists, the workflow reports that limitation and continues.

Run `python scripts/cost_guard.py` before each phase/deployment. Any uncertain provider is rejected until the owner explicitly approves it in writing after billing review.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.

