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
- không có node exec, file, watch; không cài node từ npm; WebSocket của trình soạn (/tu-dong/comms) bắt tay được
  qua cổng;
- robot của Khoa CNTT (`moc tu-dong robot add CNTT`) lấy token client_credentials: claim Hasura cố định vai trò
  `tu_dong`, đọc được văn bản của đơn vị, không đọc được nội dung văn bản, danh bạ, thông báo;
- hai flow mẫu (platform/tu-dong/flow-mau.json) triển khai kèm bí mật của robot: văn thư vào sổ văn bản Hỏa tốc thì
  trưởng khoa nhận đúng một thông báo gắn văn bản (chạy lại flow không báo trùng); flow 07:00 bấm tay gửi trưởng khoa
  một danh sách văn bản sắp hạn mỗi ngày. Flow mẫu để chạy tiếp sau màn demo.
--sau-khoi-phuc: chỉ đăng nhập lại và đọc flow của lần chạy trước — bước kiểm sau moc backup restore trong CI.

Thoát 0: đạt; 1: có bước sai hoặc không gọi được Signet.
"""

from __future__ import annotations

import argparse
import base64
import copy
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
from datetime import datetime, timedelta, timezone

import tu_dong
from demo_ca_nhan import Browser, DemoFailed, ok, say
from moc_env import (ENV, PUBLIC_URL, REALM, ROOT, USER_AGENT, HTTPError, Session, _otp_counter, call_json, request,
                     totp_at)

ROOT_URL = f"{PUBLIC_URL}{tu_dong.BASE}"
OPERATOR, OTHER = "quantri", "giangvienktpm"     # seed/users.csv: quản trị Khoa CNTT (TOTP); giảng viên Khoa CNTT
FLOW_TAB = "moc-demo-tu-dong"
UNIT = "CNTT"                                    # seed: robot của Khoa CNTT gửi cho trưởng khoa, văn thư nhập văn bản
DIRECTOR, CLERK = "truongkhoa", "vanthu"
CLAIMS = "https://hasura.io/jwt/claims"
VN = timezone(timedelta(hours=7))                # giờ Việt Nam, UTC+7 quanh năm
FLOW_MAU = ROOT / "platform" / "tu-dong" / "flow-mau.json"
MAU_TAB, HOA_TOC, HAN = "moc-flow-mau", "moc-mau-hoa-toc-inject", "moc-mau-han-inject"
NOTICES = """{ core_notifications(where: {kind: {_eq: "flow.message"}}, order_by: {created_at: desc}, limit: 50) {
  id document_id data created_at } }"""
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
    found = re.search(r"(?:^|&)code=([^&]*)", urllib.parse.urlsplit(page.url).query)
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
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:              # POST /inject/<id> trả chữ "OK", không phải JSON
        return status, raw.decode(errors="replace") if isinstance(raw, bytes) else raw


def sample_flow() -> list[dict[str, object]]:
    return [
        {"id": FLOW_TAB, "type": "tab", "label": "Demo #366", "disabled": True, "info": ""},
        {"id": "moc-demo-fn", "type": "function", "z": FLOW_TAB, "name": "Hỏa tốc → lãnh đạo", "func": FUNCTION,
         "outputs": 1, "x": 200, "y": 80, "wires": [["moc-demo-tpl"]]},
        {"id": "moc-demo-tpl", "type": "template", "z": FLOW_TAB, "name": "Câu báo", "field": "payload",
         "fieldType": "msg", "format": "html", "syntax": "mustache", "template": TEMPLATE, "output": "str",
         "x": 420, "y": 80, "wires": [[]]},
    ]


def robot_token(client_id: str, secret: str) -> str:
    """Token của robot như node HTTP của flow mẫu lấy: luồng client_credentials qua cổng."""
    data, _ = call_json("POST", f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token",
                        form={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
    return data["access_token"]


def claims_of(token: str) -> dict[str, object]:
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def graphql(token: str, query: str, variables: dict[str, object] | None = None) -> dict[str, object]:
    data, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": query, "variables": variables or {}},
                        headers={"Authorization": f"Bearer {token}"})
    return data


def flow_mau_body(current: dict[str, object], robot_id: str, secret: str) -> dict[str, object]:
    """Flow mẫu như người vận hành nhập rồi điền biến của tab: ROBOT_SECRET đặt ở `credentials` của chính node tab
    (Node-RED mã hóa vào flows_cred.json) — không đặt `credentials` ở gốc thân, Node-RED sẽ coi đó là toàn bộ thông tin
    đăng nhập của mọi node và thay hết."""
    nodes = copy.deepcopy(json.loads(FLOW_MAU.read_text(encoding="utf-8")))
    tab = next(n for n in nodes if n["type"] == "tab")
    for var in tab["env"]:
        if var["name"] == "ROBOT_ID":
            var["value"] = robot_id
    tab["credentials"] = {"ROBOT_SECRET": secret}
    keep = [n for n in current.get("flows", []) if n.get("id") != MAU_TAB and n.get("z") != MAU_TAB]
    return {"flows": keep + nodes, "rev": current.get("rev")}


def fire(token: str, inject: str) -> None:
    """Bấm nút của node inject (API trình soạn). POST /flows trả lời trước khi node chạy: 404 thì đợi, thử lại."""
    for _ in range(20):
        status, _ = api("POST", f"inject/{inject}", token)
        if status == 200:
            return
        time.sleep(1)
    raise DemoFailed(f"POST /tu-dong/inject/{inject} trả {status}: flow mẫu chưa chạy")


def vn_date(at: str) -> str:
    """Ngày theo giờ Việt Nam của một mốc timestamptz Hasura trả về. Hasura ghi mốc theo múi giờ của phiên Postgres
    (+00:00 hay +07:00 tùy máy): đổi múi giờ chứ không cộng 7 giờ, không thì sau 17:00 đã sang ngày mai."""
    return datetime.fromisoformat(at).astimezone(VN).strftime("%Y-%m-%d")


def wait_notices(director: Session, robot: str, doc_id: str | None, *, day: str | None = None,
                 timeout_s: float = 60) -> list[dict[str, object]]:
    """Thông báo flow.message của robot trong chuông của lãnh đạo: gắn văn bản doc_id, hoặc (doc_id None) không gắn
    văn bản và tạo trong ngày `day` (giờ Việt Nam)."""
    deadline = time.time() + timeout_s
    while True:
        rows = [n for n in director.gql(NOTICES)["core_notifications"]
                if n["document_id"] == doc_id and n["data"].get("robot") == robot
                and (day is None or vn_date(n["created_at"]) == day)]
        if rows or time.time() > deadline:
            return rows
        time.sleep(2)


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

    say(6, "Khóa của Signet: không node exec, file, watch; không cài node từ npm; WebSocket trình soạn qua cổng")
    status, types = api("GET", "nodes", token)
    names = {t for s in types for t in s.get("types", [])} if status == 200 and isinstance(types, list) else set()
    locked = names & {"exec", "file", "file in", "watch"}
    if not names or locked or "function" not in names:
        raise DemoFailed(f"GET /tu-dong/nodes trả {status}; còn node {sorted(locked)} hay thiếu node cơ bản")
    palette = settings.get("externalModules", {}).get("palette", {}) if isinstance(settings, dict) else {}
    if palette.get("allowInstall") is not False or palette.get("allowUpload") is not False:
        raise DemoFailed(f"trình soạn vẫn cho cài node: {palette}")
    line = websocket_handshake()
    if " 101 " not in f"{line} ":
        raise DemoFailed(f"WebSocket /tu-dong/comms qua cổng: {line!r}")
    ok(f"{len(names)} loại node, không có exec, file, watch; palette không cài, không tải lên; /tu-dong/comms: {line}")

    say(7, f"Robot của đơn vị {UNIT} (moc tu-dong robot add): token client_credentials, vai trò Hasura tu_dong")
    robot = tu_dong.add_robot(kc, UNIT)
    rtoken = robot_token(robot["client_id"], robot["secret"])
    hasura = claims_of(rtoken).get(CLAIMS) or {}
    if (hasura.get("x-hasura-default-role"), hasura.get("x-hasura-allowed-roles"), hasura.get("x-hasura-tenant-id"),
            hasura.get("x-hasura-user-id")) != ("tu_dong", ["tu_dong"], robot["tenant_id"], robot["client_id"]):
        raise DemoFailed(f"claim Hasura trong token của {robot['client_id']} không đúng: {hasura}")
    seen = graphql(rtoken, "{ office_documents(limit: 5) { id symbol urgency status due_on } }")
    if seen.get("errors") or not isinstance(seen.get("data", {}).get("office_documents"), list):
        raise DemoFailed(f"robot không đọc được văn bản của đơn vị: {str(seen)[:160]}")
    for query in ("{ office_documents(limit: 1) { body } }", "{ core_users { id } }", "{ core_notifications { id } }"):
        if not graphql(rtoken, query).get("errors"):
            raise DemoFailed(f"robot đọc được thứ không được đọc: {query}")
    ok(f"{robot['client_id']} ({robot['result']}): đọc {len(seen['data']['office_documents'])} văn bản của đơn vị; "
       "không đọc được nội dung văn bản, danh bạ, thông báo")

    say(8, "Nhập hai flow mẫu (platform/tu-dong/flow-mau.json), điền ROBOT_ID, ROBOT_SECRET của tab, triển khai")
    status, current = api("GET", "flows", token)
    status, result = api("POST", "flows", token, flow_mau_body(current, robot["client_id"], robot["secret"])) \
        if status == 200 and isinstance(current, dict) else (status, current)
    if status != 200:
        raise DemoFailed(f"triển khai flow mẫu: POST /tu-dong/flows trả {status} {str(result)[:120]}")
    status, secret = api("GET", f"credentials/tab/{MAU_TAB}", token)
    if status != 200 or secret != {"has_ROBOT_SECRET": True}:
        raise DemoFailed(f"Node-RED không giữ ROBOT_SECRET của tab {MAU_TAB}: {status} {secret}")
    ok(f"tab {MAU_TAB}: 07:00 hằng ngày văn bản sắp hạn; mỗi phút văn bản Hỏa tốc vừa vào sổ; bí mật robot chỉ còn "
       "dạng has_ROBOT_SECRET")

    say(9, f"{CLERK} vào sổ một văn bản Hỏa tốc hạn ngày mai → flow báo {DIRECTOR} (lãnh đạo đơn vị) ngay")
    clerk, director = Session(CLERK), Session(DIRECTOR)
    now = datetime.now(VN)
    today, due = now.strftime("%Y-%m-%d"), (now + timedelta(days=1)).strftime("%Y-%m-%d")
    symbol = f"{tag[:4]}/HT-ĐHCN"
    doc_id = clerk.gql("mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }", {"d": {
        "type_code": "CV", "symbol": symbol, "issuer_name": "Trường Đại học Công nghiệp", "issued_on": today,
        "urgency": "hoa_toc", "due_on": due, "summary": f"Về việc nộp báo cáo kiểm định gấp (demo #366, {tag})",
    }})["receiveIncoming"]["document_id"]
    clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": doc_id})
    fire(token, HOA_TOC)
    first = wait_notices(director, robot["client_id"], doc_id)
    if len(first) != 1 or symbol not in str(first[0]["data"]):
        raise DemoFailed(f"{DIRECTOR} có {len(first)} thông báo của flow cho văn bản Hỏa tốc {symbol}, không phải 1")
    fire(token, HOA_TOC)                # chạy lại: cùng khóa hoa-toc:<id>, máy chủ không báo lần nữa
    time.sleep(5)
    if len(again := wait_notices(director, robot["client_id"], doc_id, timeout_s=0)) != 1:
        raise DemoFailed(f"chạy lại flow Hỏa tốc: {DIRECTOR} có {len(again)} thông báo cho {symbol}")
    ok(f"\"{first[0]['data'].get('title')}\" — {symbol}, bấm vào mở văn bản; chạy lại flow không báo trùng")

    # khóa han:<ngày>: mỗi ngày một tin — đã báo hôm nay (07:00, lần chạy trước) thì bấm lại không báo thêm
    say(10, f"Flow 07:00 (bấm tay thay vì đợi giờ): {DIRECTOR} nhận danh sách văn bản đến hạn trong 3 ngày")
    fire(token, HAN)
    digest = wait_notices(director, robot["client_id"], None, day=today)
    if len(digest) != 1:
        raise DemoFailed(f"{DIRECTOR} có {len(digest)} danh sách văn bản sắp hạn hôm nay {today}, không phải 1")
    ok(f"\"{digest[0]['data'].get('title')}\" (một tin mỗi ngày)")
    print(f"\nĐẠT — trình soạn: {ROOT_URL} (đăng nhập bằng {OPERATOR}); flow mẫu đang chạy ở tab {MAU_TAB} (tắt: mở "
          "tab, Disable, Deploy)")


def operator_token() -> str:
    code = exchange_code(login(OPERATOR))
    if not code:
        raise DemoFailed(f"{OPERATOR} có vai trò operator mà Node-RED không cấp mã")
    return editor_token(code)


def after_restore() -> None:
    print("Node-RED sau khi khôi phục bản sao lưu (#366): flow triển khai trước lúc sao lưu còn nguyên")
    status, saved = api("GET", "flows", operator_token())
    nodes = {n.get("id"): n for n in saved.get("flows", [])} if isinstance(saved, dict) else {}
    if status != 200 or nodes.get("moc-demo-fn", {}).get("func") != FUNCTION:
        raise DemoFailed(f"GET /tu-dong/flows trả {status}; flow {FLOW_TAB} không còn như trước lúc sao lưu")
    ok(f"{OPERATOR} đăng nhập lại (vai trò operator còn trong Keycloak), đọc được flow {FLOW_TAB}: "
       f"{nodes[FLOW_TAB].get('info')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sau-khoi-phuc", action="store_true", help="chỉ kiểm flow của lần chạy trước còn đó")
    args = parser.parse_args(argv)
    try:
        after_restore() if args.sau_khoi_phuc else run()
    except (DemoFailed, tu_dong.tenants.TenantError, tu_dong.tenants.Unavailable, urllib.error.URLError,
            OSError) as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
