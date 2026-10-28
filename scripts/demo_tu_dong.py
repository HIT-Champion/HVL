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

"""make demo-tu-dong — tự động hóa bằng Node-RED (#366, profile tu-dong; cần make seed, make tu-dong-up).

Đi đúng đường của trình duyệt, qua cổng APISIX (WAF bật): /tu-dong/auth/strategy → Keycloak (client công khai
`tu-dong`, PKCE do Node-RED giữ) → mật khẩu, mã TOTP → Keycloak chuyển về /tu-dong/auth/strategy/callback, Node-RED đổi
mã lấy token, kiểm vai trò `operator` trong ID token rồi trả mã đổi một lần về trình soạn (/tu-dong/?code=…); trình
soạn đổi mã đó lấy token của Node-RED ở POST /tu-dong/auth/token. Kiểm:
- chưa đăng nhập: API trình soạn trả 401, trang đăng nhập chuyển sang Keycloak;
- người không có vai trò `operator` (giảng viên) qua Keycloak xong vẫn không nhận được mã, không vào được;
- người vận hành (`quantri`, được cấp vai trò bằng `moc tu-dong operator add`) vào được, triển khai được một flow có
  node Function, Template chứa mã JavaScript, HTML, câu GraphQL qua cổng mà WAF không chặn, đọc lại đúng flow đó;
- không có node exec, không cài node từ npm; WebSocket của trình soạn (/tu-dong/comms) bắt tay được qua cổng.

Thoát 0: đạt; 1: có bước sai hoặc không gọi được Signet.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import uuid

import tu_dong
from demo_ca_nhan import Browser, DemoFailed, ok, say
from moc_env import ENV, PUBLIC_URL, REALM, USER_AGENT, HTTPError, _otp_counter, request, totp_at

ROOT_URL = f"{PUBLIC_URL}{tu_dong.BASE}"
OPERATOR, OTHER = "quantri", "giangvienktpm"     # seed/users.csv: quản trị Khoa CNTT (TOTP); giảng viên Khoa CNTT
FLOW_TAB = "moc-demo-tu-dong"
# Mã của flow mẫu: trông như tấn công với bộ luật CRS (lệnh, HTML, câu truy vấn) nhưng là việc thường ngày của flow
FUNCTION = """// Văn bản Hỏa tốc vừa vào sổ: báo lãnh đạo (bản thu gọn của flow mẫu, #366 bước 2)
const doc = msg.payload || {};
if (doc.urgency !== 'hoa_toc') { return null; }
msg.query = 'query Due($t: timestamptz!) { office_documents(where: {due_at: {_lte: $t}}) { id summary } }';
msg.payload = { text: `Văn bản Hỏa tốc: ${doc.summary}`, link: '/van-ban/' + doc.id };
return msg;"""
TEMPLATE = "<p>Văn bản <b>{{payload.text}}</b> — <a href=\"{{payload.link}}\">mở</a></p>"


class Page:
    def __init__(self, url: str, body: str) -> None:
        self.url, self.body = url, body
        self.path = urllib.parse.urlsplit(url).path


def open_page(browser: Browser, url: str, data: dict[str, str] | None = None) -> Page:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        resp = browser.opener.open(url, data=body, timeout=30)
    except urllib.error.HTTPError as exc:
        raise DemoFailed(f"{url} → HTTP {exc.code} — xem: docker compose --profile tu-dong logs tu-dong") from None
    return Page(resp.geturl(), resp.read().decode(errors="replace"))


def login(username: str) -> Page:
    """Đăng nhập trình soạn như trình duyệt → trang Node-RED cuối cùng (URL mang ?code= hay ?session_message=)."""
    browser = Browser()
    page = open_page(browser, f"{ROOT_URL}auth/strategy")
    otp_sent = 0
    for _ in range(6):
        if not page.path.startswith(f"/realms/{REALM}/"):
            break
        form = re.search(r'<form[^>]*\saction="([^"]+)"', page.body)
        if form is None:
            raise DemoFailed(f"{username}: Keycloak không hỏi đăng nhập, cũng không chuyển về /tu-dong ({page.path})")
        if 'name="otp"' in page.body:
            if not ENV.get("MOC_DEMO_TOTP_SECRET") or otp_sent >= 3:
                raise DemoFailed(f"{username}: Keycloak không nhận mã TOTP (MOC_DEMO_TOTP_SECRET khác khóa make seed "
                                 "đã cài?)")
            if otp_sent:
                time.sleep(1.5)        # hai lần sai sát nhau thì Keycloak coi là dò mật khẩu
            fields = {"otp": totp_at(ENV["MOC_DEMO_TOTP_SECRET"], _otp_counter(username))}
            otp_sent += 1
        elif 'name="password"' in page.body:
            fields = {"username": username, "password": ENV["MOC_DEMO_PASSWORD"]}
        else:
            raise DemoFailed(f"{username}: trang Keycloak lạ ở {page.path} (cần đổi mật khẩu, cài TOTP?)")
        page = open_page(browser, urllib.parse.urljoin(page.url, html.unescape(form.group(1))), fields)
    if not page.path.startswith(tu_dong.BASE.rstrip("/")):
        raise DemoFailed(f"{username}: chưa về trình soạn Node-RED (dừng ở {page.path})")
    return page


def exchange_code(page: Page) -> str | None:
    """Mã đổi một lần Node-RED gắn vào URL, lấy NGUYÊN chữ như trình soạn (settings.js của editor-client đọc bằng biểu
    thức chính quy, không giải mã %, +): mã là base64 nên có + / =."""
    found = re.search(r"[?&]code=([^&]*)", urllib.parse.urlsplit(page.url).query)
    return found.group(1) if found else None


def editor_token(code: str) -> str:
    status, _, body = request("POST", f"{ROOT_URL}auth/token", data=urllib.parse.urlencode({"code": code}).encode(),
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = json.loads(body).get("accessToken") if status == 200 else None
    if not token:
        raise DemoFailed(f"POST /tu-dong/auth/token trả {status}, không có accessToken")
    return token


def api(method: str, path: str, token: str | None, body: object = None) -> tuple[int, object]:
    headers = {"Accept": "application/json", "Node-RED-API-Version": "v2"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        status, _, raw = request(method, f"{ROOT_URL}{path}", data=data, headers=headers)
    except HTTPError as exc:
        return exc.status, exc.body if hasattr(exc, "body") else str(exc)
    return status, json.loads(raw) if raw else None


def sample_flow() -> list[dict[str, object]]:
    return [
        {"id": FLOW_TAB, "type": "tab", "label": "Demo #366", "disabled": True, "info": ""},
        {"id": "moc-demo-fn", "type": "function", "z": FLOW_TAB, "name": "Hỏa tốc → lãnh đạo", "func": FUNCTION,
         "outputs": 1, "x": 200, "y": 80, "wires": [["moc-demo-tpl"]]},
        {"id": "moc-demo-tpl", "type": "template", "z": FLOW_TAB, "name": "Câu báo", "field": "payload",
         "fieldType": "msg", "format": "html", "syntax": "mustache", "template": TEMPLATE, "output": "str",
         "x": 420, "y": 80, "wires": [[]]},
    ]


def websocket_handshake() -> str:
    """Dòng trạng thái khi mở WebSocket /tu-dong/comms qua cổng (trình soạn dùng để nhận sự kiện)."""
    url = urllib.parse.urlsplit(PUBLIC_URL)
    port = url.port or (443 if url.scheme == "https" else 80)
    key = base64.b64encode(os.urandom(16)).decode()
    raw = socket.create_connection((url.hostname, port), timeout=15)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=url.hostname) if url.scheme == "https" else raw
    with sock:
        sock.sendall((f"GET {tu_dong.BASE}comms HTTP/1.1\r\nHost: {url.netloc}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                      f"Origin: {PUBLIC_URL}\r\nUser-Agent: {USER_AGENT}\r\n\r\n").encode())
        return sock.recv(1024).decode(errors="replace").split("\r\n", 1)[0]


def run() -> None:
    print("Tự động hóa bằng Node-RED — trình soạn ở /tu-dong/, đăng nhập Keycloak, chỉ vai trò operator (#366)")
    tag = uuid.uuid4().hex[:6].upper()

    # dữ liệu mẫu không có tài khoản vận hành nền tảng riêng: màn demo cấp vai trò cho quản trị Khoa CNTT
    say(1, f"Node-RED sau cổng APISIX: {ROOT_URL}auth/login; client Keycloak `tu-dong`, cấp operator cho {OPERATOR}")
    status, info = api("GET", "auth/login", None)
    if status != 200 or not isinstance(info, dict) or info.get("type") != "strategy":
        raise DemoFailed(f"/tu-dong/auth/login trả {status} {str(info)[:80]} — chạy make tu-dong-up trước")
    import tenants
    kc = tenants.connect()
    tu_dong.ensure_client(kc, PUBLIC_URL)
    tu_dong.set_operator(kc, OPERATOR)
    if OTHER in tu_dong.operators(kc):
        tu_dong.set_operator(kc, OTHER, revoke=True)
    ok(f"đăng nhập kiểu strategy (Keycloak), nút \"{info.get('prompts', [{}])[0].get('label', '?')}\"; người vận "
       f"hành: {', '.join(tu_dong.operators(kc))}")

    say(2, "Chưa đăng nhập: API trình soạn trả 401; mở trang đăng nhập thì sang Keycloak")
    status, _ = api("GET", "flows", None)
    if status != 401:
        raise DemoFailed(f"GET /tu-dong/flows không token trả {status}, không phải 401")
    anon = open_page(Browser(), f"{ROOT_URL}auth/strategy")
    if not anon.path.startswith(f"/realms/{REALM}/") or 'name="password"' not in anon.body:
        raise DemoFailed(f"/tu-dong/auth/strategy không chuyển sang trang đăng nhập Keycloak ({anon.path})")
    ok(f"GET /tu-dong/flows → 401; /tu-dong/auth/strategy → {anon.path}")

    say(3, f"{OTHER} (giảng viên, không có vai trò operator) đăng nhập Keycloak xong vẫn không vào được trình soạn")
    denied = login(OTHER)
    if exchange_code(denied) is not None or "session_message=" not in denied.url:
        raise DemoFailed(f"{OTHER} được Node-RED cấp mã vào trình soạn ({denied.path})")
    ok("Node-RED từ chối ở verify: không cấp mã, trình soạn báo đăng nhập không thành công")

    say(4, f"{OPERATOR} (mật khẩu + TOTP) đăng nhập: Node-RED cấp mã đổi một lần, đổi lấy token của trình soạn")
    code = exchange_code(login(OPERATOR))
    if not code:
        raise DemoFailed(f"{OPERATOR} có vai trò operator mà Node-RED không cấp mã")
    token = editor_token(code)
    status, settings = api("GET", "settings", token)
    user = settings.get("user", {}).get("username") if isinstance(settings, dict) else None
    if status != 200 or user != OPERATOR:
        raise DemoFailed(f"GET /tu-dong/settings bằng token trình soạn trả {status}, người dùng {user!r}")
    if api("POST", "auth/token", None, {"code": code})[0] != 400:
        raise DemoFailed("mã đổi một lần dùng lại được lần thứ hai")
    ok(f"token trình soạn của {OPERATOR}; mã đổi đã dùng thì dùng lại bị từ chối")

    say(5, "Triển khai flow có node Function, Template (JavaScript, HTML, câu GraphQL) qua cổng: WAF không chặn")
    status, current = api("GET", "flows", token)
    if status != 200 or not isinstance(current, dict):
        raise DemoFailed(f"GET /tu-dong/flows trả {status}")
    keep = [n for n in current.get("flows", []) if n.get("id") != FLOW_TAB and n.get("z") != FLOW_TAB]
    flow = sample_flow()
    flow[0]["info"] = f"Flow mẫu của make demo-tu-dong, lần {tag}"
    status, result = api("POST", "flows", token, {"flows": keep + flow, "rev": current.get("rev")})
    if status != 200:
        raise DemoFailed(f"POST /tu-dong/flows trả {status} {str(result)[:120]} (403 là WAF chặn — loại trừ 10081)")
    status, saved = api("GET", "flows", token)
    nodes = {n.get("id"): n for n in saved.get("flows", [])} if isinstance(saved, dict) else {}
    if nodes.get("moc-demo-fn", {}).get("func") != FUNCTION or tag not in str(nodes.get(FLOW_TAB, {}).get("info")):
        raise DemoFailed("đọc lại flow không đúng bản vừa triển khai")
    ok(f"đã triển khai, đọc lại đúng mã node Function (lần {tag}); flow để tắt, không chạy")

    say(6, "Khóa của Signet: không node exec, không cài node từ npm; WebSocket trình soạn bắt tay được qua cổng")
    status, types = api("GET", "nodes", token)
    names = {t for s in types for t in s.get("types", [])} if status == 200 and isinstance(types, list) else set()
    if not names or "exec" in names or "function" not in names:
        raise DemoFailed(f"GET /tu-dong/nodes trả {status}; exec có mặt hay thiếu node cơ bản")
    palette = settings.get("externalModules", {}).get("palette", {}) if isinstance(settings, dict) else {}
    if palette.get("allowInstall") is not False or palette.get("allowUpload") is not False:
        raise DemoFailed(f"trình soạn vẫn cho cài node: {palette}")
    line = websocket_handshake()
    if " 101 " not in f"{line} ":
        raise DemoFailed(f"WebSocket /tu-dong/comms qua cổng: {line!r}")
    ok(f"{len(names)} loại node, không có exec; palette không cài, không tải lên; /tu-dong/comms: {line}")
    print(f"\nĐẠT — trình soạn: {ROOT_URL} (đăng nhập bằng {OPERATOR})")


def main() -> int:
    try:
        run()
    except (DemoFailed, tu_dong.tenants.TenantError, tu_dong.tenants.Unavailable, urllib.error.URLError,
            OSError) as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
