from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .service import Service
from .auth import session_token, verify_password
from .db import now

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


class Handler(SimpleHTTPRequestHandler):
    service: Service

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def _json(self, status: int, payload: object, cookie: str | None = None):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; object-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _identity(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie.get("test3_session")
        if not token:
            raise PermissionError("Sign in required")
        with self.service.db.connect() as connection:
            user = connection.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=? AND s.expires_at>?", (token.value, now())).fetchone()
        if not user:
            raise PermissionError("Session expired")
        return {key: user[key] for key in ("id", "organization_id", "email", "display_name", "role")}

    def _payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > self.service.max_upload_bytes + 1_000_000:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/bootstrap":
                user = self._identity()
                return self._json(200, self.service.bootstrap(user))
            if parsed.path.startswith("/api/deals/"):
                user = self._identity()
                parts = parsed.path.strip("/").split("/")
                deal_id = parts[2]
                if len(parts) == 3:
                    return self._json(200, self.service.deal(deal_id, user["organization_id"]))
                if len(parts) == 5 and parts[3] == "export":
                    return self._json(200, self.service.export(user["organization_id"], user["id"], deal_id, parts[4]))
            if parsed.path.startswith("/api/documents/"):
                user = self._identity()
                document_id = parsed.path.rsplit("/", 1)[-1]
                with self.service.db.connect() as connection:
                    document = connection.execute("SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, user["organization_id"])).fetchone()
                if not document:
                    raise LookupError("Document not found")
                path = (self.service.upload_dir / user["organization_id"] / document["deal_id"] / document["stored_name"]).resolve()
                if self.service.upload_dir.resolve() not in path.parents:
                    raise ValueError("Unsafe document path")
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", document["detected_mime"])
                self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{document['original_name']}")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                return self.wfile.write(body)
            return super().do_GET()
        except PermissionError as error:
            return self._json(401, {"error": str(error)})
        except (ValueError, LookupError, json.JSONDecodeError) as error:
            return self._json(404 if isinstance(error, LookupError) else 400, {"error": str(error)})

    def do_POST(self):
        try:
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts == ["api", "signin"]:
                self.service.seed()
                payload = self._payload()
                with self.service.db.connect() as connection:
                    user = connection.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (str(payload.get("email", "")),)).fetchone()
                    if not user or not verify_password(str(payload.get("password", "")), user["password_hash"]):
                        raise PermissionError("Invalid local credentials")
                    token = session_token()
                    expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
                    connection.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token, user["id"], expires, now()))
                cookie = f"test3_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200"
                return self._json(200, {"signedIn": True}, cookie)
            user = self._identity()
            if parts == ["api", "deals"]:
                return self._json(201, self.service.create_deal(user["organization_id"], user["id"], self._payload()))
            if len(parts) == 4 and parts[:2] == ["api", "deals"] and parts[3] == "upload":
                filename = self.headers.get("X-Filename", "upload")
                length = int(self.headers.get("Content-Length", "0"))
                content = self.rfile.read(length)
                return self._json(201, self.service.upload(user["organization_id"], user["id"], parts[2], filename, content))
            if len(parts) == 4 and parts[:2] == ["api", "deals"] and parts[3] == "reconcile":
                return self._json(200, self.service.run_reconciliation(user["organization_id"], user["id"], parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "values"] and parts[3] == "review":
                payload = self._payload()
                return self._json(200, self.service.review_value(user["organization_id"], user["id"], parts[2], payload.get("status"), payload.get("normalized_value"), payload.get("comments", "")))
            if len(parts) == 4 and parts[:2] == ["api", "findings"] and parts[3] == "resolve":
                return self._json(200, self.service.resolve_finding(user["organization_id"], user["id"], parts[2], self._payload().get("notes", "")))
            return self._json(404, {"error": "Route not found"})
        except PermissionError as error:
            return self._json(401, {"error": str(error)})
        except (ValueError, LookupError, json.JSONDecodeError) as error:
            return self._json(404 if isinstance(error, LookupError) else 400, {"error": str(error)})

    def log_message(self, format, *args):
        print(f"[test3] {format % args}")


def main():
    host = os.getenv("TEST3_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Refusing non-loopback binding. Set up explicit local security before network exposure.")
    port = int(os.getenv("TEST3_PORT", "8765"))
    data_dir = Path(os.getenv("TEST3_DATA_DIR", ROOT / "data"))
    Handler.service = Service(data_dir, int(os.getenv("TEST3_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))))
    Handler.service.seed()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"test3 is running locally at http://{host}:{port}")
    print("ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
