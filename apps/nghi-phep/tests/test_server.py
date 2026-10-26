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

"""Máy chủ trang của Đơn nghỉ phép (apps/nghi-phep/server.py) chạy thật trên 127.0.0.1 cổng ngẫu nhiên: trang tĩnh,
CSP, config.json đúng client, không lộ tệp ngoài public/ (server.py, app.yaml, BPMN, form), chỉ GET/HEAD, nhật ký
không ghi chuỗi truy vấn. Chạy: python3 -m unittest discover -s apps/nghi-phep/tests (make test)."""

from __future__ import annotations

import http.server
import json
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request
from typing import Any
from unittest import mock

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import server  # noqa: E402


def call(url: str, data: bytes | None = None, method: str | None = None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=data, method=method)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class Page(unittest.TestCase):
    def setUp(self) -> None:
        self.logs: list[dict[str, Any]] = []
        patcher = mock.patch.object(server, "log", lambda event, **f: self.logs.append({"event": event, **f}))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Page)
        self.srv.realm = "moc"          # type: ignore[attr-defined]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    def test_static_files_with_headers(self) -> None:
        status, headers, body = call(self.base + "/nghi-phep/")
        self.assertEqual(status, 200)
        self.assertIn("Đơn nghỉ phép".encode(), body)
        csp = headers["Content-Security-Policy"]
        for rule in ("script-src 'self'", "connect-src 'self'", "frame-ancestors 'none'", "object-src 'none'"):
            self.assertIn(rule, csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        for name in ("app.js", "don.js", "auth.js", "schema-form.js"):
            with self.subTest(name=name):
                status, headers, _ = call(f"{self.base}/nghi-phep/{name}")
                self.assertEqual((status, headers["Content-Type"]), (200, "text/javascript; charset=utf-8"))
        status, headers, _ = call(self.base + "/nghi-phep/style.css")
        self.assertEqual((status, headers["Content-Type"]), (200, "text/css; charset=utf-8"))
        status, headers, _ = call(self.base + "/nghi-phep", method="GET")
        self.assertEqual((status, headers["Location"]), (302, "/nghi-phep/"))

    def test_config_health_and_spa_fallback(self) -> None:
        status, headers, body = call(self.base + "/nghi-phep/config.json")
        self.assertEqual((status, json.loads(body)), (200, {"realm": "moc", "clientId": "app-nghi-phep"}))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(call(self.base + "/nghi-phep/healthz")[:1], (200,))
        index = call(self.base + "/nghi-phep/")[2]
        self.assertEqual(call(self.base + "/nghi-phep/dang-nhap")[2], index)
        self.assertEqual(call(self.base + "/nghi-phep/khong-co.js")[2], index)

    def test_no_file_outside_public(self) -> None:
        index = call(self.base + "/nghi-phep/")[2]
        for path in ("/nghi-phep/../server.py", "/nghi-phep/%2e%2e/server.py", "/nghi-phep/..%2fapp.yaml",
                     "/nghi-phep/%2e%2e%2fworkflow/don-nghi-phep.bpmn20.xml", "/nghi-phep/..%2fforms/don.json",
                     "/nghi-phep/%2e%2e%2fpackage.json", "/nghi-phep/%00", "/nghi-phep/app.js%00.txt"):
            with self.subTest(path=path):
                status, _, body = call(self.base + path)
                self.assertEqual((status, body), (200, index))
        self.assertEqual(call(self.base + "/khac/")[0], 404)
        self.assertEqual(call(self.base + "/api/workflow/nghi-phep/tasks")[0], 404)

    def test_only_get_and_head(self) -> None:
        for method in ("POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(call(self.base + "/nghi-phep/", b"{}", method=method)[0], 501)
        status, headers, body = call(self.base + "/nghi-phep/", method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertGreater(int(headers["Content-Length"]), 0)

    def test_access_log_has_no_query_string(self) -> None:
        call(self.base + "/nghi-phep/dang-nhap?code=bi-mat&state=x")
        call(self.base + "/nghi-phep/", b"{}", method="POST")
        self.assertEqual(self.logs[0], {"event": "access", "method": "GET", "path": "/nghi-phep/dang-nhap",
                                        "status": 200})
        self.assertEqual(self.logs[-1]["status"], 501)
        self.assertNotIn("bi-mat", json.dumps(self.logs))


class Image(unittest.TestCase):
    def test_dockerfile_matches_manifest(self) -> None:
        """Cổng, đường kiểm sức khỏe trong Dockerfile và app.yaml trùng nhau; chạy không root; image chỉ mang trang."""
        docker = (APP / "Dockerfile").read_text(encoding="utf-8")
        manifest = (APP / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", docker)
        self.assertIn("EXPOSE 8080\n", docker)
        self.assertIn("\nport: 8080\n", manifest)
        for text in (docker, manifest):
            self.assertIn("http://127.0.0.1:8080/nghi-phep/healthz", text)
        copied = [line.split()[1] for line in docker.splitlines() if line.startswith("COPY ") and "--from" not in line]
        self.assertEqual(copied, ["package.json", "server.py", "public/"])
        self.assertEqual(server.BASE, "/nghi-phep/")
        self.assertIn("path: /nghi-phep\n", manifest)


if __name__ == "__main__":
    unittest.main()
