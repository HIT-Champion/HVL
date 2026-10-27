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

"""Kiểm bản chạy công khai qua HTTPS từ bên ngoài, như trình duyệt của người dùng thấy (F1.9, #197):
.github/workflows/ban-online.yml gọi mỗi ngày, chạy tay được.

- Chứng chỉ: hợp lệ với kho CA của máy chạy, đúng tên máy, TLS từ 1.2, còn ít nhất ``--min-days`` ngày.
- HTTP chuyển sang HTTPS: ``http://<máy>/`` trả mã chuyển hướng về ``https://<máy>``.
- ``/api/status`` trả 200, ``status`` là ``ok`` hoặc ``degraded`` (thành phần không ``ok`` in thành cảnh báo, ``down``
  là lỗi), ``version`` đúng ``--version`` nếu có. Bản dựng từ git (reconciler theo nhánh: ``git describe --tags
  --always``, ra ``<băm>`` hay ``<thẻ>-<n>-g<băm>``) thì ``--commit`` (lặp được): băm đó là đầu của một commit đã nêu.
- Keycloak sau proxy: ``issuer`` OIDC của realm là ``https://<máy>/realms/moc``, ``authorization_endpoint`` và
  ``token_endpoint`` nằm dưới đó. Proxy không chuyển đúng ``X-Forwarded-*`` thì Keycloak sinh URL ``http://`` hay có
  ``:9080``, và đăng nhập hỏng.
- Header bảo mật của cổng đi qua proxy: trang chủ còn ``Content-Security-Policy`` và
  ``X-Content-Type-Options: nosniff``.

  python3 scripts/kiem_ban_online.py https://signet.htechcs.com [--version 1.2.0] [--min-days 14]
  python3 scripts/kiem_ban_online.py https://signet-dev.htechcs.com --commit <sha đầu develop> [--commit <sha>…]

Chạy hết các mục rồi báo mục trượt. Thoát 0 khi đạt, 1 khi có mục trượt, 2 khi gọi sai. Chỉ dùng thư viện chuẩn.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

REALM = "moc"
TIMEOUT_S = 20
MAX_BODY = 1 << 20          # /api/status, cấu hình OIDC chỉ vài KiB; trang lạ thì không đọc quá 1 MiB
MIN_DAYS = 14               # Let's Encrypt gia hạn khi còn 30 ngày: dưới 14 ngày là việc gia hạn đã hỏng
TLS_OK = ("TLSv1.2", "TLSv1.3")
REDIRECTS = (301, 302, 307, 308)
USER_AGENT = "signet-kiem-ban-online"
# phiên bản `git describe --tags --always` (bỏ v): băm rút gọn, hay sau thẻ gần nhất `<thẻ>-<n>-g<băm>`
DESCRIBED = re.compile(r"(?:.+-g)?([0-9a-f]{7,40})")


@dataclass
class Reply:
    status: int
    headers: dict[str, str]     # tên header viết thường
    body: bytes = b""


class Site(Protocol):
    def certificate(self) -> tuple[dict[str, Any], str]:
        """Chứng chỉ đã xác thực (``getpeercert()``) và phiên bản TLS; lỗi xác thực thì ném ``ssl.SSLError``."""

    def get(self, url: str) -> Reply:
        """GET, không theo chuyển hướng; lỗi mạng hay TLS thì ném ``OSError``."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class Internet:
    """Gọi thật: kho CA của máy, kiểm tên máy (``ssl.create_default_context``)."""

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self._open = urllib.request.build_opener(_NoRedirect).open

    def certificate(self) -> tuple[dict[str, Any], str]:
        ctx = ssl.create_default_context()
        with socket.create_connection((self.host, self.port), timeout=TIMEOUT_S) as raw, \
                ctx.wrap_socket(raw, server_hostname=self.host) as tls:
            return tls.getpeercert() or {}, tls.version() or ""

    def get(self, url: str) -> Reply:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._open(request, timeout=TIMEOUT_S) as r:
                return Reply(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(MAX_BODY))
        except urllib.error.HTTPError as e:     # 3xx (không theo), 4xx, 5xx: vẫn là một câu trả lời
            return Reply(e.code, {k.lower(): v for k, v in e.headers.items()}, e.read(MAX_BODY))


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, item: str, detail: str) -> None:
        print(f"✓ {item}: {detail}")

    def fail(self, item: str, why: str) -> None:
        print(f"✗ {item}: {why}")
        self.errors.append(f"{item}: {why}")

    def warn(self, item: str, why: str) -> None:
        print(f"! {item}: {why}")
        self.warnings.append(f"{item}: {why}")


