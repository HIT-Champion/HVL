# Copyright 2026 Mộc Team
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

"""Tiện ích chung cho seed.py và smoke.py: đọc .env, gọi HTTP, lấy token — chỉ dùng thư viện chuẩn."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Chuỗi kiểm thử chuẩn EICAR (không phải mã độc thật), ghép từ hai nửa để chính tệp này không bị phần mềm diệt
# virus chặn — dùng cho kiểm tra chặn (smoke.py) và màn demo kiểm dịch (demo.py)
EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode()


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit("Chưa có .env — chạy: make env")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    # biến môi trường đặt khi gọi lệnh được ưu tiên
    env.update({k: v for k, v in os.environ.items() if k in env})
    return env


ENV = load_env()
PUBLIC_URL = ENV["MOC_PUBLIC_URL"].rstrip("/")
REALM = ENV.get("MOC_REALM", "moc")
KEYCLOAK_ADMIN_URL = f"http://127.0.0.1:{ENV.get('KEYCLOAK_ADMIN_PORT', '8180')}"


class HTTPError(Exception):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} {url}: {body[:500]}")
        self.status = status
        self.body = body


def request(method: str, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None,
            timeout: float = 60) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        raise HTTPError(exc.code, exc.read().decode(errors="replace"), url) from None


def call_json(method: str, url: str, body=None, *, headers: dict[str, str] | None = None, form: dict | None = None):
    hdrs = dict(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    _, resp_headers, raw = request(method, url, data=data, headers=hdrs)
    return (json.loads(raw) if raw else None), resp_headers


def wait_for(url: str, what: str, timeout_s: int = 300) -> None:
    deadline = time.time() + timeout_s
    while True:
        try:
            request("GET", url, timeout=5)
            return
        except (HTTPError, OSError):
            if time.time() > deadline:
                sys.exit(f"{what} chưa sẵn sàng sau {timeout_s} giây ({url}) — xem: make logs")
            time.sleep(2)


def user_token(username: str, password: str | None = None) -> str:
    """Token của tài khoản qua client moc-cli (luồng mật khẩu), lấy qua APISIX như một ứng dụng thật."""
    data, _ = call_json(
        "POST",
        f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token",
        form={"grant_type": "password", "client_id": "moc-cli", "username": username,
              "password": password or ENV["MOC_DEMO_PASSWORD"], "scope": "openid"},
    )
    return data["access_token"]


class Session:
    """Một người dùng gọi Mộc qua cổng APISIX."""

    def __init__(self, username: str):
        self.username = username
        self.token = user_token(username)

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def gql(self, query: str, variables: dict | None = None) -> dict:
        data, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": query, "variables": variables or {}},
                            headers=self.auth)
        if data.get("errors"):
            raise RuntimeError(f"{self.username}: {data['errors'][0].get('message')}")
        return data["data"]

    def wait_task(self, doc_id: str, form_key: str, timeout_s: float = 20) -> str:
        """id của việc form_key trên văn bản doc_id trong hộp việc của người này (đợi Flowable tạo việc)."""
        deadline = time.time() + timeout_s
        while True:
            for t in self.gql("{ myTasks { id form_key document_id } }")["myTasks"]:
                if t["document_id"] == doc_id and t["form_key"] == form_key:
                    return t["id"]
            if time.time() > deadline:
                raise RuntimeError(f"{self.username} không thấy việc {form_key} của văn bản {doc_id}")
            time.sleep(1)

    def complete(self, task_id: str, outcome: str, data: dict) -> None:
        self.gql(
            "mutation ($t: String!, $o: String!, $d: jsonb) { completeTask(taskId: $t, outcome: $o, data: $d) { task_id } }",
            {"t": task_id, "o": outcome, "d": data},
        )

    def upload(self, filename: str, content: bytes, mime: str = "application/pdf", *, restricted: bool = False) -> dict:
        """restricted: tải lên cho văn bản hạn chế (F3.7) — svc-files mã hóa trước khi lưu, chỉ nhận PDF."""
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        url = f"{PUBLIC_URL}/api/files" + ("?restricted=true" if restricted else "")
        _, _, raw = request("POST", url, data=body,
                            headers={**self.auth, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        return json.loads(raw)


def text_pdf(*lines: str) -> bytes:
    """PDF một trang có lớp chữ (Helvetica, chỉ ASCII) — để kiểm tìm theo nội dung tệp (F2.7)."""
    def esc(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream = ("BT /F1 12 Tf 72 760 Td 14 TL " + " ".join(f"({esc(line)}) '" for line in lines) + " ET").encode()
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
            b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<</Size 6/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % xref


def compose(*args: str, stdin: bytes | None = None) -> bytes:
    cmd = ["docker", "compose", "--profile", "core", "--profile", "app", *args]
    return subprocess.run(cmd, cwd=ROOT, input=stdin, check=True, capture_output=True).stdout
