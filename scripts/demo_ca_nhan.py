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

"""make demo-ca-nhan — ứng dụng thứ hai trên lõi Signet: Không gian cá nhân P.A.R.A (apps/ca-nhan,
docs/them-ung-dung.md).

Đi đúng đường của trình duyệt, qua cổng APISIX: mở /ca-nhan/; đăng nhập luồng code + PKCE bằng client riêng
`app-ca-nhan` — đã đăng nhập Văn phòng điện tử thì không hỏi lại mật khẩu (SSO); token mang đủ claim Hasura của lõi.
Với chính token đó: tải tệp lên /api/files của svc-files (ClamAV quét), xếp vào Dự án, liệt kê, chuyển sang Lưu trữ,
tải về đúng từng byte; tệp EICAR bị chặn như ở Văn phòng điện tử. Người khác cùng đơn vị không thấy, không tải được,
không xếp được tệp đó vào không gian của mình, không chuyển được mục của người khác. Mỗi lần xếp, chuyển là một dòng
sổ kiểm toán chuỗi băm của lõi, lãnh đạo khoa đọc được (không thấy tên thư mục). Lõi không sửa dòng nào cho ứng dụng
này: chỉ thêm cấu hình (client Keycloak, route APISIX, service compose) và schema riêng `personal`.

Cần make seed trước. Thoát 0: đạt; 1: có bước sai hoặc không gọi được Signet.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from moc_env import EICAR, PUBLIC_URL, REALM, USER_AGENT, ENV, HTTPError, Session, call_json, request, text_pdf

CLIENT = "app-ca-nhan"
BASE = "/ca-nhan/"
CALLBACK = f"{PUBLIC_URL}{BASE}dang-nhap"
OWNER, OTHER, DIRECTOR = "giangvienktpm", "chuyenviendt", "truongkhoa"   # seed/users.csv: staff, staff, director
TENANT_CNTT = "c300d5bb-028f-44cc-ba10-7b5277a4225d"
HASURA = "https://hasura.io/jwt/claims"

# Đúng các câu GraphQL của apps/ca-nhan/public/para.js (apps/ca-nhan/tests kiểm câu đó theo quyền Hasura)
QUERY_ITEMS = """query MyItems {
  personal_items(order_by: {updated_at: desc}) {
    file_id para created_at updated_at
    file { filename mime_type size_bytes scanned_at }
  }
}"""
PLACE_ITEM = """mutation Place($file: uuid!, $para: String!) {
  insert_personal_items_one(object: {file_id: $file, para: $para}) { file_id para }
}"""
MOVE_ITEM = """mutation Move($file: uuid!, $para: String!) {
  update_personal_items_by_pk(pk_columns: {file_id: $file}, _set: {para: $para}) { file_id para updated_at }
}"""


class DemoFailed(Exception):
    pass


def say(n: int, text: str) -> None:
    print(f"\n{n}. {text}")


def ok(text: str) -> None:
    print(f"   ✓ {text}")


def header(headers: dict[str, str], name: str) -> str:
    return next((v for k, v in headers.items() if k.lower() == name.lower()), "")


def claims_of(token: str) -> dict[str, Any]:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


class BrowserCookies(http.cookiejar.DefaultCookiePolicy):
    """Keycloak gắn Secure cho cookie phiên cả khi chạy http; trình duyệt coi http://localhost là ngữ cảnh an toàn
    nên vẫn gửi — làm giống vậy, chỉ với localhost (như scripts/smoke.py)."""

    def return_ok_secure(self, cookie, request) -> bool:
        return request.host.split(":")[0] in ("localhost", "127.0.0.1") or super().return_ok_secure(cookie, request)


def arrived(url: str, redirect_uri: str) -> bool:
    """Đã về tới ứng dụng: đúng địa chỉ chuyển hướng (trang của Keycloak cũng nằm dưới PUBLIC_URL/)."""
    return url.split("?", 1)[0] == redirect_uri and not urllib.parse.urlsplit(url).path.startswith("/realms/")


class Browser:
    """Một trình duyệt: giữ cookie phiên Keycloak giữa các ứng dụng, như SSO thật."""

    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar(policy=BrowserCookies())
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.opener.addheaders = [("User-Agent", USER_AGENT)]

    def authorize(self, client_id: str, redirect_uri: str, username: str | None,
                  verifier: str | None = None) -> tuple[str, str, bool]:
        """Luồng code + PKCE S256 tới lúc Keycloak chuyển về ứng dụng → (mã cấp quyền, code_verifier, có hỏi mật khẩu
        không). username None: phiên SSO phải đủ, Keycloak hỏi mật khẩu là lỗi."""
        verifier = verifier or base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = uuid.uuid4().hex
        query = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
                                        "scope": "openid", "state": state, "code_challenge": challenge,
                                        "code_challenge_method": "S256"})
        resp = self.opener.open(f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/auth?{query}", timeout=30)
        asked = False
        if not arrived(resp.geturl(), redirect_uri):
            page = resp.read().decode(errors="replace")
            form = re.search(r'<form[^>]*\saction="([^"]+)"', page)
            if username is None or form is None:
                raise DemoFailed(f"{client_id}: Keycloak hỏi đăng nhập lại thay vì chuyển về ứng dụng (SSO hỏng?)"
                                 if username is None else f"{client_id}: không thấy biểu mẫu đăng nhập")
            asked = True
            action = urllib.parse.urljoin(resp.geturl(), html.unescape(form.group(1)))
            resp = self.opener.open(action, timeout=30, data=urllib.parse.urlencode(
                {"username": username, "password": ENV["MOC_DEMO_PASSWORD"]}).encode())
            if 'name="otp"' in resp.read().decode(errors="replace"):
                raise DemoFailed(f"{username} bị hỏi mã TOTP — tài khoản giảng viên mẫu không cài TOTP; ai đã cài?")
        url = urllib.parse.urlsplit(resp.geturl())
        params = urllib.parse.parse_qs(url.query)
        if not arrived(resp.geturl(), redirect_uri) or "code" not in params:
            raise DemoFailed(f"{client_id}: Keycloak không chuyển về {redirect_uri} kèm mã cấp quyền ({url.path})")
        if params.get("state") != [state]:
            raise DemoFailed(f"{client_id}: state trả về không khớp")
        return params["code"][0], verifier, asked


def exchange(client_id: str, redirect_uri: str, code: str, verifier: str) -> dict[str, Any]:
    data, _ = call_json("POST", f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token",
                        form={"grant_type": "authorization_code", "client_id": client_id, "code": code,
                              "redirect_uri": redirect_uri, "code_verifier": verifier})
    return data


def as_session(username: str, token: str) -> Session:
    """Session của moc_env với token đã có (không đăng nhập lại qua moc-cli)."""
    s = Session.__new__(Session)
    s.username, s.token = username, token
    return s


def gql_errors(s: Session, query: str, variables: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    data, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": query, "variables": variables}, headers=s.auth)
    return data.get("data"), data.get("errors") or []


def run() -> None:
    print("Không gian cá nhân P.A.R.A — ứng dụng thứ hai trên lõi Signet, không sửa dòng nào của lõi")
    tag = uuid.uuid4().hex[:6].upper()

    say(1, f"Mở {PUBLIC_URL}{BASE} — trang tĩnh của app-ca-nhan qua APISIX, CSP chặn mã nội tuyến")
    status, headers, body = request("GET", f"{PUBLIC_URL}{BASE}")
    csp = header(headers, "Content-Security-Policy")
    if status != 200 or "Không gian cá nhân" not in body.decode() or "script-src 'self'" not in csp:
        raise DemoFailed(f"/ca-nhan/ trả {status}, CSP {csp!r}")
    _, _, raw = request("GET", f"{PUBLIC_URL}{BASE}config.json")
    config = json.loads(raw)
    if config != {"realm": REALM, "clientId": CLIENT}:
        raise DemoFailed(f"config.json: {config}")
    ok(f"200, {len(body)} byte; config.json: realm {REALM}, client {CLIENT}")

    say(2, f"{OWNER} đăng nhập Văn phòng điện tử, rồi mở Không gian cá nhân: client riêng, không hỏi lại mật khẩu")
    browser = Browser()
    code, verifier, asked = browser.authorize("app-office", f"{PUBLIC_URL}/", OWNER)
    exchange("app-office", f"{PUBLIC_URL}/", code, verifier)
    ok(f"app-office: nhập mật khẩu {'một lần' if asked else '— phiên đã có'}, nhận token")
    code, verifier, asked = browser.authorize(CLIENT, CALLBACK, None)
    tokens = exchange(CLIENT, CALLBACK, code, verifier)
    claims = claims_of(tokens["access_token"])
    ns = claims.get(HASURA) or {}
    if (claims.get("azp") != CLIENT or ns.get("x-hasura-default-role") != "staff"
            or ns.get("x-hasura-tenant-id") != TENANT_CNTT or not ns.get("x-hasura-user-id")):
        raise DemoFailed(f"token của {CLIENT}: azp {claims.get('azp')}, claim Hasura {sorted(ns)}")
    ok(f"{CLIENT}: Keycloak chuyển thẳng về {BASE}dang-nhap kèm mã (SSO), đổi mã bằng code_verifier → token azp "
       f"{CLIENT}, vai trò staff, đơn vị Khoa CNTT")
    code, _, _ = browser.authorize(CLIENT, CALLBACK, None)
    try:
        exchange(CLIENT, CALLBACK, code, "sai-" + verifier)
        raise DemoFailed("đổi mã với code_verifier sai mà vẫn được token — PKCE không được bắt buộc")
    except HTTPError as exc:
        if exc.status != 400:
            raise
    try:
        browser.authorize(CLIENT, f"{PUBLIC_URL}/ngoai-ca-nhan/", None)
        raise DemoFailed(f"{CLIENT} nhận redirect_uri ngoài {BASE}")
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
    ok("PKCE bắt buộc (code_verifier sai → 400); redirect_uri ngoài /ca-nhan/ → 400")

    owner = as_session(OWNER, tokens["access_token"])
    say(3, "Tải một tệp lên bằng token của ứng dụng — vẫn qua svc-files, ClamAV quét trước khi vào kho")
    name = f"ke-hoach-ca-nhan-{tag}.pdf"
    content = text_pdf("Ke hoach hoc ky", f"Ma thu {tag}")
    stored = owner.upload(name, content)
    if stored.get("encrypted") or stored.get("sha256") != hashlib.sha256(content).hexdigest():
        raise DemoFailed(f"svc-files trả {stored}")
    try:
        owner.upload(f"virus-{tag}.pdf", EICAR)
        raise DemoFailed("tệp EICAR không bị chặn")
    except HTTPError as exc:
        if exc.status != 422 or "infected" not in exc.body:
            raise DemoFailed(f"tệp EICAR trả {exc.status} {exc.body[:200]}") from exc
    ok(f"{name} → 201, SHA-256 {stored['sha256'][:16]}…; tệp EICAR → 422 infected, như ở Văn phòng điện tử")

    say(4, "Xếp vào Dự án, liệt kê, chuyển sang Lưu trữ — bảng personal.items của ứng dụng, quyền theo từng dòng")
    placed = owner.gql(PLACE_ITEM, {"file": stored["id"], "para": "projects"})["insert_personal_items_one"]
    mine = {i["file_id"]: i for i in owner.gql(QUERY_ITEMS)["personal_items"]}
    item = mine.get(stored["id"])
    if placed["para"] != "projects" or not item or item["file"]["filename"] != name:
        raise DemoFailed(f"sau khi xếp: {placed}, danh sách {item}")
    moved = owner.gql(MOVE_ITEM, {"file": stored["id"], "para": "archives"})["update_personal_items_by_pk"]
    if moved["para"] != "archives" or moved["updated_at"] <= item["updated_at"]:
        raise DemoFailed(f"sau khi chuyển: {moved}")
    _, errors = gql_errors(owner, MOVE_ITEM, {"file": stored["id"], "para": "thung-rac"})
    if not errors:
        raise DemoFailed("chuyển vào thư mục ngoài bốn thư mục P.A.R.A mà không bị chặn")
    ok(f"Dự án → Lưu trữ; {len(mine)} tệp trong không gian của {OWNER}; thư mục lạ bị CSDL chặn (items_para)")

    say(5, "Tải về từ Lưu trữ — cùng API /api/files/{id} của lõi, đúng từng byte")
    status, headers, got = request("GET", f"{PUBLIC_URL}/api/files/{stored['id']}", headers=owner.auth)
    if status != 200 or got != content:
        raise DemoFailed(f"tải về: {status}, {len(got)} byte (gửi {len(content)})")
    ok(f"200, {len(got)} byte, SHA-256 khớp; {header(headers, 'Content-Disposition')[:60]}")

    say(6, f"{OTHER} (cùng Khoa CNTT) không với tới được tệp và mục của {OWNER}")
    other = Session(OTHER)
    if any(i["file_id"] == stored["id"] for i in other.gql(QUERY_ITEMS)["personal_items"]):
        raise DemoFailed(f"{OTHER} thấy mục của {OWNER}")
    try:
        request("GET", f"{PUBLIC_URL}/api/files/{stored['id']}", headers=other.auth)
        raise DemoFailed(f"{OTHER} tải được tệp của {OWNER}")
    except HTTPError as exc:
        if exc.status != 404:
            raise
    _, errors = gql_errors(other, PLACE_ITEM, {"file": stored["id"], "para": "resources"})
    if not errors:
        raise DemoFailed(f"{OTHER} xếp được tệp của {OWNER} vào không gian của mình")
    data, errors = gql_errors(other, MOVE_ITEM, {"file": stored["id"], "para": "projects"})
    if errors or (data or {}).get("update_personal_items_by_pk") is not None:
        raise DemoFailed(f"{OTHER} chuyển được mục của {OWNER}: {data} {errors}")
    ok("danh sách không có; tải về → 404; xếp tệp của người khác → CSDL chặn (items_guard); chuyển mục của người "
       "khác → không có dòng nào khớp")

    say(7, "Sổ kiểm toán chuỗi băm của lõi: lãnh đạo khoa thấy ai xếp, chuyển tệp nào — không thấy tên thư mục")
    director = Session(DIRECTOR)
    rows: list[dict[str, Any]] = []
    for _ in range(10):
        rows = director.gql(
            """query ($id: String!) {
                 core_audit_log(where: {entity: {_eq: "personal.items"}, entity_id: {_eq: $id}}, order_by: {id: asc})
                 { id action actor_id overview hash }
               }""", {"id": stored["id"]})["core_audit_log"]
        if len(rows) >= 2:
            break
        time.sleep(1)
    actions = [r["action"] for r in rows]
    if actions != ["insert", "update"] or any(r["actor_id"] != ns["x-hasura-user-id"] for r in rows):
        raise DemoFailed(f"sổ kiểm toán của mục: {[(r['action'], r['actor_id']) for r in rows]}")
    if any((r["overview"] or {}).get("para") is not None for r in rows):
        raise DemoFailed(f"sổ lộ tên thư mục: {[r['overview'] for r in rows]}")
    ok(f"dòng #{rows[0]['id']} insert, #{rows[1]['id']} update · personal.items · người làm: {OWNER} · cột para "
       f"chỉ có tên · hash {str(rows[1]['hash']).removeprefix(chr(92) + 'x')[:16]}…")

    print(f"\nXem trên giao diện ({OWNER}): {PUBLIC_URL}{BASE}#archives")


def main() -> int:
    started = time.monotonic()
    try:
        run()
    except DemoFailed as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except (HTTPError, urllib.error.URLError, RuntimeError, OSError, KeyError, ValueError) as exc:
        print(f"\n✗ Không chạy được màn demo: {exc}. Signet có đang chạy và đã make seed chưa?", file=sys.stderr)
        return 1
    print(f"\nXong trong {time.monotonic() - started:.0f} giây.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
