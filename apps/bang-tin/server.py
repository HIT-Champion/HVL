# Copyright 2026 Signet Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Bảng tin đơn vị — phần máy chủ: một tiến trình Python thư viện chuẩn, chạy không quyền root.

  :8080  trang tĩnh dưới /bang-tin/ (route APISIX app-bang-tin, chỉ GET/HEAD), /bang-tin/config.json, /bang-tin/healthz.
         CSP script-src 'self'; nhật ký truy cập không ghi chuỗi truy vấn (như app-office, F4.4).
  :8081  POST /su-kien — webhook của Hasura Event Trigger app_bang_tin trên core.app_events. Không có route qua APISIX:
         chỉ container trong mạng nội bộ gọi tới. Kiểm header X-Moc-Hook-Secret (so khớp thời gian hằng), ghi một dòng
         bang_tin.tin bằng danh tính dịch vụ riêng (client credentials của app-bang-tin-svc → vai trò Hasura
         app_bang_tin, chỉ được thêm dòng vào bảng này). Trùng event_id → coi như đã ghi. Lỗi → 503: Hasura tự gửi lại.

Biến môi trường (moc app install đặt; bí mật từ .moc-apps/bang-tin.env, không nằm trong manifest): MOC_HOOK_SECRET,
MOC_CLIENT_ID, MOC_CLIENT_SECRET, MOC_REALM, MOC_KEYCLOAK_INTERNAL_URL, MOC_GRAPHQL_INTERNAL_URL (MOC_APP_EVENT_KINDS
lõi cũng đặt: loại manifest khai — trùng KINDS dưới đây, test kiểm).

