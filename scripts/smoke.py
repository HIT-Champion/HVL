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

"""make smoke — đi trọn luồng văn bản đến qua cổng APISIX, như người dùng thật (cần make seed trước).

văn thư tải công văn lên (qua ClamAV) → nhập văn bản (Action receiveIncoming; dữ liệu sai bị chặn ở svc-workflow
và ở CSDL, theo cùng schemas/van-ban-den.json với form) → vào sổ, có số đến → lãnh đạo khoa chỉ đạo, giao
Tổ Đào tạo chủ trì → tổ trưởng phân công chuyên viên → chuyên viên báo xong. Rồi luồng văn bản đi: chuyên
viên soạn công văn trả lời, xem trước → trình → tổ trưởng duyệt → lãnh đạo khoa ký → văn thư phát hành PDF có
mã QR; người ngoài tra mã và băm ở cổng xác thực không cần đăng nhập. Thông báo: tổ trưởng nhận tin việc mới
qua WebSocket (Centrifugo) ngay khi chuyên viên trình; để quá hạn thì timer Flowable nhắc rồi báo lãnh đạo (chỉ
kiểm khi MOC_SLA_DURATION ngắn, CI đặt PT20S). Sổ kiểm toán: neo đầu chuỗi ra bucket lạnh khóa ghi, tính lại cả
chuỗi ngoài CSDL (moc audit verify). Kèm các kiểm tra chặn: tệp EICAR, không token, đường quản trị,
đơn vị khác không thấy văn bản; văn thư đăng nhập trình duyệt phải nhập mã TOTP; giới hạn tốc độ.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.cookiejar
import json
import os
import pathlib
import re
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

from moc_env import ENV, PUBLIC_URL, REALM, HTTPError, Session, call_json, compose, request, text_pdf

DEPT_DT = "5cc372aa-304d-4574-896c-4f3e781a2ce7"
DEPT_KTPM = "7ee31261-b14c-4c42-8e1b-9a7e99935412"
# Chuỗi kiểm thử chuẩn EICAR (không phải mã độc thật), ghép từ hai nửa để chính tệp này không bị chặn
EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode()

passed = 0


def ok(message: str) -> None:
    global passed
    passed += 1
    print(f"  ✓ {message}")


def fail(message: str) -> None:
    print(f"  ✗ {message}")
    sys.exit(1)


def header(headers: dict[str, str], name: str) -> str | None:
    return next((v for k, v in headers.items() if k.lower() == name.lower()), None)


class BrowserCookies(http.cookiejar.DefaultCookiePolicy):
    """Keycloak gắn Secure cho cookie phiên cả khi chạy http; trình duyệt coi http://localhost là ngữ cảnh an
    toàn nên vẫn gửi — làm giống vậy, chỉ với localhost."""

    def return_ok_secure(self, cookie, request) -> bool:
        return request.host.split(":")[0] in ("localhost", "127.0.0.1") or super().return_ok_secure(cookie, request)


def browser_login(username: str) -> str:
    """Đăng nhập như trình duyệt (luồng code + PKCE của app-office) tới hết bước mật khẩu. Trả "otp" nếu
    Keycloak hỏi tiếp mã TOTP, "code" nếu đã chuyển về giao diện kèm mã cấp quyền."""
    jar = http.cookiejar.CookieJar(policy=BrowserCookies())
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    query = urllib.parse.urlencode({"client_id": "app-office", "redirect_uri": f"{PUBLIC_URL}/", "response_type": "code",
                                    "scope": "openid", "code_challenge": "x" * 43, "code_challenge_method": "S256"})
    page = opener.open(f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/auth?{query}", timeout=30).read().decode()
    form = re.search(r'<form[^>]*\saction="([^"]+)"', page) or fail(f"không thấy biểu mẫu đăng nhập cho {username}")
    resp = opener.open(html.unescape(form.group(1)), timeout=30, data=urllib.parse.urlencode(
        {"username": username, "password": ENV["MOC_DEMO_PASSWORD"]}).encode())
    url = urllib.parse.urlsplit(resp.geturl())  # trang của Keycloak có session_code=, không phải mã cấp quyền
    if not url.path.startswith("/realms/") and "code" in urllib.parse.parse_qs(url.query):
        return "code"
    return "otp" if 'name="otp"' in resp.read().decode() else "khác"


class Realtime:
    """Kết nối WebSocket tới /realtime như trình duyệt, nói giao thức JSON của Centrifugo — chỉ thư viện chuẩn."""

    def __init__(self, token: str) -> None:
        url = urllib.parse.urlsplit(PUBLIC_URL)
        port = url.port or (443 if url.scheme == "https" else 80)
        sock = socket.create_connection((url.hostname, port), timeout=15)
        if url.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=url.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET /realtime HTTP/1.1\r\nHost: {url.netloc}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                      f"Origin: {PUBLIC_URL}\r\n\r\n").encode())
        self.sock, self.buf, self.closed = sock, b"", None
        head = self._until(b"\r\n\r\n").decode(errors="replace")
        " 101 " in head.split("\r\n")[0] or fail(f"/realtime không nâng lên WebSocket: {head.splitlines()[0]}")
        self.send({"id": 1, "connect": {"token": token, "name": "smoke"}})
        self.reply = self.next(15)

    def _until(self, marker: bytes) -> bytes:
        while marker not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("đóng kết nối")
            self.buf += chunk
        head, self.buf = self.buf.split(marker, 1)
        return head

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("đóng kết nối")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        n = len(payload)
        size = bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack("!H", n)
        self.sock.sendall(bytes([0x80 | opcode]) + size + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, command: dict) -> None:
        self._frame(0x1, json.dumps(command).encode())

    def next(self, timeout: float) -> dict | None:
        """Lệnh kế tiếp từ máy chủ (trả lời ping ngay); None nếu máy chủ đóng kết nối hoặc hết giờ."""
        deadline = time.time() + timeout
        pending: list[dict] = getattr(self, "_pending", [])
        while not pending:
            self.sock.settimeout(max(deadline - time.time(), 0.01))
            try:
                first, second = self._read(2)
            except (TimeoutError, socket.timeout):
                return None
            self.sock.settimeout(15)  # đã có đầu khung: đọc trọn khung, không cắt giữa chừng theo hạn chờ
            n = second & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            payload, opcode = self._read(n), first & 0x0F
            if opcode == 0x8:
                self.closed = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                return None
            if opcode == 0x9:
                self._frame(0xA, payload)
            elif opcode == 0x1:
                for line in payload.decode().splitlines():
                    msg = json.loads(line) if line.strip() else None
                    if msg == {}:
                        self.send({})  # ping của Centrifugo → pong
                    elif msg:
                        pending.append(msg)
        self._pending = pending
        return pending.pop(0)

    def wait_push(self, match, timeout: float) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.next(deadline - time.time())
            if msg is None and self.closed is not None:
                return None
            data = ((msg or {}).get("push") or {}).get("pub", {}).get("data")
            if data and match(data):
                return data
        return None

    def close(self) -> None:
        try:
            self._frame(0x8, struct.pack("!H", 1000))
        finally:
            self.sock.close()


def sla_seconds() -> float | None:
    """MOC_SLA_DURATION đủ ngắn để chờ trong smoke (≤ 1 phút) → số giây; dài hơn thì None."""
    m = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+)S)?", ENV.get("MOC_SLA_DURATION", "PT24H"))
    seconds = (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 0
    return seconds if 0 < seconds <= 60 else None


def wait_notification(session: Session, doc_id: str, kind: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = session.gql("""query ($d: uuid!, $k: String!) {
            core_notifications(where: {document_id: {_eq: $d}, kind: {_eq: $k}}) { id } }""", {"d": doc_id, "k": kind})
        if found["core_notifications"]:
            return True
        time.sleep(2)
    return False


def main() -> None:
    print(f"Kiểm tra {PUBLIC_URL}")
    tag = uuid.uuid4().hex[:6].upper()

    print("Cổng APISIX")
    try:
        call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": "{ __typename }"})
        fail("GraphQL không token vẫn trả lời")
    except HTTPError as exc:
        exc.status == 401 or fail(f"GraphQL không token trả {exc.status}")
    ok("GraphQL không có token → 401")
    for path in ("/v1/metadata", "/v2/query", "/console", "/admin/master/console/", "/flowable-rest/service/repository/deployments"):
        try:
            request("GET", PUBLIC_URL + path)
            fail(f"{path} không bị chặn")
        except HTTPError as exc:
            exc.status == 404 or fail(f"{path} trả {exc.status}")
    ok("đường quản trị của Hasura, Keycloak, Flowable bị chặn ở cổng")

    clerk, director = Session("vanthu"), Session("truongkhoa")
    manager, staff = Session("totruongdt"), Session("chuyenviendt")
    other_tenant = Session("vanthukt")
    ok("5 tài khoản đăng nhập được (Keycloak, qua cổng)")

    print("Xác thực hai bước")
    step = browser_login("vanthu")
    step == "otp" or fail(f"văn thư đăng nhập trình duyệt không bị hỏi mã TOTP ({step})")
    ok("văn thư đăng nhập trên trình duyệt: qua mật khẩu vẫn phải nhập mã TOTP")
    step = browser_login("chuyenviendt")
    step == "code" or fail(f"chuyên viên đăng nhập trình duyệt chưa vào được ({step})")
    ok("chuyên viên (vai trò không bắt buộc TOTP): đúng mật khẩu là vào")

    print("Trạm kiểm dịch")
    try:
        clerk.upload("eicar.pdf", EICAR)
        fail("tệp EICAR không bị chặn")
    except HTTPError as exc:
        exc.status == 422 or fail(f"tệp EICAR trả {exc.status}")
    ok("tệp EICAR bị ClamAV chặn (422), không lưu")

    print("Luồng văn bản đến")
    # Văn bản hạn chế tiếp nhận TRƯỚC: svc-files đọc chữ PDF theo thứ tự tải lên, nên khi công văn dưới đã tìm được
    # theo nội dung mà tệp này vẫn chưa được đọc thì đúng là tệp của văn bản hạn chế bị bỏ qua (F2.7)
    secret_pdf = clerk.upload(f"han-che-{tag}.pdf", text_pdf(f"Danh sach nang luong truoc han MATKIN{tag}"))
    file = clerk.upload(f"cong-van-{tag}.pdf", text_pdf("De nghi Khoa ra soat chuong trinh dao tao nam hoc 2026-2027",
                                                        f"Ma kiem tra noi dung NOIDUNG{tag}"))
    ok(f"văn thư tải công văn lên, quét sạch ({file['sha256'][:12]}…)")
    incoming = {
        "type_code": "CV", "symbol": f"123/ĐHCN-ĐT{tag}", "issuer_name": "Trường Đại học Công nghiệp",
        "issued_on": datetime.now(timezone(timedelta(hours=7))).date().isoformat(), "urgency": "khan",   # giờ Việt Nam
        "summary": f"Về việc rà soát chương trình đào tạo năm học 2026–2027 (kiểm tra {tag})", "file_ids": [file["id"]],
    }
    receive = "mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id document { status files { role } } } }"
    clerk.gql(receive, {"d": {**incoming, "symbol": f"124/ĐHCN-TC{tag}", "restricted": True, "urgency": "normal",
                              "summary": f"Về việc nâng lương trước hạn (kiểm tra {tag})", "file_ids": [secret_pdf["id"]]}})
    doc = clerk.gql(receive, {"d": incoming})["receiveIncoming"]
    doc_id = doc["document_id"]
    doc["document"] == {"status": "received", "files": [{"role": "main"}]} or fail(f"văn bản mới chưa đúng: {doc}")
    ok("văn thư nhập văn bản đến kèm tệp (Action receiveIncoming)")

    print("Poka-yoke: dữ liệu văn bản đến sai bị chặn ở svc-workflow và CSDL, không chỉ ở form")
    direct, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", headers=clerk.auth, body={
        "query": "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }",
        "variables": {"o": {k: v for k, v in incoming.items() if k != "file_ids"}}})
    "insert_office_documents_one" in json.dumps(direct.get("errors")) \
        or fail(f"văn thư vẫn ghi thẳng được bảng văn bản: {direct}")
    ok("văn thư không ghi thẳng được bảng văn bản: văn bản đến chỉ vào qua Action")

    def rejected(data: dict) -> dict:
        body, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", headers=clerk.auth,
                            body={"query": receive, "variables": {"d": data}})
        return ((body.get("errors") or [{}])[0].get("extensions") or {}) if body else {}

    bad = rejected({**incoming, "symbol": " 124/ĐHCN-ĐT", "summary": "Ngắn", "status": "registered"})
    (bad.get("code"), bad.get("fields")) == ("invalid", {"symbol": "not", "summary": "minLength",
                                                         "status": "additionalProperties"}) \
        or fail(f"svc-workflow chưa trả lỗi từng trường: {bad}")
    ok("svc-workflow kiểm lại theo schemas/van-ban-den.json, trả lỗi từng trường về form")
    dup = rejected({**incoming, "issuer_name": incoming["issuer_name"].upper(), "file_ids": []})
    dup.get("code") == "duplicate" or fail(f"tiếp nhận trùng không bị chặn: {dup}")
    ok("tiếp nhận lần hai cùng cơ quan ban hành, số ký hiệu, ngày ban hành bị chặn")
    tampered = (f"begin;\ninsert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, "
                f"issued_on, summary, created_by) select tenant_id, 'in', 'received', type_code, symbol || ' sửa', "
                f"issuer_name || E'\\n', issued_on, summary, created_by from office.documents where id = '{doc_id}';\n"
                f"rollback;\n")
    try:
        compose("exec", "-T", "postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U",
                ENV.get("POSTGRES_USER", "moc"), "-d", ENV.get("POSTGRES_DB", "moc"), "-f", "-",
                stdin=tampered.encode())
        fail("CSDL nhận văn bản đến có cơ quan ban hành xuống dòng khi ghi thẳng")
    except subprocess.CalledProcessError as exc:
        b"documents_in_issuer" in exc.stderr or fail(f"CSDL từ chối nhưng không vì ràng buộc: {exc.stderr!r}")
    ok("ghi thẳng vào CSDL bằng quyền quản trị cũng bị ràng buộc CHECK chặn")

    reg = clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number document { status process_id } } }",
                    {"id": doc_id})["registerIncoming"]
    reg["document"]["status"] == "registered" and reg["document"]["process_id"] or fail(f"vào sổ chưa đúng: {reg}")
    ok(f"vào sổ: số đến {reg['register_number']}, quy trình đã khởi chạy")

    task = director.wait_task(doc_id, "vbden.chiDao")
    director.complete(task, "direct", {
        "instruction": "Giao Tổ Đào tạo chủ trì, Bộ môn KTPM phối hợp; báo cáo trước hạn.",
        "lead_department_id": DEPT_DT, "supports": [DEPT_KTPM],
        "due_on": (date.today() + timedelta(days=3)).isoformat(),
    })
    ok("lãnh đạo khoa chỉ đạo: Tổ Đào tạo chủ trì, hạn 3 ngày")

    task = manager.wait_task(doc_id, "vbden.phanCong")
    staff_id = staff.gql("{ core_users(where: {username: {_eq: \"chuyenviendt\"}}) { id } }")["core_users"][0]["id"]
    manager.complete(task, "assign", {"user_id": staff_id, "note": "Em rà soát và dự thảo công văn trả lời."})
    ok("tổ trưởng phân công chuyên viên")

    task = staff.wait_task(doc_id, "vbden.xuLy")
    staff.complete(task, "done", {"result_note": "Đã rà soát, gửi báo cáo cho lãnh đạo khoa."})
    ok("chuyên viên báo xong")

    final = staff.gql("""query ($id: uuid!) { office_documents_by_pk(id: $id) { status
        events(order_by: {id: asc}) { kind } assignments { role status } } }""", {"id": doc_id})["office_documents_by_pk"]
    kinds = [e["kind"] for e in final["events"]]
    expected = ["office.document.registered", "office.document.directed", "office.document.assigned",
                "office.document.processed"]
    final["status"] == "done" or fail(f"văn bản chưa xong: {final['status']}")
    kinds == expected or fail(f"dòng thời gian sai: {kinds}")
    ok("văn bản ở trạng thái done, dòng thời gian đủ 4 bước")

    print("Cách ly")
    seen = other_tenant.gql("query ($id: uuid!) { office_documents_by_pk(id: $id) { id } }", {"id": doc_id})
    seen["office_documents_by_pk"] is None or fail("đơn vị khác đọc được văn bản")
    ok("văn thư Khoa Kinh tế không thấy văn bản của Khoa CNTT")
    try:
        request("GET", f"{PUBLIC_URL}/api/files/{file['id']}", headers=other_tenant.auth)
        fail("đơn vị khác tải được tệp")
    except HTTPError as exc:
        exc.status == 404 or fail(f"tải tệp của đơn vị khác trả {exc.status}")
    ok("đơn vị khác không tải được tệp (404)")

    print("Văn bản đi")
    signer = staff.gql('{ core_users(where: {username: {_eq: "truongkhoa"}}) { id } }')["core_users"][0]["id"]
    out_id = staff.gql(
        "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id status } }",
        {"o": {
            "type_code": "CV", "reply_to_id": doc_id, "recipients": ["Phòng Đào tạo"],
            "summary": f"Về việc báo cáo kết quả rà soát chương trình đào tạo (kiểm tra {tag})",
            "body": "Phúc đáp công văn của Phòng Đào tạo, Khoa báo cáo kết quả rà soát chương trình đào tạo.\n"
                    "Đề nghị Phòng tổng hợp, báo cáo Ban Giám hiệu.",
        }},
    )["insert_office_documents_one"]["id"]
    _, _, preview = request("GET", f"{PUBLIC_URL}/api/documents/{out_id}/preview", headers=staff.auth)
    preview.startswith(b"%PDF-") or fail("xem trước dự thảo không ra tệp PDF")
    ok("chuyên viên soạn công văn trả lời, xem trước bản PDF (DỰ THẢO)")

    staff.gql("mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }",
              {"d": out_id, "s": signer})
    manager.complete(manager.wait_task(out_id, "vbdi.duyetPhong"), "approve", {"note": "Đồng ý, trình ký."})
    director.complete(director.wait_task(out_id, "vbdi.duyetDonVi"), "approve", {})
    ok("trình → tổ trưởng duyệt → lãnh đạo khoa ký duyệt")

    clerk.complete(clerk.wait_task(out_id, "vbdi.phatHanh"), "issue", {"is_public": True})
    issued = clerk.gql("""query ($id: uuid!) { office_documents_by_pk(id: $id) { status symbol verify_code
        content_sha256 files(where: {role: {_eq: "issued"}}) { file_id } } }""", {"id": out_id})["office_documents_by_pk"]
    issued["status"] == "issued" and re.fullmatch(r"\d{2,}/CNTT-ĐT", issued["symbol"] or "") and issued["files"] \
        or fail(f"phát hành chưa đúng: {issued}")
    _, _, released = request("GET", f"{PUBLIC_URL}/api/files/{issued['files'][0]['file_id']}", headers=clerk.auth)
    sha = hashlib.sha256(released).hexdigest()
    released.startswith(b"%PDF-") and issued["content_sha256"] == "\\x" + sha \
        or fail("tệp phát hành không phải PDF hoặc băm không khớp CSDL")
    ok(f"văn thư phát hành: số {issued['symbol']}, tệp PDF có mã QR, SHA-256 khớp CSDL")

    print("Cổng xác thực (không đăng nhập)")
    found, headers = call_json("GET", f"{PUBLIC_URL}/api/verify/{issued['verify_code']}")
    found["result"] == "valid" and found["document"]["symbol"] == issued["symbol"] \
        or fail(f"tra mã tra cứu không ra văn bản: {found}")
    header(headers, "X-RateLimit-Limit") == ENV.get("MOC_RATE_VERIFY_PER_MIN", "30") \
        or fail("cổng xác thực không có giới hạn tra cứu như cấu hình")
    ok("tra mã in cạnh mã QR → đúng văn bản; giới hạn tra cứu theo địa chỉ IP")
    tampered = bytearray(released)
    tampered[len(tampered) // 2] ^= 1
    same = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={sha}")[0]["result"]
    changed = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={hashlib.sha256(tampered).hexdigest()}")[0]["result"]
    (same, changed) == ("valid", "not_found") or fail(f"tra theo băm sai: nguyên vẹn {same}, đã sửa {changed}")
    ok("tệp nguyên vẹn → khớp; sửa một byte → không khớp")

    print("Tìm theo nội dung tệp PDF")
    # svc-files đọc lớp chữ ở vòng nền (MOC_TEXT_INTERVAL_S) rồi đồng bộ sang Meilisearch (MOC_SEARCH_SYNC_INTERVAL_S)
    started, hits = time.time(), []
    while not hits and time.time() - started < 120:
        hits = call_json("GET", f"{PUBLIC_URL}/api/search?q=NOIDUNG{tag}", headers=director.auth)[0]["hits"]
        hits or time.sleep(2)
    [(h["id"], h["matched_content"]) for h in hits] == [(doc_id, True)] \
        or fail(f"không tìm được công văn theo chữ trong tệp PDF: {hits}")
    ok(f"đọc lớp chữ của PDF đính kèm, tìm theo nội dung ra đúng công văn (sau {time.time() - started:.0f} giây)")
    hidden = call_json("GET", f"{PUBLIC_URL}/api/search?q=MATKIN{tag}", headers=clerk.auth)[0]["hits"]
    read = compose("exec", "-T", "postgres", "psql", "-X", "-q", "-t", "-A", "-U", ENV.get("POSTGRES_USER", "moc"),
                   "-d", ENV.get("POSTGRES_DB", "moc"), "-c",
                   f"select count(*) from core.file_texts where file_id = '{secret_pdf['id']}'").decode().strip()
    hidden == [] and read == "0" or fail(f"tệp của văn bản hạn chế bị đọc chữ hoặc tìm được: {hidden}, {read}")
    ok("văn bản hạn chế: tệp không bị đọc chữ, không tìm được theo nội dung (kể cả người tạo)")

    print("Sổ đăng ký văn bản (in theo NĐ 30, Điều 16, 22)")
    years = clerk.gql("""query ($a: uuid!, $b: uuid!) { a: office_documents_by_pk(id: $a) { register { year } }
        b: office_documents_by_pk(id: $b) { register { year } } }""", {"a": doc_id, "b": out_id})
    year_in, year_out = years["a"]["register"]["year"], years["b"]["register"]["year"]
    book_in = call_json("GET", f"{PUBLIC_URL}/api/registers/in/{year_in}", headers=clerk.auth)[0]
    book_out = call_json("GET", f"{PUBLIC_URL}/api/registers/out/{year_out}", headers=director.auth)[0]
    row_in = next((e for e in book_in["entries"] if e["document_id"] == doc_id), None)
    row_out = next((e for e in book_out["entries"] if e["document_id"] == out_id), None)
    row_in and row_in["number"] == reg["register_number"] and row_out and row_out["cells"][0] == issued["symbol"] \
        and book_in["missing"] == [] and book_out["missing"] == [] \
        or fail(f"sổ đăng ký thiếu văn bản hoặc không liền số: đến {row_in}, đi {row_out}")
    ok(f"sổ đến {year_in} có số đến {reg['register_number']}, sổ đi có {issued['symbol']}; cả hai liền số")
    _, _, printed = request("GET", f"{PUBLIC_URL}/api/registers/in/{year_in}/pdf", headers=clerk.auth)
    prints = director.gql("""query ($e: String!) { core_audit_log(where: {action: {_eq: "register.printed"},
        entity_id: {_eq: $e}}, order_by: {id: desc}, limit: 1) { actor_id overview } }""",
                          {"e": f"in/{year_in}"})["core_audit_log"]
    clerk_id = clerk.gql('{ core_users(where: {username: {_eq: "vanthu"}}) { id } }')["core_users"][0]["id"]
    printed.startswith(b"%PDF-") and prints and prints[0]["actor_id"] == clerk_id \
        and prints[0]["overview"].get("entries") == len(book_in["entries"]) \
        or fail(f"in sổ chưa ra PDF hoặc chưa ghi sổ kiểm toán: {prints}")
    ok("văn thư in sổ đến ra PDF; lần in vào sổ kiểm toán, lãnh đạo thấy ai in, bao nhiêu dòng")
    try:
        request("GET", f"{PUBLIC_URL}/api/registers/in/{year_in}", headers=staff.auth)
        fail("chuyên viên xem được sổ đăng ký")
    except HTTPError as exc:
        exc.status == 403 or fail(f"chuyên viên xem sổ đăng ký trả {exc.status}")
    ok("chuyên viên không xem được sổ đăng ký (403)")

    print("Thông báo (Centrifugo, timer Flowable)")
    fake = Realtime("khong.phai.token")
    fake.reply is None and fake.closed == 3500 or fail(f"token giả vẫn kết nối được: {fake.reply} {fake.closed}")
    fake.sock.close()
    live = Realtime(manager.token)
    channels = list(((live.reply or {}).get("connect") or {}).get("subs") or {})
    len(channels) == 1 and channels[0].startswith("personal:#") or fail(f"kết nối realtime chưa vào kênh riêng: {live.reply}")
    ok("token giả bị Centrifugo đóng (3500); token thật tự vào kênh riêng của người đó")

    waiting = staff.gql(
        "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }",
        {"o": {"type_code": "TB", "recipients": ["Các bộ môn"], "body": "Khoa thông báo lịch họp giao ban tháng 11.",
               "summary": f"Thông báo lịch họp giao ban tháng 11 (kiểm tra {tag})"}},
    )["insert_office_documents_one"]["id"]
    started = time.time()
    staff.gql("mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }",
              {"d": waiting, "s": signer})
    pushed = live.wait_push(lambda d: d["kind"] == "task.assigned" and d["document_id"] == waiting, 15)
    live.close()
    pushed and pushed["data"]["form_key"] == "vbdi.duyetPhong" or fail("tổ trưởng không nhận tin việc mới qua WebSocket")
    ok(f"chuyên viên trình → tổ trưởng nhận tin việc mới qua WebSocket sau {time.time() - started:.1f} giây")
    mine = manager.gql("query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}}) { kind } }",
                       {"d": waiting})["core_notifications"]
    theirs = staff.gql("query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}}) { kind } }",
                       {"d": waiting})["core_notifications"]
    issued_note = staff.gql("query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}}) { kind } }",
                            {"d": out_id})["core_notifications"]
    [n["kind"] for n in mine] == ["task.assigned"] and theirs == [] \
        and "document.issued" in [n["kind"] for n in issued_note] \
        or fail(f"thông báo đã lưu chưa đúng: {mine} / {theirs} / {issued_note}")
    ok("thông báo lưu lại cho người nhận (người khác không đọc được); người soạn có tin văn bản đã phát hành")

    print("Sổ kiểm toán (neo hash ra ngoài CSDL)")
    moc = [sys.executable, str(pathlib.Path(__file__).resolve().parent / "moc.py"), "audit"]
    anchored = subprocess.run([*moc, "anchor"], capture_output=True, text=True)
    anchored.returncode == 0 or fail(f"moc audit anchor lỗi: {anchored.stderr.strip() or anchored.stdout.strip()}")
    checked = subprocess.run([*moc, "verify", "--json"], capture_output=True, text=True)
    try:
        report = json.loads(checked.stdout)
    except json.JSONDecodeError:
        fail(f"moc audit verify không chạy được: {checked.stderr.strip() or checked.stdout.strip()}")
    checked.returncode == 0 and report["ok"] or fail(f"sổ kiểm toán chưa ổn: {report['problems'] or report['notes']}")
    bucket = next((v for k, v in report["anchors"].items() if k.startswith("bucket")), None)
    bucket and bucket["checked"] >= 1 and bucket["matched"] == bucket["checked"] and report["documents"] >= 1 \
        or fail(f"thiếu mốc neo hoặc văn bản có hash: {report}")
    ok(f"moc audit verify: tính lại {report['rows']} dòng sổ ngoài CSDL, khớp {bucket['matched']} mốc neo trong"
       f" bucket lạnh và hash của {report['documents']} văn bản")
    try_delete = (
        "from svc_files.config import Settings\n"
        "from svc_files.storage import s3_client\n"
        "s = Settings.from_env()\n"
        "c = s3_client(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_region)\n"
        "v = c.list_object_versions(Bucket=s.cold_bucket, Prefix='anchors/')['Versions'][0]\n"
        "try:\n"
        "    c.delete_object(Bucket=s.cold_bucket, Key=v['Key'], VersionId=v['VersionId'])\n"
        "    print('deleted')\n"
        "except Exception as exc:\n"
        "    print('refused', type(exc).__name__)\n"
    )
    refused = compose("exec", "-T", "svc-files", "python", "-c", try_delete).decode().strip()
    refused.startswith("refused") or fail(f"xóa được mốc neo trong bucket lạnh: {refused}")
    ok("mốc neo không xóa được, kể cả bằng khóa quản trị kho (S3 Object Lock)")
    rows = director.gql("""query ($e: String!) { core_audit_log(where: {entity: {_eq: "office.documents"},
        entity_id: {_eq: $e}}) { id overview } }""", {"e": out_id})["core_audit_log"]
    issued_rows = [r["overview"] for r in rows if (r["overview"].get("status") or [None, None])[1] == "issued"]
    hashed = [r["overview"] for r in rows if "content_sha256" in r["overview"]]
    issued_rows and hashed and all(o["content_sha256"] is None for o in hashed) \
        and all(o.get("summary") is None for o in (r["overview"] for r in rows)) \
        or fail(f"sổ lãnh đạo xem chưa đúng (cần thấy lần phát hành, không thấy hash, trích yếu): {rows}")
    ok("lãnh đạo khoa xem sổ của đơn vị: thấy lần phát hành, không thấy hash hay trích yếu")

    # Không dùng hết giới hạn đăng nhập ở đây: nó tính theo IP, make e2e chạy ngay sau từ cùng máy
    print("Giới hạn tốc độ")
    _, headers = call_json("POST", f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token", form={
        "grant_type": "password", "client_id": "moc-cli", "username": "vanthu",
        "password": ENV["MOC_DEMO_PASSWORD"], "scope": "openid"})
    login_limit = header(headers, "X-RateLimit-Limit")
    login_limit and login_limit == ENV.get("MOC_RATE_LOGIN_PER_MIN", login_limit) \
        or fail(f"đường đăng nhập không có giới hạn tốc độ như cấu hình ({login_limit})")
    ok(f"đăng nhập giới hạn {login_limit} lần mỗi phút theo địa chỉ IP")

    burst = Session("chuyenviendt")  # phiên mới: bộ đếm riêng, không ảnh hưởng các phiên ở trên

    def ping(session: Session) -> dict[str, str]:
        return call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": "{ __typename }"}, headers=session.auth)[1]

    for _ in range(2):  # cửa sổ đếm sang phút mới giữa chừng thì thử lại một lần
        remaining = int(header(ping(burst), "X-RateLimit-Remaining") or -1)
        remaining >= 0 or fail("GraphQL không có giới hạn tốc độ")
        for _ in range(remaining):
            ping(burst)
        try:
            ping(burst)
        except HTTPError as exc:
            exc.status == 429 or fail(f"vượt giới hạn mà GraphQL trả {exc.status}")
            break
    else:
        fail("vượt giới hạn mà GraphQL vẫn trả lời")
    ok("một phiên gọi GraphQL vượt giới hạn mỗi phút → 429")
    ping(clerk)
    ok("phiên khác vẫn gọi được, không bị chặn lây")

    # Để cuối: thời gian các phần trên đã chạy cũng tính vào thời hạn đang chờ
    print("Nhắc hạn (timer Flowable)")
    sla = sla_seconds()
    if sla is None:
        print(f"  – bỏ qua: MOC_SLA_DURATION={ENV.get('MOC_SLA_DURATION', 'PT24H')}; đặt PT20S để kiểm (CI đặt sẵn)")
    else:
        fresh = Session("totruongdt")  # phiên trước đã dùng nhiều yêu cầu trong phút này
        wait_notification(fresh, waiting, "task.overdue", started + sla + 45 - time.time()) \
            or fail(f"quá {sla:.0f} giây mà tổ trưởng chưa được nhắc")
        ok(f"để quá {sla:.0f} giây: tổ trưởng được nhắc việc duyệt dự thảo")
        wait_notification(Session("truongkhoa"), waiting, "task.escalated", started + 2 * sla + 45 - time.time()) \
            or fail(f"quá {2 * sla:.0f} giây mà lãnh đạo khoa chưa được báo")
        events = [e["kind"] for e in fresh.gql("query ($d: uuid!) { office_documents_by_pk(id: $d) { events { kind } } }",
                                               {"d": waiting})["office_documents_by_pk"]["events"]]
        {"office.task.overdue", "office.task.escalated"} <= set(events) or fail(f"dòng thời gian thiếu nhắc hạn: {events}")
        ok(f"quá {2 * sla:.0f} giây: báo lãnh đạo khoa; dòng thời gian ghi cả hai lần")

    print(f"Đạt {passed} kiểm tra.")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, RuntimeError) as exc:
        fail(str(exc))