def _json(reply: Reply) -> Any:
    try:
        return json.loads(reply.body)
    except ValueError:
        return None


def check_certificate(site: Site, report: Report, min_days: int, now: float) -> None:
    item = "chứng chỉ"
    try:
        cert, version = site.certificate()
    except OSError as e:        # gồm ssl.SSLCertVerificationError: hết hạn, sai tên máy, CA lạ
        report.fail(item, f"bắt tay TLS lỗi: {e}")
        return
    if version not in TLS_OK:
        report.fail(item, f"{version or 'không rõ phiên bản TLS'}, cần TLS 1.2 trở lên")
    try:
        days = (ssl.cert_time_to_seconds(cert["notAfter"]) - now) / 86400
    except (KeyError, ValueError):
        report.fail(item, "không đọc được hạn của chứng chỉ")
        return
    issuer = dict(pair for rdn in cert.get("issuer", ()) for pair in rdn)
    detail = f"{issuer.get('organizationName', 'CA không rõ')}, {version}, hết hạn {cert['notAfter']}"
    if days < min_days:
        report.fail(item, f"chỉ còn {days:.0f} ngày (dưới {min_days}): {detail}")
    elif version in TLS_OK:
        report.ok(item, f"{detail}, còn {days:.0f} ngày")


def check_redirect(site: Site, report: Report, host: str, base: str) -> None:
    item = "HTTP chuyển sang HTTPS"
    try:
        reply = site.get(f"http://{host}/")
    except OSError as e:
        report.fail(item, f"http://{host}/ không trả lời: {e}")
        return
    location = reply.headers.get("location", "")
    if reply.status in REDIRECTS and (location == base or location.startswith(base + "/")):
        report.ok(item, f"{reply.status} → {location}")
    else:
        went = f" → {location}" if location else ""
        report.fail(item, f"http://{host}/ trả {reply.status}{went}, cần chuyển về {base}")


def built_from(running: Any, commits: list[str]) -> bool:
    m = DESCRIBED.fullmatch(running) if isinstance(running, str) else None
    return bool(m) and any(c.startswith(m[1]) for c in commits)


def check_status(site: Site, report: Report, base: str, version: str | None, commits: list[str]) -> None:
    item = "/api/status"
    try:
        reply = site.get(f"{base}/api/status")
    except OSError as e:
        report.fail(item, f"không gọi được: {e}")
        return
    status = _json(reply)
    if reply.status != 200 or not isinstance(status, dict):
        report.fail(item, f"trả {reply.status}, không phải JSON trạng thái")
        return
    state, running = status.get("status"), status.get("version")
    bad = [f"{c.get('label') or c.get('id')}: {c.get('status')}" for c in status.get("components") or []
           if isinstance(c, dict) and c.get("status") not in ("ok", "off")]
    if state not in ("ok", "degraded"):
        report.fail(item, f"status {state}" + (" (" + "; ".join(bad) + ")" if bad else ""))
    elif version is not None and running != version:
        report.fail(item, f"chạy bản {running}, bản phát hành mới nhất là {version}")
    elif commits and not built_from(running, commits):
        more = f" (hay {len(commits) - 1} commit trước đó)" if len(commits) > 1 else ""
        report.fail(item, f"chạy bản {running}, không dựng từ commit {commits[0][:12]}{more}")
    else:
        report.ok(item, f"status {state}, bản {running}")
        if bad:
            report.warn(item, "thành phần không ok: " + "; ".join(bad))


