from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class LocalModelUnavailable(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request: Request, timeout: float):
    return build_opener(_NoRedirect).open(request, timeout=timeout)


def validate_local_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Only loopback local-model endpoints are permitted")
    return url.rstrip("/")


def status(url: str) -> dict:
    validate_local_endpoint(url)
    return {"available": False, "provider": "ollama-local", "endpoint": url, "message": "Optional local model not probed automatically. Deterministic processing remains active."}


def probe(url: str, timeout: float = 2.0) -> dict:
    endpoint = validate_local_endpoint(url)
    try:
        with _open(Request(f"{endpoint}/api/tags", headers={"Accept": "application/json"}), timeout) as response:
            payload = json.loads(response.read(1_000_001))
        models = [str(item.get("name")) for item in payload.get("models", []) if isinstance(item, dict) and item.get("name")]
        return {"available": True, "provider": "ollama-local", "endpoint": endpoint, "models": models}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
        return {"available": False, "provider": "ollama-local", "endpoint": endpoint, "models": [], "message": f"Local model unavailable: {type(error).__name__}. Deterministic processing remains active."}


def generate_json(url: str, model: str, prompt: str, prompt_template_version: str, input_document_sha256: str, timeout: float = 60.0) -> dict:
    endpoint = validate_local_endpoint(url)
    model, prompt, prompt_template_version = str(model).strip(), str(prompt), str(prompt_template_version).strip()
    if not model or not prompt_template_version:
        raise ValueError("Model and prompt-template version are required")
    if len(prompt) > 200_000:
        raise ValueError("Local-model prompt exceeds the safety limit")
    if len(input_document_sha256) != 64 or any(character not in "0123456789abcdef" for character in input_document_sha256.lower()):
        raise ValueError("Input document SHA-256 must be a 64-character hexadecimal digest")
    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode()
    request = Request(f"{endpoint}/api/generate", data=body, method="POST", headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with _open(request, timeout) as response:
            payload = json.loads(response.read(2_000_001))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise LocalModelUnavailable(f"Local Ollama generation failed: {type(error).__name__}") from error
    try:
        structured = json.loads(payload["response"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise LocalModelUnavailable("Local Ollama response did not contain valid structured JSON") from error
    if not isinstance(structured, dict):
        raise LocalModelUnavailable("Local Ollama structured output must be a JSON object")
    return {
        "provider": "ollama-local", "modelName": str(payload.get("model") or model),
        "modelVersion": str(payload.get("model") or model), "promptTemplateVersion": prompt_template_version,
        "inputDocumentSha256": input_document_sha256.lower(), "promptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "generatedAt": datetime.now(timezone.utc).isoformat(), "structuredOutputValid": True,
        "output": structured, "approvalStatus": "candidate_only",
    }