Cách ly đơn vị: sự kiện mang tenant_id; tin ghi kèm đúng tenant_id đó, quyền đọc của Hasura lọc theo đơn vị của người
xem và chỉ hiện văn bản người đó được xem (`document.visible`). Bản thân sự kiện không có số ký hiệu, trích yếu: trang
hỏi GraphQL bằng token của người dùng.
"""

from __future__ import annotations

import hmac
import http.server
import json
import mimetypes
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PUBLIC = pathlib.Path(__file__).resolve().parent / "public"
BASE = "/bang-tin/"
KINDS = {"office.document.registered", "office.document.issued"}     # trùng app.yaml và CHECK của bang_tin.tin
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                               "connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                               "form-action 'self'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# insert_…(objects) { affected_rows }: vai trò app_bang_tin chỉ có quyền thêm, không có quyền đọc — insert_…_one và
# returning cần quyền đọc nên không dùng được
INSERT = """mutation Tin($o: bang_tin_tin_insert_input!) {
  insert_bang_tin_tin(objects: [$o]) { affected_rows }
}"""


def log(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


class Settings:
    def __init__(self, env: dict[str, str]):
        self.realm = env.get("MOC_REALM", "moc")
        self.hook_secret = env.get("MOC_HOOK_SECRET", "")
        self.client_id = env.get("MOC_CLIENT_ID", "")
        self.client_secret = env.get("MOC_CLIENT_SECRET", "")
        keycloak = env.get("MOC_KEYCLOAK_INTERNAL_URL", "http://keycloak:8080").rstrip("/")
        self.token_url = f"{keycloak}/realms/{self.realm}/protocol/openid-connect/token"
        self.graphql_url = env.get("MOC_GRAPHQL_INTERNAL_URL", "http://hasura:8080/v1/graphql")


class Upstream(Exception):
    """Keycloak hoặc Hasura chưa nhận: trả 503 để Hasura gửi lại sự kiện."""


def post(url: str, data: bytes, headers: dict[str, str], timeout: float = 8) -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise Upstream(f"HTTP {exc.code} từ {urllib.parse.urlsplit(url).netloc}") from None
    except (OSError, ValueError) as exc:
        raise Upstream(f"không gọi được {urllib.parse.urlsplit(url).netloc}: {exc}") from None


class ServiceToken:
    """Access token client credentials của app-bang-tin-svc, giữ tới 30 giây trước khi hết hạn."""

    def __init__(self, settings: Settings, fetch=post, clock=time.monotonic):
        self.settings, self._fetch, self._clock = settings, fetch, clock
        self._token, self._until = "", 0.0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token and self._clock() < self._until:
                return self._token
            form = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.settings.client_id,
                                           "client_secret": self.settings.client_secret}).encode()
            data = self._fetch(self.settings.token_url, form, {"Content-Type": "application/x-www-form-urlencoded"})
            if not data.get("access_token"):
                raise Upstream("Keycloak không trả access_token")
            self._token = data["access_token"]
            self._until = self._clock() + max(int(data.get("expires_in", 60)) - 30, 5)
            return self._token

    def forget(self) -> None:
        with self._lock:
            self._token, self._until = "", 0.0


FEED = {"schema": "core", "name": "app_events"}
COLUMNS = {"id", "tenant_id", "document_id", "kind", "occurred_at"}


def row_from(body: Any) -> dict[str, Any] | None:
    """Thân sự kiện chuẩn của Hasura (trigger app_bang_tin, INSERT trên core.app_events) → dòng bang_tin.tin. Lõi gửi
    mọi loại trong danh sách trắng: loại ứng dụng không nghe → None (trả 200, không ghi gì). session_variables lõi để
    null — không dùng. Sai dạng → ValueError (400, Hasura ghi lỗi)."""
    event = body.get("event") if isinstance(body, dict) else None
    if not isinstance(event, dict) or body.get("table") != FEED or event.get("op") != "INSERT":
        raise ValueError("thân không đúng dạng sự kiện Hasura (INSERT trên core.app_events)")
    data = (event.get("data") or {}).get("new") if isinstance(event.get("data"), dict) else None
    if not isinstance(data, dict) or not COLUMNS <= set(data):
        raise ValueError("event.data.new thiếu cột của core.app_events")
    if data["kind"] not in KINDS:
        return None
    return {"event_id": int(data["id"]), "tenant_id": str(data["tenant_id"]), "document_id": str(data["document_id"]),
            "kind": data["kind"], "occurred_at": str(data["occurred_at"])}


def record(row: dict[str, Any], token: ServiceToken, settings: Settings, fetch=post) -> str:
    """Ghi tin → 'ghi' | 'trùng'. Lỗi xác thực thì lấy token mới một lần."""
    body = json.dumps({"query": INSERT, "variables": {"o": row}}).encode()
    for attempt in (1, 2):
        out = fetch(settings.graphql_url, body, {"Content-Type": "application/json",
                                                 "Authorization": f"Bearer {token.get()}"})
        errors = out.get("errors") or []
        if not errors:
            return "ghi"
        codes = {(e.get("extensions") or {}).get("code") for e in errors}
        if "constraint-violation" in codes and "tin_pkey" in json.dumps(errors):
            return "trùng"
        if attempt == 1 and codes & {"invalid-jwt", "access-denied"}:
            token.forget()
            continue
        raise Upstream("Hasura từ chối: " + "; ".join(str(e.get("message"))[:120] for e in errors))
    raise Upstream("Hasura từ chối token dịch vụ")


class Page(http.server.BaseHTTPRequestHandler):
    server_version = "bang-tin"
    sys_version = ""

    def log_request(self, code: Any = "-", size: Any = "-") -> None:     # không ghi chuỗi truy vấn (F4.4)
        status = getattr(code, "value", code)
        log("access", method=self.command, path=urllib.parse.urlsplit(self.path).path,
            status=int(status) if str(status).isdigit() else None)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-cache") -> None:
        self.send_response(status)
        for k, v in HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == BASE.rstrip("/"):
            self.send_response(302)
            self.send_header("Location", BASE)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not path.startswith(BASE):
            self._send(404, b"not found\n", "text/plain; charset=utf-8")
            return
        rel = path[len(BASE):]
        if rel == "healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8", "no-store")
            return
        if rel == "config.json":
            cfg = {"realm": self.server.settings.realm, "clientId": "app-bang-tin"}       # type: ignore[attr-defined]
            self._send(200, json.dumps(cfg).encode(), "application/json", "no-store")
            return
        target = (PUBLIC / rel).resolve() if rel else PUBLIC / "index.html"
        if PUBLIC not in target.parents or not target.is_file():
            target = PUBLIC / "index.html"          # ứng dụng một trang: /bang-tin/dang-nhap… trả trang chính
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)


class Hook(http.server.BaseHTTPRequestHandler):
    server_version = "bang-tin"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        srv = self.server
        if urllib.parse.urlsplit(self.path).path != "/su-kien":
            self._reply(404, {"error": "not_found"})
            return
        given = self.headers.get("X-Moc-Hook-Secret", "")
        if not srv.settings.hook_secret or not hmac.compare_digest(given.encode(), srv.settings.hook_secret.encode()):
            log("hook.rejected", reason="secret")
            self._reply(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 65536:
                raise ValueError("thân quá lớn")
            row = row_from(json.loads(self.rfile.read(length) or b"null"))
        except ValueError as exc:
            log("hook.invalid", error=str(exc))
            self._reply(400, {"error": "invalid"})
            return
        if row is None:
            self._reply(200, {"ok": True, "ignored": True})
            return
        try:
            result = record(row, srv.token, srv.settings)
        except Upstream as exc:
            log("hook.retry", event_id=row["event_id"], error=str(exc))
            self._reply(503, {"error": "retry"})
            return
        log("hook.recorded", event_id=row["event_id"], tenant_id=row["tenant_id"], kind=row["kind"], result=result)
        self._reply(200, {"ok": True, "result": result})


def serve(settings: Settings, page_port: int = 8080, hook_port: int = 8081) -> None:
    token = ServiceToken(settings)
    servers = []
    for port, handler in ((page_port, Page), (hook_port, Hook)):
        srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
        srv.settings, srv.token = settings, token       # type: ignore[attr-defined]
        servers.append(srv)
    threading.Thread(target=servers[1].serve_forever, daemon=True).start()
    log("ready", page=page_port, hook=hook_port, hook_secret=bool(settings.hook_secret),
        service_identity=bool(settings.client_id and settings.client_secret))
    servers[0].serve_forever()


if __name__ == "__main__":
    try:
        serve(Settings(dict(os.environ)))
    except KeyboardInterrupt:
        sys.exit(0)
