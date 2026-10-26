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

"""Phần máy chủ của Bảng tin (apps/bang-tin/server.py) chạy thật trên 127.0.0.1 cổng ngẫu nhiên, Keycloak và Hasura
giả là một máy chủ HTTP nhỏ: trang tĩnh, CSP, không lộ tệp ngoài public/; webhook kiểm bí mật, bỏ sự kiện không nghe,
ghi tin bằng token dịch vụ (giữ token, lấy lại khi Hasura báo JWT sai), trùng event_id là đã ghi, lỗi → 503 để Hasura
gửi lại. Chạy: python3 -m unittest discover -s apps/bang-tin/tests (make test)."""

from __future__ import annotations

import http.client
import http.server
import json
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from unittest import mock

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import server  # noqa: E402

SECRET = "bi-mat-thu-" + "x" * 20
EVENT = {"id": 41, "tenant_id": "00000000-0000-4000-8000-000000000001", "document_id":
         "00000000-0000-4000-8000-0000000000aa", "kind": "office.document.registered",
         "occurred_at": "2026-10-25T07:00:00+00:00"}


def hasura(new: Any = EVENT, *, op: str = "INSERT", table: Any = None) -> dict[str, Any]:
    """Thân sự kiện chuẩn Hasura v2 gửi (không request_transform), như đã đo trên Hasura thật."""
    return {"id": "8f2c4e0a-0000-4000-8000-000000000001", "created_at": "2026-10-25T07:00:01.5Z",
            "trigger": {"name": "app_bang_tin"}, "table": table or {"schema": "core", "name": "app_events"},
            "delivery_info": {"current_retry": 0, "max_retries": 5},
            "event": {"op": op, "data": {"old": None, "new": new}, "session_variables": None,
                      "trace_context": {"trace_id": "0", "span_id": "0"}}}


