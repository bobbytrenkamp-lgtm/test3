# Zero-cost operation

The full app runs locally with Python, SQLite and exact-pinned open-source document packages. Package installation is free and local. No account, payment method, API key, domain, cloud resource, hosted database, storage, OCR, AI inference or monitoring is required.

Optional Ollama/Tesseract are locally installed open-source software and must remain loopback/local. GitHub may store source and run CI for this public repository; the workflow does not enable paid features or deploy cloud runtime resources. The full private-document workflow is not deployed.

Run `python scripts/cost_guard.py` before each phase/deployment. Any uncertain provider is rejected until the owner explicitly approves it in writing after billing review.

ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.

