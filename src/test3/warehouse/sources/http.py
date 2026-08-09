from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import time
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


MAX_RESPONSE_BYTES = 256 * 1024 * 1024
_HOST_REQUEST_TIMES: dict[str, float] = {}
_HOST_RATE_LOCK = Lock()
MIN_HOST_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class HttpResponse:
    request_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    sha256: str
    retrieved_at: str


class _RestrictedRedirect(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: tuple[str, ...], max_redirects: int = 3):
        self.allowed_hosts, self.max_redirects, self.count = allowed_hosts, max_redirects, 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        target = urljoin(req.full_url, newurl)
        parsed = urlsplit(target)
        if self.count > self.max_redirects or parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise ValueError("redirect left the governed HTTPS source boundary")
        return super().redirect_request(req, fp, code, msg, headers, target)


class GovernedHttpClient:
    def __init__(self, allowed_hosts: tuple[str, ...], *, timeout: float = 60, max_bytes: int = MAX_RESPONSE_BYTES):
        if not allowed_hosts:
            raise ValueError("an explicit official-host allowlist is required")
        self.allowed_hosts, self.timeout, self.max_bytes = allowed_hosts, timeout, max_bytes
        self._last_request = 0.0

    def get(self, url: str) -> HttpResponse:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts or parsed.username or parsed.password:
            raise ValueError("URL is not an allowed official HTTPS endpoint")
        with _HOST_RATE_LOCK:
            elapsed = time.monotonic() - _HOST_REQUEST_TIMES.get(parsed.hostname, 0.0)
            if elapsed < MIN_HOST_INTERVAL_SECONDS:
                time.sleep(MIN_HOST_INTERVAL_SECONDS - elapsed)
            _HOST_REQUEST_TIMES[parsed.hostname] = time.monotonic()
        handler = _RestrictedRedirect(self.allowed_hosts)
        opener = build_opener(handler)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Test3PublicData/0.1; local open-source research; no credentials)", "Accept": "*/*", "Connection": "close"})
        self._last_request = time.monotonic()
        try:
            with opener.open(request, timeout=self.timeout) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > self.max_bytes:
                    raise ValueError("official response exceeds configured byte limit")
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise ValueError("official response exceeds configured byte limit")
                if not body:
                    raise ValueError("official source returned an empty response")
                return HttpResponse(url, response.geturl(), response.status, response.headers.get_content_type(), body,
                                    hashlib.sha256(body).hexdigest(), datetime.now(timezone.utc).isoformat())
        except HTTPError as exc:
            raise RuntimeError(f"official source returned HTTP {exc.code}") from exc