class Upstream(http.server.BaseHTTPRequestHandler):
    """Keycloak (token) và Hasura (/v1/graphql) giả; `script` quyết định câu trả lời GraphQL kế tiếp."""

    def log_message(self, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        srv: Any = self.server
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path.endswith("/protocol/openid-connect/token"):
            srv.tokens.append(urllib.parse.parse_qs(body.decode()))
            out: Any = {"access_token": f"tok-{len(srv.tokens)}", "expires_in": 300}
        else:
            srv.graphql.append((self.headers["Authorization"], json.loads(body)))
            out = srv.script.pop(0) if srv.script else {"data": {"insert_bang_tin_tin": {"affected_rows": 1}}}
            if out == 500:
                self.send_response(500)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start(handler: type, **attrs: Any) -> http.server.ThreadingHTTPServer:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    for k, v in attrs.items():
        setattr(srv, k, v)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return srv


def call(url: str, data: bytes | None = None, headers: dict[str, str] | None = None,
         method: str | None = None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.logs: list[dict[str, Any]] = []
        patcher = mock.patch.object(server, "log", lambda event, **f: self.logs.append({"event": event, **f}))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.up: Any = start(Upstream, tokens=[], graphql=[], script=[])
        base = f"http://127.0.0.1:{self.up.server_address[1]}"
        self.settings = server.Settings({"MOC_HOOK_SECRET": SECRET, "MOC_CLIENT_ID": "app-bang-tin-svc",
                                         "MOC_CLIENT_SECRET": "khong-in", "MOC_REALM": "moc",
                                         "MOC_KEYCLOAK_INTERNAL_URL": base, "MOC_GRAPHQL_INTERNAL_URL":
                                         f"{base}/v1/graphql"})
        self.servers = []
        for handler in (server.Page, server.Hook):
            srv = start(handler, settings=self.settings, token=server.ServiceToken(self.settings))
            self.servers.append(srv)
        self.page = f"http://127.0.0.1:{self.servers[0].server_address[1]}"
        self.hook = f"http://127.0.0.1:{self.servers[1].server_address[1]}"

    def tearDown(self) -> None:
        for srv in [self.up, *self.servers]:
            srv.shutdown()
            srv.server_close()

    def send(self, body: Any, secret: str | None = SECRET, path: str = "/su-kien") -> tuple[int, dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers["X-Moc-Hook-Secret"] = secret
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        status, _, out = call(self.hook + path, raw, headers)
        return status, json.loads(out)


class Page(Base):
    def test_static_files_with_headers(self) -> None:
        status, headers, body = call(self.page + "/bang-tin/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, headers, _ = call(self.page + "/bang-tin/tin.js")
        self.assertEqual((status, headers["Content-Type"]), (200, "text/javascript; charset=utf-8"))
        status, headers, _ = call(self.page + "/bang-tin", method="GET")
        self.assertEqual((status, headers["Location"]), (302, "/bang-tin/"))

    def test_config_health_and_spa_fallback(self) -> None:
        status, _, body = call(self.page + "/bang-tin/config.json")
        self.assertEqual(json.loads(body), {"realm": "moc", "clientId": "app-bang-tin"})
        self.assertNotIn(b"khong-in", body)
        self.assertEqual(call(self.page + "/bang-tin/healthz")[:1], (200,))
        index = call(self.page + "/bang-tin/")[2]
        self.assertEqual(call(self.page + "/bang-tin/dang-nhap#code=x")[2], index)

    def test_no_file_outside_public(self) -> None:
        index = call(self.page + "/bang-tin/")[2]
        for path in ("/bang-tin/../server.py", "/bang-tin/%2e%2e/server.py", "/bang-tin/..%2fserver.py",
                     "/bang-tin/%2e%2e%2fapp.yaml", "/bang-tin/%00", "/bang-tin/app.js%00.txt"):
            with self.subTest(path=path):
                status, _, body = call(self.page + path)
                self.assertEqual(status, 200)
                self.assertEqual(body, index)
        self.assertEqual(call(self.page + "/khac/")[0], 404)
        self.assertEqual(call(self.page + "/bang-tin/", b"{}", method="POST")[0], 501)

    def test_access_log_has_no_query_string(self) -> None:
        call(self.page + "/bang-tin/?code=bi-mat&state=x")
        call(self.page + "/bang-tin/", b"{}", method="POST")
        self.assertEqual(self.logs[0], {"event": "access", "method": "GET", "path": "/bang-tin/", "status": 200})
        self.assertEqual(self.logs[-1]["status"], 501)
        self.assertNotIn("bi-mat", json.dumps(self.logs))

    def test_head_has_no_body(self) -> None:
        status, headers, body = call(self.page + "/bang-tin/", method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertGreater(int(headers["Content-Length"]), 0)


class Hook(Base):
    def test_secret_required(self) -> None:
        for secret in (None, "", "sai", SECRET + "x"):
            with self.subTest(secret=secret):
                self.assertEqual(self.send(hasura(), secret=secret)[0], 401)
        self.settings.hook_secret = ""                      # chưa có bí mật: từ chối mọi lời gọi
        self.assertEqual(self.send(hasura(), secret="")[0], 401)
        self.assertEqual(self.up.graphql, [])
        self.assertEqual({e["event"] for e in self.logs}, {"hook.rejected"})
        self.assertNotIn(SECRET[:12], json.dumps(self.logs))

    def test_records_with_service_token_and_caches_it(self) -> None:
        status, out = self.send(hasura())
        self.assertEqual((status, out), (200, {"ok": True, "result": "ghi"}))
        self.send(hasura({**EVENT, "id": 42}))
        self.assertEqual(len(self.up.tokens), 1)
        form = self.up.tokens[0]
        self.assertEqual((form["grant_type"], form["client_id"]), (["client_credentials"], ["app-bang-tin-svc"]))
        auth, body = self.up.graphql[0]
        self.assertEqual(auth, "Bearer tok-1")
        self.assertEqual(body["variables"]["o"], {**{k: EVENT[k] for k in ("tenant_id", "document_id", "kind",
                                                                         "occurred_at")}, "event_id": 41})
        self.assertIn("insert_bang_tin_tin(objects: [$o])", body["query"])

    def test_not_listened_kinds_are_ignored(self) -> None:
        self.assertEqual(self.send(hasura({**EVENT, "kind": "office.document.received"}))[1],
                         {"ok": True, "ignored": True})
        self.assertEqual(self.up.graphql, [])

    def test_bad_body_is_400(self) -> None:
        for body in (b"khong-phai-json", [], {"data": EVENT}, {"event_id": "e", "data": EVENT}, hasura(None),
                     hasura({"id": 1}), hasura(op="UPDATE"), hasura(table={"schema": "office", "name": "documents"}),
                     hasura({**EVENT, "id": None}), hasura({**EVENT, "id": "abc"}), hasura({**EVENT, "id": [1]}),
                     hasura({**EVENT, "tenant_id": None}), hasura({**EVENT, "kind": ["office.document.issued"]})):
            with self.subTest(body=body):
                self.assertEqual(self.send(body)[0], 400)
        self.assertEqual(self.send(hasura(), path="/khac")[0], 404)
        self.assertEqual(self.up.graphql, [])

    def test_negative_content_length_is_400_not_a_hang(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.servers[1].server_address[1], timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest("POST", "/su-kien")
        conn.putheader("X-Moc-Hook-Secret", SECRET)
        conn.putheader("Content-Length", "-1")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 400)

    def test_duplicate_is_success(self) -> None:
        message = 'Uniqueness violation. duplicate key value violates unique constraint "tin_pkey"'
        self.up.script.append({"errors": [{"message": message, "extensions": {"code": "constraint-violation"}}]})
        self.assertEqual(self.send(hasura()), (200, {"ok": True, "result": "trùng"}))

    def test_upstream_errors_ask_hasura_to_retry(self) -> None:
        self.up.script.extend([500, {"errors": [{"message": "x", "extensions": {"code": "validation-failed"}}]}])
        self.assertEqual(self.send(hasura()), (503, {"error": "retry"}))
        self.assertEqual(self.send(hasura()), (503, {"error": "retry"}))

    def test_rejected_token_is_refreshed_once(self) -> None:
        self.up.script.append({"errors": [{"message": "JWTExpired", "extensions": {"code": "invalid-jwt"}}]})
        self.assertEqual(self.send(hasura())[0], 200)
        self.assertEqual([a for a, _ in self.up.graphql], ["Bearer tok-1", "Bearer tok-2"])


class Pure(unittest.TestCase):
    def test_kinds_match_manifest_and_migration(self) -> None:
        manifest = (APP / "app.yaml").read_text(encoding="utf-8")
        listed = manifest.split("kinds: [", 1)[1].split("]", 1)[0]
        self.assertEqual(server.KINDS, {k.strip() for k in listed.split(",")})
        sql = (APP / "migrations" / "0001_tin" / "up.sql").read_text(encoding="utf-8")
        for kind in server.KINDS:
            self.assertIn(f"'{kind}'", sql)

    def test_token_cache_expiry(self) -> None:
        now = [0.0]
        calls = []

        def fetch(url: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
            calls.append(url)
            return {"access_token": f"t{len(calls)}", "expires_in": 60}

        tok = server.ServiceToken(server.Settings({}), fetch=fetch, clock=lambda: now[0])
        self.assertEqual(tok.get(), "t1")
        now[0] = 29
        self.assertEqual(tok.get(), "t1")
        now[0] = 31
        self.assertEqual(tok.get(), "t2")
        self.assertEqual(calls[0], "http://keycloak:8080/realms/moc/protocol/openid-connect/token")


if __name__ == "__main__":
    unittest.main()