def check_issuer(site: Site, report: Report, base: str) -> None:
    item = "Keycloak sau proxy"
    want = f"{base}/realms/{REALM}"
    try:
        reply = site.get(f"{want}/.well-known/openid-configuration")
    except OSError as e:
        report.fail(item, f"không gọi được cấu hình OIDC: {e}")
        return
    config = _json(reply)
    if reply.status != 200 or not isinstance(config, dict):
        report.fail(item, f"cấu hình OIDC trả {reply.status}")
        return
    # issuer lấy từ MOC_PUBLIC_URL; token_endpoint, authorization_endpoint mới theo header của proxy (sai thì ra
    # http://… hay :9080, docs/trien-khai.md mục 6)
    wrong = [] if config.get("issuer") == want else [f"issuer {config.get('issuer') or 'không có'}"]
    for key in ("authorization_endpoint", "token_endpoint"):
        if not str(config.get(key, "")).startswith(want + "/"):
            wrong.append(f"{key} {config.get(key) or 'không có'}")
    if wrong:
        report.fail(item, "; ".join(wrong) + f" — cần bắt đầu bằng {want}")
    else:
        report.ok(item, f"issuer, authorization_endpoint, token_endpoint dưới {want}")


def check_headers(site: Site, report: Report, base: str) -> None:
    item = "header bảo mật"
    try:
        reply = site.get(f"{base}/")
    except OSError as e:
        report.fail(item, f"không gọi được trang chủ: {e}")
        return
    missing = []
    if not reply.headers.get("content-security-policy", "").strip():
        missing.append("Content-Security-Policy")
    if reply.headers.get("x-content-type-options", "").strip().lower() != "nosniff":
        missing.append("X-Content-Type-Options: nosniff")
    if reply.status != 200:
        report.fail(item, f"trang chủ trả {reply.status}")
    elif missing:
        report.fail(item, "thiếu " + ", ".join(missing))
    else:
        report.ok(item, "Content-Security-Policy, X-Content-Type-Options: nosniff")


def check(site: Site, base: str, host: str, version: str | None, min_days: int, now: float,
          commits: list[str] | None = None) -> Report:
    report = Report()
    check_certificate(site, report, min_days, now)
    check_redirect(site, report, host, base)
    check_status(site, report, base, version, commits or [])
    check_issuer(site, report, base)
    check_headers(site, report, base)
    return report


def main(argv: list[str] | None = None, site: Callable[[str, int], Site] = Internet) -> int:
    parser = argparse.ArgumentParser(description="Kiểm bản chạy công khai qua HTTPS.")
    parser.add_argument("url", help="địa chỉ gốc, vd. https://signet.htechcs.com")
    want = parser.add_mutually_exclusive_group()
    want.add_argument("--version", help="phiên bản phải chạy, không có tiền tố v (vd. thẻ phát hành mới nhất)")
    want.add_argument("--commit", action="append", default=[],
                      help="bản phải dựng từ commit này (băm đủ 40 ký tự; lặp được: commit nào trong số đó cũng đạt)")
    parser.add_argument("--min-days", type=int, default=MIN_DAYS,
                        help=f"số ngày tối thiểu chứng chỉ còn hạn (mặc định {MIN_DAYS})")
    args = parser.parse_args(argv)
    url = urllib.parse.urlsplit(args.url)
    if url.scheme != "https" or not url.hostname or url.path.strip("/") or url.query or url.fragment:
        parser.error(f"cần địa chỉ gốc dạng https://<máy>, đang là {args.url}")
    host, port = url.hostname, url.port or 443
    base = f"https://{host}" + (f":{port}" if port != 443 else "")
    if args.version is not None and args.version.startswith("v"):
        args.version = args.version[1:]
    bad = [c for c in args.commit if not re.fullmatch(r"[0-9a-f]{40}", c)]
    if bad:
        parser.error(f"--commit cần băm SHA-1 đủ 40 ký tự thường, đang là {bad[0]}")

    report = check(site(host, port), base, host, args.version, args.min_days, time.time(), args.commit)
    annotate = bool(os.environ.get("GITHUB_ACTIONS"))
    for warning in report.warnings:
        if annotate:
            print(f"::warning::{base}: {warning}")
    if not report.errors:
        print(f"{base} đạt mọi mục kiểm.")
        return 0
    print(f"{base}: {len(report.errors)} mục trượt:")
    for error in report.errors:
        print(f"::error::{base}: {error}" if annotate else f"  - {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
