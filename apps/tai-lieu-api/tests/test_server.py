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

"""Máy chủ trang của Tài liệu API (apps/tai-lieu-api/server.py) chạy thật trên 127.0.0.1 cổng ngẫu nhiên: trang tĩnh,
CSP, config.json đúng client, bộ OpenAPI là JSON (thiếu thì 404, không trả trang HTML thay), không lộ tệp ngoài public/,
chỉ GET/HEAD, nhật ký không ghi chuỗi truy vấn; Dockerfile, docker-compose.yml khớp nhau.
Chạy: python3 -m unittest discover -s apps/tai-lieu-api/tests (make test)."""

from __future__ import annotations

import http.server
import json
import pathlib
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from typing import Any
from unittest import mock

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
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
        status, headers, body = call(self.base + "/tai-lieu-api/")
        self.assertEqual(status, 200)
        self.assertIn("Tài liệu API".encode(), body)
        csp = headers["Content-Security-Policy"]
        for rule in ("script-src 'self'", "style-src 'self'", "connect-src 'self'", "frame-ancestors 'none'",
                     "object-src 'none'"):
            self.assertIn(rule, csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        for name in ("app.js", "auth.js"):
            with self.subTest(name=name):
                status, headers, _ = call(f"{self.base}/tai-lieu-api/{name}")
                self.assertEqual((status, headers["Content-Type"]), (200, "text/javascript; charset=utf-8"))
        status, headers, _ = call(self.base + "/tai-lieu-api/style.css")
        self.assertEqual((status, headers["Content-Type"]), (200, "text/css; charset=utf-8"))
        status, headers, _ = call(self.base + "/tai-lieu-api", method="GET")
        self.assertEqual((status, headers["Location"]), (302, "/tai-lieu-api/"))

    def test_config_health_and_spa_fallback(self) -> None:
        status, headers, body = call(self.base + "/tai-lieu-api/config.json")
        self.assertEqual((status, json.loads(body)), (200, {"realm": "moc", "clientId": "app-tai-lieu-api"}))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(call(self.base + "/tai-lieu-api/healthz")[:1], (200,))
        index = call(self.base + "/tai-lieu-api/")[2]
        self.assertEqual(call(self.base + "/tai-lieu-api/dang-nhap")[2], index)
        self.assertEqual(call(self.base + "/tai-lieu-api/khong-co.js")[2], index)

    def test_openapi_is_json_and_missing_one_is_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            public = pathlib.Path(tmp) / "public"
            shutil.copytree(APP / "public", public)
            (public / "openapi").mkdir()
            (public / "openapi" / "loi.json").write_text('{"openapi": "3.1.0"}', encoding="utf-8")
            with mock.patch.object(server, "PUBLIC", public):
                status, headers, body = call(self.base + "/tai-lieu-api/openapi/loi.json")
                self.assertEqual((status, headers["Content-Type"]), (200, "application/json; charset=utf-8"))
                self.assertEqual(json.loads(body), {"openapi": "3.1.0"})
                status, _, body = call(self.base + "/tai-lieu-api/openapi/khong-co.json")
                self.assertEqual((status, body), (404, b"not found\n"))

    def test_no_file_outside_public(self) -> None:
        index = call(self.base + "/tai-lieu-api/")[2]
        for path in ("/tai-lieu-api/../server.py", "/tai-lieu-api/%2e%2e/server.py", "/tai-lieu-api/..%2fDockerfile",
                     "/tai-lieu-api/%2e%2e%2fchia_openapi.py", "/tai-lieu-api/%2e%2e%2fpackage.json",
                     "/tai-lieu-api/%00", "/tai-lieu-api/app.js%00.txt"):
            with self.subTest(path=path):
                status, _, body = call(self.base + path)
                self.assertEqual((status, body), (200, index))
        self.assertEqual(call(self.base + "/khac/")[0], 404)
        self.assertEqual(call(self.base + "/api/status")[0], 404)

    def test_only_get_and_head(self) -> None:
        for method in ("POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(call(self.base + "/tai-lieu-api/", b"{}", method=method)[0], 501)
        status, headers, body = call(self.base + "/tai-lieu-api/", method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertGreater(int(headers["Content-Length"]), 0)

    def test_access_log_has_no_query_string(self) -> None:
        call(self.base + "/tai-lieu-api/dang-nhap?code=bi-mat&state=x")
        call(self.base + "/tai-lieu-api/", b"{}", method="POST")
        self.assertEqual(self.logs[0], {"event": "access", "method": "GET", "path": "/tai-lieu-api/dang-nhap",
                                        "status": 200})
        self.assertEqual(self.logs[-1]["status"], 501)
        self.assertNotIn("bi-mat", json.dumps(self.logs))


class Image(unittest.TestCase):
    def test_dockerfile_matches_compose(self) -> None:
        """Cổng, đường kiểm sức khỏe, ngữ cảnh phụ openapi trùng giữa Dockerfile và docker-compose.yml; chạy không
        root; thư viện lấy từ npm lúc dựng, image chỉ mang trang."""
        docker = (APP / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", docker)
        self.assertIn("EXPOSE 8080\n", docker)
        self.assertIn("http://127.0.0.1:8080/tai-lieu-api/healthz", docker)
        self.assertIn("RUN npm ci --no-audit --no-fund --ignore-scripts\n", docker)
        copied = [line.split()[1] for line in docker.splitlines() if line.startswith("COPY ") and "--from" not in line]
        self.assertEqual(copied, ["package.json", "chia_openapi.py", "server.py", "public/"])
        self.assertIn("COPY --from=openapi svc-files.json svc-workflow.json ./in/\n", docker)
        build = re.search(r"\n  app-tai-lieu-api:\n(?:    .*\n)*?    build: (.+)\n", compose)
        self.assertIsNotNone(build, "docker-compose.yml: thiếu service app-tai-lieu-api")
        self.assertEqual(build.group(1),
                         "{context: ./apps/tai-lieu-api, additional_contexts: {openapi: ./docs/api/openapi}}")
        self.assertEqual(server.BASE, "/tai-lieu-api/")

    def test_page_loads_libraries_built_into_the_image(self) -> None:
        html = (APP / "public" / "index.html").read_text(encoding="utf-8")
        docker = (APP / "Dockerfile").read_text(encoding="utf-8")
        for src in re.findall(r'(?:src|href)="/tai-lieu-api/(lib/[^"]+)"', html):
            with self.subTest(src=src):
                self.assertFalse((APP / "public" / src).exists(), f"{src}: mã thư viện không nằm trong repo")
                self.assertIn(src.rsplit("/", 1)[1], docker)
        self.assertNotIn("http", "".join(re.findall(r'(?:src|href)="([^"]+)"', html)))   # không tải gì từ ngoài


if __name__ == "__main__":
    unittest.main()
