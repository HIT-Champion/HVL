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

"""Đổi, bù lịch giảng — máy chủ trang tĩnh: một tiến trình Python thư viện chuẩn, chạy không quyền root, hệ tệp gốc chỉ
đọc.

  :8080  trang dưới /lich-giang/ (route APISIX app-lich-giang, chỉ GET/HEAD), /lich-giang/config.json,
         /lich-giang/healthz. CSP script-src 'self'; nhật ký truy cập không ghi chuỗi truy vấn (như app-office, F4.4).

Ứng dụng không có phần máy chủ nghiệp vụ, không giữ bí mật: trang gọi thẳng API chung của lõi
(/api/workflow/lich-giang/…) bằng token của người dùng (client app-lich-giang), lõi kiểm quyền và chạy quy trình. Biến
môi trường lõi đặt: MOC_REALM (để trang biết realm đăng nhập).
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
import pathlib
import sys
import urllib.parse
from typing import Any

PUBLIC = pathlib.Path(__file__).resolve().parent / "public"
BASE = "/lich-giang/"
CLIENT_ID = "app-lich-giang"          # moc app install tạo client công khai app-<tên> (PKCE S256)
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                               "connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                               "form-action 'self'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def log(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


class Page(http.server.BaseHTTPRequestHandler):
    server_version = "lich-giang"
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
            cfg = {"realm": self.server.realm, "clientId": CLIENT_ID}       # type: ignore[attr-defined]
            self._send(200, json.dumps(cfg).encode(), "application/json", "no-store")
            return
        try:
            target = (PUBLIC / rel).resolve() if rel else PUBLIC / "index.html"
            found = PUBLIC in target.parents and target.is_file()
        except (ValueError, OSError):               # vd %00 (byte rỗng) trong đường dẫn: không có tệp nào như vậy
            found = False
        if not found:
            target = PUBLIC / "index.html"          # ứng dụng một trang: /lich-giang/dang-nhap… trả trang chính
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)


def serve(realm: str, port: int = 8080) -> None:
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), Page)
    srv.realm = realm           # type: ignore[attr-defined]
    log("ready", page=port, realm=realm)
    srv.serve_forever()


if __name__ == "__main__":
    try:
        serve(os.environ.get("MOC_REALM", "moc"))
    except KeyboardInterrupt:
        sys.exit(0)
