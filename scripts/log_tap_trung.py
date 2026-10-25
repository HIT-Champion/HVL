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

"""Log tập trung (F3.14, profile logs — docs/van-hanh.md mục Log tập trung): chuẩn bị và tra Parseable.

    python3 scripts/log_tap_trung.py init                  # make logs-up gọi: chờ Parseable, tạo luồng, đặt giữ log
    python3 scripts/log_tap_trung.py tra <mã> [--phut 60]  # make logs-tra ID=…: dòng của mọi dịch vụ mang mã yêu cầu

Vector (platform/logs/vector.yaml) gửi mọi dòng vào luồng ``moc``; mã yêu cầu nằm ở cột ``request_id``. Parseable chỉ
nghe 127.0.0.1:MOC_LOGS_PORT, tài khoản ``moc`` với mật khẩu MOC_LOGS_PASSWORD trong .env — không in ra ở đâu cả.
Chỉ dùng thư viện chuẩn; hàm thuần ở đầu tệp test được không cần .env, không cần Docker.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

STREAM = "moc"              # trùng X-P-Stream trong platform/logs/vector.yaml (test kiểm)
USER = "moc"                # trùng P_USERNAME của dịch vụ parseable trong docker-compose.yml
MAX_DAYS = 36500            # Parseable nhận tối đa chừng này ngày
# Mã yêu cầu ghép vào câu SQL: chỉ nhận ký tự an toàn (uuid của APISIX, hex của svc-files/svc-workflow, goi-y:<việc>)
REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")


class ParseableError(Exception):
    def __init__(self, status: int, body: str, what: str) -> None:
        super().__init__(f"Parseable trả HTTP {status} khi {what}: {body[:300]}")
        self.status = status
        self.body = body


def valid_request_id(value: str) -> bool:
    return bool(REQUEST_ID_RE.fullmatch(value))


def query_body(request_id: str, minutes: int) -> dict[str, str]:
    """Thân POST /api/v1/query: mọi dòng mang mã này trong ``minutes`` phút gần nhất, cũ trước mới sau."""
    if not valid_request_id(request_id):
        raise ValueError(f"Mã yêu cầu không hợp lệ (chỉ chữ, số, . _ : -; tối đa 128 ký tự): {request_id!r}")
    if not 1 <= minutes <= MAX_DAYS * 24 * 60:
        raise ValueError(f"Số phút phải từ 1 tới {MAX_DAYS * 24 * 60}")
    return {"query": f"select * from {STREAM} where request_id = '{request_id}' order by p_timestamp",
            "startTime": f"{minutes}m", "endTime": "now"}


def retention_days(value: str) -> int:
    try:
        days = int(value)
    except ValueError:
        raise ValueError(f"MOC_LOGS_RETENTION_DAYS phải là số ngày nguyên: {value!r}") from None
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"MOC_LOGS_RETENTION_DAYS phải từ 1 tới {MAX_DAYS}: {days}")
    return days


def retention_body(days: int) -> list[dict[str, str]]:
    """Thân PUT /api/v1/logstream/<luồng>/retention: một tác vụ xóa dữ liệu cũ hơn ``days`` ngày."""
    return [{"description": f"Giữ log tập trung {days} ngày (MOC_LOGS_RETENTION_DAYS)", "action": "delete",
             "duration": f"{days}d"}]


def auth_header(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def table(rows: list[dict[str, Any]], width: int = 120) -> list[str]:
    """Mỗi dòng log một dòng in: giờ (UTC) · dịch vụ · sự kiện · đầu thông điệp."""
    out = []
    for row in rows:
        when = str(row.get("p_timestamp") or row.get("timestamp") or "")[:23]
        message = " ".join(str(row.get("message") or "").split())
        out.append(f"{when:23}  {row.get('service') or '?':12}  {row.get('event') or '-':28}  {message[:width]}")
    return out


class Parseable:
    """Gọi API Parseable bằng basic auth. Lỗi HTTP thành ``ParseableError`` (không kèm header nào của yêu cầu)."""

    def __init__(self, base_url: str, password: str, *, user: str = USER, timeout_s: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth = auth_header(user, password)
        self.timeout_s = timeout_s

    def call(self, method: str, path: str, body: Any = None, *, what: str, auth: bool = True) -> Any:
        headers = {"Authorization": self._auth} if auth else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise ParseableError(exc.code, exc.read().decode(errors="replace"), what) from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode(errors="replace")

    def wait_ready(self, timeout_s: float = 60) -> None:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                self.call("GET", "/api/v1/readiness", what="hỏi trạng thái", auth=False)
                return
            except (ParseableError, OSError):
                if time.monotonic() > deadline:
                    raise SystemExit(f"Parseable chưa sẵn sàng sau {timeout_s:.0f} giây ({self.base_url}) — "
                                     "xem: docker compose --profile logs logs parseable") from None
                time.sleep(2)

    def streams(self) -> list[str]:
        return [s["name"] for s in self.call("GET", "/api/v1/logstream", what="liệt kê luồng") or []]

    def ensure_stream(self) -> bool:
        """Tạo luồng ``moc`` nếu chưa có (Vector nạp trước thì Parseable đã tự tạo). True khi vừa tạo."""
        if STREAM in self.streams():
            return False
        self.call("PUT", f"/api/v1/logstream/{STREAM}", what=f"tạo luồng {STREAM}")
        return True

    def set_retention(self, days: int) -> list[dict[str, Any]]:
        """Đặt rồi đọc lại thời gian giữ log; đọc lại khác thì báo lỗi."""
        path = f"/api/v1/logstream/{STREAM}/retention"
        self.call("PUT", path, retention_body(days), what="đặt thời gian giữ log")
        got = self.call("GET", path, what="đọc thời gian giữ log") or []
        if [(t.get("action"), t.get("duration")) for t in got] != [("delete", f"{days}d")]:
            raise ParseableError(200, json.dumps(got, ensure_ascii=False), "đọc lại thời gian giữ log")
        return got

    def find(self, request_id: str, minutes: int = 60) -> list[dict[str, Any]]:
        """Dòng mang mã yêu cầu. Luồng chưa có dòng nào mang cột request_id thì Parseable trả 400: coi là chưa có."""
        try:
            rows = self.call("POST", "/api/v1/query", query_body(request_id, minutes), what="tra log")
        except ParseableError as exc:
            if exc.status == 400 and "request_id" in exc.body:
                return []
            raise
        return rows if isinstance(rows, list) else []


def base_url(env: dict[str, str]) -> str:
    return f"http://127.0.0.1:{env.get('MOC_LOGS_PORT') or '8400'}"


def client(env: dict[str, str]) -> Parseable:
    """Parseable theo các biến của .env (moc_env.load_env()); thiếu mật khẩu thì dừng, không đoán."""
    password = env.get("MOC_LOGS_PASSWORD", "")
    if not password or password.startswith("change_me"):
        raise SystemExit("Chưa có MOC_LOGS_PASSWORD trong .env — chạy: make logs-up (tự thêm, sinh như make env)")
    return Parseable(base_url(env), password)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log tập trung (F3.14): chuẩn bị và tra Parseable")
    sub = parser.add_subparsers(dest="lenh", required=True)
    sub.add_parser("init", help="chờ Parseable, tạo luồng moc, đặt giữ log MOC_LOGS_RETENTION_DAYS ngày")
    tra = sub.add_parser("tra", help="dòng của mọi dịch vụ mang một mã yêu cầu (X-Request-Id)")
    tra.add_argument("ma", help="mã yêu cầu: header X-Request-Id của phản hồi, hay câu 'đã ghi nhật ký với mã …'")
    tra.add_argument("--phut", type=int, default=60, help="tra trong bao nhiêu phút gần nhất (mặc định 60)")
    args = parser.parse_args(argv)

    if args.lenh == "tra" and not valid_request_id(args.ma):
        parser.error("thiếu hoặc sai mã yêu cầu — dùng: make logs-tra ID=<mã> (chữ, số, . _ : -; tối đa 128 ký tự)")
    from moc_env import ENV as env     # nạp ở đây: hàm thuần, test không cần .env

    api = client(env)
    try:
        if args.lenh == "init":
            days = retention_days(env.get("MOC_LOGS_RETENTION_DAYS") or "7")
            api.wait_ready()
            created = api.ensure_stream()
            api.set_retention(days)
            print(f"Log tập trung sẵn sàng: luồng {STREAM} ({'vừa tạo' if created else 'đã có'}), giữ {days} ngày; "
                  f"giao diện {api.base_url} (tài khoản {USER}, mật khẩu MOC_LOGS_PASSWORD trong .env)")
            return 0
        rows = api.find(args.ma, args.phut)
    except (ParseableError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Không gọi được Parseable ở {api.base_url} ({exc}) — đã bật chưa: make logs-up", file=sys.stderr)
        return 1
    if not rows:
        print(f"Không có dòng nào mang mã {args.ma} trong {args.phut} phút gần nhất (giờ UTC).")
        return 1
    print(f"{len(rows)} dòng mang mã {args.ma} (giờ UTC):")
    print("\n".join(table(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
