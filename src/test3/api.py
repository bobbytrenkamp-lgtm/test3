from __future__ import annotations

import json
import hashlib
import os
import secrets
import io
import sys
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from .service import Service
from .auth import DUMMY_PASSWORD_HASH, SigninLimiter, session_token, verify_password
from .db import now
from .extraction import parse_csv, parse_xlsx
from .permissions import require
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


class GoneError(Exception):
    pass


class Handler(SimpleHTTPRequestHandler):
    service: Service
    signin_limiter = SigninLimiter()
    signin_address_limiter = SigninLimiter(max_failures=20)
    secure_cookie = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; object-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def _json(self, status: int, payload: object, cookie: str | None = None):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
            token_hash = hashlib.sha256(token.value.encode()).hexdigest()
            user = connection.execute("SELECT u.*,s.csrf_token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", (token_hash, now())).fetchone()
        if not user:
            raise PermissionError("Session expired")
        identity = {key: user[key] for key in ("id", "organization_id", "email", "display_name", "role", "csrf_token")}
        identity["session_token_hash"] = token_hash
        return identity

    def _authorize_post(self, user: dict, permission: str):
        if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), user["csrf_token"]):
            raise PermissionError("Invalid CSRF token")
        require(user["role"], permission)

    def _reauthorize(self, user: dict, password: object) -> None:
        with self.service.db.connect() as connection:
            current = connection.execute("SELECT password_hash FROM users WHERE id=? AND organization_id=?", (user["id"], user["organization_id"])).fetchone()
        if not current or not verify_password(str(password or ""), current["password_hash"]):
            self.service.db.audit(user["organization_id"], user["id"], "security.reauthentication_failed", "user", user["id"], {"request_path": urlparse(self.path).path})
            raise PermissionError("Current-password reauthentication failed")

    def _payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1_000_000:
            raise ValueError("Request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/bootstrap":
                user = self._identity()
                return self._json(200, self.service.bootstrap(user))
            if parsed.path == "/api/operations/integrity":
                user = self._identity()
                require(user["role"], "operations.inspect")
                return self._json(200, self.service.operational_integrity(user["organization_id"]))
            if parsed.path.startswith("/api/deals/"):
                user = self._identity()
                parts = parsed.path.strip("/").split("/")
                deal_id = parts[2]
                if len(parts) == 3:
                    return self._json(200, self.service.deal(deal_id, user["organization_id"]))
                if len(parts) == 4 and parts[3] == "exports":
                    return self._json(200, self.service.export_history(user["organization_id"], deal_id))
            if parsed.path.startswith("/api/exports/"):
                user = self._identity()
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 3:
                    return self._json(200, self.service.export_artifact(user["organization_id"], parts[2]))
            if parsed.path.startswith("/api/documents/"):
                user = self._identity()
                parts = parsed.path.strip("/").split("/")
                document_id = parts[2]
                with self.service.db.connect() as connection:
                    document = connection.execute("SELECT * FROM documents WHERE id=? AND organization_id=?", (document_id, user["organization_id"])).fetchone()
                if not document:
                    raise LookupError("Document not found")
                if document["original_purged_at"]:
                    raise GoneError("Original document bytes were purged; provenance metadata and governed history remain")
                path = (self.service.upload_dir / user["organization_id"] / document["deal_id"] / document["stored_name"]).resolve()
                if self.service.upload_dir.resolve() not in path.parents:
                    raise ValueError("Unsafe document path")
                body = path.read_bytes()
                if len(parts) == 5 and parts[3] == "page":
                    if document["detected_mime"] != "application/pdf":
                        raise ValueError("Rendered pages are available only for PDFs")
                    page_number = int(parts[4])
                    pdf = pdfium.PdfDocument(body)
                    try:
                        if page_number < 1 or page_number > len(pdf):
                            raise ValueError("Page number is out of range")
                        page = pdf[page_number - 1]
                        try:
                            width, height = page.get_size()
                            scale = min(2.0, 10_000 / max(width, height))
                            if width * height * scale * scale > 80_000_000:
                                raise ValueError("Rendered page exceeds the pixel safety limit")
                            bitmap = page.render(scale=scale)
                            try:
                                image = bitmap.to_pil(); output = io.BytesIO(); image.save(output, format="PNG"); body = output.getvalue()
                            finally:
                                bitmap.close()
                        finally:
                            page.close()
                    finally:
                        pdf.close()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "private, no-store")
                    self.end_headers()
                    return self.wfile.write(body)
                if len(parts) == 4 and parts[3] == "table":
                    if document["detected_mime"] == "text/csv":
                        rows, _ = parse_csv(body)
                        kind, sheet = "csv", None
                    elif document["detected_mime"].endswith("spreadsheetml.sheet"):
                        rows, _ = parse_xlsx(body)
                        kind, sheet = "xlsx", "First worksheet"
                    else:
                        raise ValueError("Table view is available only for CSV and XLSX documents")
                    truncated = len(rows) > 500 or any(len(row) > 200 for row in rows[:500]) or sum(len(row) for row in rows[:500]) > 20_000
                    visible, cells = [], 0
                    for row in rows[:500]:
                        remaining = 20_000 - cells
                        if remaining <= 0:
                            break
                        clipped = row[:min(200, remaining)]
                        visible.append(clipped)
                        cells += len(clipped)
                    return self._json(200, {"kind": kind, "sheet": sheet, "rows": visible, "rowCount": len(rows), "visibleCellCount": cells, "truncated": truncated, "formulasExecuted": False})
                if len(parts) != 3:
                    raise LookupError("Document route not found")
                self.send_response(200)
                self.send_header("Content-Type", document["detected_mime"])
                self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(document['original_name'], safe='')}")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "private, no-store")
                self.end_headers()
                return self.wfile.write(body)
            return super().do_GET()
        except PermissionError as error:
            return self._json(401, {"error": str(error)})
        except GoneError as error:
            return self._json(410, {"error": str(error)})
        except (ValueError, LookupError, json.JSONDecodeError) as error:
            return self._json(404 if isinstance(error, LookupError) else 400, {"error": str(error)})

    def do_POST(self):
        try:
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts == ["api", "signin"]:
                payload = self._payload()
                email = str(payload.get("email", "")).strip().lower()
                address_key = self.client_address[0]
                limiter_key = f"{address_key}:{email}"
                if not self.signin_limiter.allowed(limiter_key) or not self.signin_address_limiter.allowed(address_key):
                    return self._json(429, {"error": "Too many failed sign-in attempts; retry later"})
                with self.service.db.connect() as connection:
                    users = connection.execute("SELECT * FROM users WHERE lower(email)=? LIMIT 2", (email,)).fetchall()
                    user = users[0] if len(users) == 1 else None
                    password_valid = verify_password(str(payload.get("password", "")), user["password_hash"] if user else DUMMY_PASSWORD_HASH)
                    if not user or not password_valid:
                        self.signin_limiter.failure(limiter_key)
                        self.signin_address_limiter.failure(address_key)
                        raise PermissionError("Invalid local credentials")
                    self.signin_limiter.success(limiter_key)
                    self.signin_address_limiter.success(address_key)
                    token, csrf = session_token(), session_token()
                    expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
                    connection.execute("DELETE FROM sessions WHERE expires_at<=?", (now(),))
                    connection.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)", (secrets.token_hex(16), hashlib.sha256(token.encode()).hexdigest(), csrf, user["id"], expires, now()))
                secure = "; Secure" if self.secure_cookie else ""
                cookie = f"test3_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}"
                return self._json(200, {"signedIn": True}, cookie)
            user = self._identity()
            if parts == ["api", "signout"]:
                self._authorize_post(user, "read")
                with self.service.db.connect() as connection:
                    connection.execute("DELETE FROM sessions WHERE token_hash=?", (user["session_token_hash"],))
                secure = "; Secure" if self.secure_cookie else ""
                cookie = f"test3_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure}"
                return self._json(200, {"signedIn": False}, cookie)
            if len(parts) == 4 and parts[:2] == ["api", "documents"] and parts[3] == "purge-original":
                self._authorize_post(user, "document.purge")
                payload = self._payload()
                self._reauthorize(user, payload.get("current_password"))
                return self._json(200, self.service.purge_original_document(user["organization_id"], user["id"], parts[2], payload.get("reason", "")))
            if parts == ["api", "deals"]:
                self._authorize_post(user, "deal.create")
                return self._json(201, self.service.create_deal(user["organization_id"], user["id"], self._payload()))
            if len(parts) == 4 and parts[:2] == ["api", "deals"] and parts[3] == "upload":
                self._authorize_post(user, "document.upload")
                filename = self.headers.get("X-Filename", "upload")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > self.service.max_upload_bytes:
                    raise ValueError("Upload exceeds the configured file-size limit")
                content = self.rfile.read(length)
                return self._json(201, self.service.upload(user["organization_id"], user["id"], parts[2], filename, content))
            if len(parts) == 4 and parts[:2] == ["api", "deals"] and parts[3] == "reconcile":
                self._authorize_post(user, "reconcile.run")
                return self._json(200, self.service.run_reconciliation(user["organization_id"], user["id"], parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "deals"] and parts[3] == "assumptions":
                self._authorize_post(user, "assumption.create")
                return self._json(201, self.service.create_assumption(user["organization_id"], user["id"], parts[2], self._payload()))
            if len(parts) == 4 and parts[:2] == ["api", "deals"] and parts[3] == "market-panel":
                self._authorize_post(user, "assumption.create")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 16 * 1024 * 1024:
                    raise ValueError("Market panel exceeds the 16 MiB limit")
                metadata = {
                    "source_name": self.headers.get("X-Source-Name", ""), "source_version": self.headers.get("X-Source-Version", ""),
                    "as_of_date": self.headers.get("X-As-Of-Date", ""), "licensing_notes": self.headers.get("X-Licensing-Notes", ""),
                    "freshness_state": self.headers.get("X-Freshness-State", "unknown"),
                }
                return self._json(201, self.service.import_market_panel(user["organization_id"], user["id"], parts[2], self.headers.get("X-Filename", "market-panel.csv"), self.rfile.read(length), metadata))
            if len(parts) == 5 and parts[:2] == ["api", "deals"] and parts[3:] == ["assumption-intelligence", "market-rent-growth"]:
                self._authorize_post(user, "assumption.create")
                return self._json(201, self.service.run_market_rent_growth(user["organization_id"], user["id"], parts[2], self._payload()))
            if len(parts) == 4 and parts[:2] == ["api", "assumption-runs"] and parts[3] == "decision":
                self._authorize_post(user, "assumption.review")
                payload = self._payload()
                return self._json(200, self.service.decide_assumption_run(user["organization_id"], user["id"], parts[2], str(payload.get("selection", "")), payload.get("custom_value"), str(payload.get("rationale", "")), str(payload.get("controlling_source", ""))))
            if len(parts) == 4 and parts[:2] == ["api", "values"] and parts[3] == "review":
                self._authorize_post(user, "value.review")
                payload = self._payload()
                return self._json(200, self.service.review_value(user["organization_id"], user["id"], parts[2], payload.get("status"), payload.get("normalized_value"), payload.get("comments", "")))
            if len(parts) == 4 and parts[:2] == ["api", "assumptions"] and parts[3] == "review":
                self._authorize_post(user, "assumption.review")
                payload = self._payload()
                return self._json(200, self.service.review_assumption(user["organization_id"], user["id"], parts[2], payload.get("status"), payload.get("normalized_value"), payload.get("comments", "")))
            if len(parts) == 4 and parts[:2] == ["api", "findings"] and parts[3] == "resolve":
                self._authorize_post(user, "finding.resolve")
                return self._json(200, self.service.resolve_finding(user["organization_id"], user["id"], parts[2], self._payload().get("notes", "")))
            if len(parts) == 5 and parts[:2] == ["api", "deals"] and parts[3] == "export":
                self._authorize_post(user, "export.generate")
                return self._json(200, self.service.export(user["organization_id"], user["id"], parts[2], parts[4]))
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
    test1_data = os.getenv("TEST3_TEST1_DATA_DIR")
    Handler.service = Service(data_dir, int(os.getenv("TEST3_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))), Path(test1_data) if test1_data else None)
    Handler.secure_cookie = os.getenv("TEST3_SECURE_COOKIE", "0") == "1"
    if os.getenv("TEST3_DEMO_MODE", "0") == "1":
        Handler.service.seed()
    elif not Handler.service.has_users():
        raise SystemExit("No local administrator exists. Run test3-init-admin --email you@example.test, or explicitly set TEST3_DEMO_MODE=1 for fictional demonstration data.")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"test3 is running locally at http://{host}:{port}")
    print("ZERO-COST CHECK PASSED: No application component can create a charge for the repository owner.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
