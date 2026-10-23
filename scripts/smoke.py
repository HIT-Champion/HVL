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

"""make smoke — đi trọn luồng văn bản đến qua cổng APISIX, như người dùng thật (cần make seed trước).

văn thư tải công văn lên (qua ClamAV) → nhập văn bản (Action receiveIncoming; dữ liệu sai bị chặn ở svc-workflow
và ở CSDL, theo cùng schemas/van-ban-den.json với form) → vào sổ, có số đến → lãnh đạo khoa chỉ đạo, giao
Tổ Đào tạo chủ trì → tổ trưởng phân công chuyên viên → chuyên viên báo xong. Rồi luồng văn bản đi: chuyên
viên soạn công văn trả lời, xem trước → trình → tổ trưởng duyệt → lãnh đạo khoa ký → văn thư phát hành PDF có
mã QR; người ngoài tra mã và băm ở cổng xác thực không cần đăng nhập. Ký số (F4.5, chỉ minh họa): bản phát hành ký
PAdES bằng khóa của đơn vị trong két OpenBao, cổng xác thực cho biết ai ký; pyHanko trong svc-files báo hợp lệ, phát
hiện lớp sửa thêm sau khi ký và một bit bị lật (két khởi tạo trước F4.5 chưa có PKI nội bộ thì bỏ qua).
Liên thông: công văn gửi Khoa Kinh tế trong hệ
thống thành văn bản đến của bên nhận, cùng bản phát hành. Đọc văn bản đến (F4.1): tác tử moc-doc-reader đọc lớp chữ
PDF văn thư vừa tải lên, gợi ý số ký hiệu, ngày ban hành, loại; tệp hạn chế không bị đọc, đơn vị khác không gọi được,
mỗi lần đọc một dòng sổ kiểm toán (không OCR ở đây — make demo-doc-van-ban thử cả ảnh). Hỏi đáp (F4.2): trợ lý
moc-assistant trả câu trích nguyên văn đúng trang của công văn hai trang; đơn vị khác, văn bản hạn chế không có nguồn;
mỗi lượt hỏi một dòng sổ không chứa câu hỏi (không mô hình — make demo-hoi-dap). Gợi ý giao việc (F4.3): văn bản mới về
học bổng được tác tử moc-assigner gợi ý Tổ Đào tạo, căn cứ có 88/CTSV; không căn cứ nào là văn bản hạn chế, văn bản hạn
chế không được gợi ý; mỗi gợi ý một dòng sổ không chứa trích yếu; lãnh đạo giao theo gợi ý thì view đo tỉ lệ giữ tăng 1
(make demo-giao-viec thử thêm khi svc-files tắt). Thông báo: tổ trưởng nhận tin việc mới qua WebSocket (Centrifugo) ngay
khi chuyên viên trình; để quá hạn thì timer Flowable nhắc rồi báo lãnh đạo (chỉ kiểm khi MOC_SLA_DURATION ngắn, CI đặt
PT20S). Dashboard điều hành: lãnh đạo khoa đọc số liệu (văn bản hạn chế chỉ có con số tổng), văn thư không đọc được. Văn
bản hạn chế: tệp nằm trong kho dạng mã hóa, mở ra có dấu tên người xem, chỉ người có tên trong danh sách được xem (người
nhận việc tự có tên), mỗi lần mở một dòng sổ. Sổ kiểm toán: neo đầu chuỗi ra bucket lạnh khóa ghi, tính lại cả chuỗi
ngoài CSDL (moc audit verify). Kèm các kiểm tra chặn: tệp EICAR, không token, đường quản trị, đơn vị khác không thấy văn
bản; văn thư đăng nhập — trên trình duyệt hay qua client moc-cli của kịch bản — phải nhập mã TOTP; giới hạn tốc độ.
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
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

from moc_env import (EICAR, ENV, INCREMENTAL_EDIT, PUBLIC_URL, REALM, USER_AGENT, HTTPError, Session, byte_range_end,
                     call_json, compose, flip_in_signed_stream, request, signature_cli, text_pages, text_pdf,
                     user_login, vault_ca_pem)

DEPT_DT = "5cc372aa-304d-4574-896c-4f3e781a2ce7"
DEPT_KTPM = "7ee31261-b14c-4c42-8e1b-9a7e99935412"
TENANT_KT = "318da474-60d6-4a90-aa7f-928b31b8fc59"     # Khoa Kinh tế (seed/tenants.sql)

passed = 0


def ok(message: str) -> None:
    global passed
    passed += 1
    print(f"  ✓ {message}")


def fail(message: str) -> None:
    print(f"  ✗ {message}")
    sys.exit(1)


def vault_status() -> dict:
    """`bao status` trong container két; két đang khóa thì lệnh thoát 2 nhưng vẫn in trạng thái."""
    try:
        raw = compose("exec", "-T", "openbao", "bao", "status", "-format=json")
    except subprocess.CalledProcessError as exc:
        raw = exc.stdout or b"{}"
    try:
        return json.loads(raw)
    except ValueError:
        return {"error": raw.decode(errors="replace")[:200]}


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
    opener.addheaders = [("User-Agent", USER_AGENT)]
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
    while True:  # hỏi ít nhất một lần, kể cả khi các phần trước đã dùng hết thời gian chờ
        found = session.gql("""query ($d: uuid!, $k: String!) {
            core_notifications(where: {document_id: {_eq: $d}, kind: {_eq: $k}}) { id } }""", {"d": doc_id, "k": kind})
        if found["core_notifications"]:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(2)


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
    # đường cấp token viết khác đi (dấu / cuối) vẫn tới Keycloak: phải bị đếm chung bộ đếm đăng nhập theo IP
    variant = urllib.request.Request(f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token/", method="POST",
                                     data=b"grant_type=password",
                                     headers={"Content-Type": "application/x-www-form-urlencoded",
                                              "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(variant, timeout=30) as resp:
            seen = dict(resp.headers)
    except urllib.error.HTTPError as exc:
        seen = dict(exc.headers)
    header(seen, "X-RateLimit-Limit") or fail("POST …/token/ không bị giới hạn số lần đăng nhập theo IP")
    ok("giới hạn đăng nhập theo IP đếm cả đường cấp token viết khác (…/token/)")

    # F3.2: két tự mở khóa (static seal); svc-files, svc-workflow không nhận bí mật qua biến môi trường mà lấy từ két
    # bằng AppRole của riêng mình
    print("Két bí mật")
    seal = vault_status()
    seal.get("initialized") and seal.get("sealed") is False and seal.get("type") == "static" \
        or fail(f"két chưa khởi tạo, đang khóa hoặc không dùng static seal: {seal}")
    secrets = {"svc-files": ("SEAWEEDFS_S3_ACCESS_KEY", "SEAWEEDFS_S3_SECRET_KEY", "HASURA_ADMIN_SECRET",
                             "MEILI_MASTER_KEY"),
               "svc-workflow": ("HASURA_ADMIN_SECRET", "MOC_ACTION_SECRET", "FLOWABLE_ADMIN_PASSWORD",
                                "CENTRIFUGO_API_KEY", "MOC_DIRECTORY_CLIENT_SECRET")}
    for service, names in secrets.items():
        # so băm giá trị chứ không so tên: bí mật không được nằm trong env dưới bất kỳ tên nào
        hashed = json.loads(compose("exec", "-T", service, "python", "-c",
                                    "import hashlib, json, os\n"
                                    "print(json.dumps({k: hashlib.sha256(v.encode()).hexdigest()"
                                    " for k, v in os.environ.items()}))"))
        wanted = {hashlib.sha256(ENV[n].encode()).hexdigest(): n for n in names}
        leaked = sorted(f"{wanted[h]} (biến {k})" for k, h in hashed.items() if h in wanted)
        not leaked or fail(f"{service} còn nhận bí mật qua biến môi trường: {', '.join(leaked)}")
    ok("két đã mở khóa (static seal); svc-files, svc-workflow không có bí mật nào trong biến môi trường")
    cross = compose("exec", "-T", "svc-workflow", "python", "-c",
                    "import os\nfrom svc_workflow.config import ConfigError\n"
                    "from svc_workflow.openbao import with_secrets\n"
                    "try:\n    with_secrets({**os.environ, 'MOC_OPENBAO_SECRET_PATH': 'moc/data/svc-files'},\n"
                    "                 attempts=1)\n"
                    "    print('read')\nexcept ConfigError as exc:\n    print('refused', exc)\n").decode().strip()
    cross.startswith("refused") and "403" in cross or fail(f"svc-workflow đọc được bí mật của svc-files: {cross}")
    ok("mỗi dịch vụ chỉ đọc được bí mật của mình: AppRole svc-workflow đọc phần svc-files bị két từ chối (403)")

    # F3.3: một lượt reconciler trên hệ thống vừa dựng — mọi dịch vụ khai trong compose đều có container chạy, không
    # có gì phải sửa (màn phá rồi tự dựng lại: make demo-tu-phuc-hoi)
    print("Tự phục hồi")
    # --heal-only: smoke không kéo commit mới về (không tự cài lại Signet); timer đang chạy một lượt thì đợi nó xong
    rec = subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name("reconcile.py")), "--json",
                          "--heal-only", "--wait", "300"], capture_output=True, text=True)
    try:
        report = json.loads(rec.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        fail(f"reconciler không trả kết quả: {rec.stdout}{rec.stderr}")
    rec.returncode == 0 and not report["skipped"] and not report["actions"] and not report["problems"] \
        or fail(f"reconciler thấy hệ thống lệch khai báo: {report}")
    ok("reconciler: mọi dịch vụ khai trong compose đang chạy đúng, không có gì phải sửa")

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
    try:
        call_json("POST", f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token", form={
            "grant_type": "password", "client_id": "moc-cli", "username": "vanthu",
            "password": ENV["MOC_DEMO_PASSWORD"], "scope": "openid"})
        fail("văn thư lấy được token qua client moc-cli chỉ bằng mật khẩu, không cần mã TOTP")
    except HTTPError as exc:
        exc.status in (400, 401) or fail(f"lấy token không kèm mã: HTTP {exc.status}")
    ok("lấy token bằng mật khẩu (client moc-cli của kịch bản) cũng phải kèm mã TOTP — không là đường vòng")
    # client có sẵn admin-cli của realm cũng cho luồng mật khẩu: theo directGrantFlow của realm. Tài khoản khác
    # vanthu: hai lần sai liền nhau dưới 1 giây Keycloak coi là dò mật khẩu và khóa tạm
    try:
        call_json("POST", f"{PUBLIC_URL}/realms/{REALM}/protocol/openid-connect/token", form={
            "grant_type": "password", "client_id": "admin-cli", "username": "totruongdt",
            "password": ENV["MOC_DEMO_PASSWORD"], "scope": "openid"})
        fail("lãnh đạo phòng lấy được token qua client admin-cli của realm chỉ bằng mật khẩu")
    except HTTPError as exc:
        exc.status in (400, 401) or fail(f"admin-cli không kèm mã: HTTP {exc.status}")
    ok("client admin-cli có sẵn của realm cũng phải kèm mã TOTP (luồng mật khẩu mặc định của realm)")
    # khóa quản trị Hasura gửi kèm token người dùng: cổng gỡ cả tên cũ, văn thư vẫn chỉ là văn thư
    for name in ("X-Hasura-Admin-Secret", "X-Hasura-Access-Key"):
        data, _ = call_json("POST", f"{PUBLIC_URL}/v1/graphql", {"query": "{ core_audit_log(limit: 1) { diff } }"},
                            headers={**clerk.auth, name: ENV["HASURA_ADMIN_SECRET"]})
        (data or {}).get("errors") or fail(f"{name} đi qua cổng: văn thư đọc được cột diff của sổ kiểm toán")
    ok("khóa quản trị Hasura từ ngoài vào (X-Hasura-Admin-Secret, tên cũ X-Hasura-Access-Key) bị gỡ ở cổng")

    print("Trạm kiểm dịch")
    before = director.gql("{ core_audit_log_aggregate { aggregate { max { id } } } }")
    before = before["core_audit_log_aggregate"]["aggregate"]["max"]["id"] or 0
    try:
        clerk.upload(f"eicar-{tag}.pdf", EICAR)
        fail("tệp EICAR không bị chặn")
    except HTTPError as exc:
        exc.status == 422 or fail(f"tệp EICAR trả {exc.status}")
    ok("tệp EICAR bị ClamAV chặn (422), không lưu")
    # F3.1: lần chặn vào sổ kiểm toán; lãnh đạo thấy mẫu mã độc, không thấy tên tệp
    blocked = director.gql(
        """query ($h: String!, $after: bigint!) { core_audit_log(where: {action: {_eq: "file.rejected"},
             entity_id: {_eq: $h}, id: {_gt: $after}}) { overview } }""",
        {"h": hashlib.sha256(EICAR).hexdigest(), "after": before})["core_audit_log"]
    [row["overview"] for row in blocked] == [{"filename": None, "size_bytes": len(EICAR), "sha256": None,
                                              "signature": "Eicar-Test-Signature"}] \
        or fail(f"sổ kiểm toán không có đúng một dòng file.rejected của lần chặn này: {blocked}")
    ok("lần chặn nằm trong sổ kiểm toán: lãnh đạo thấy mẫu mã độc, cỡ tệp; tên tệp ẩn")

    print("Luồng văn bản đến")
    # Văn bản hạn chế tiếp nhận TRƯỚC: svc-files đọc chữ PDF theo thứ tự tải lên, nên khi công văn dưới đã tìm được
    # theo nội dung mà tệp này vẫn chưa được đọc thì đúng là tệp của văn bản hạn chế bị bỏ qua (F2.7)
    secret_pdf = clerk.upload(f"han-che-{tag}.pdf", text_pdf(f"Danh sach nang luong truoc han MATKIN{tag}"),
                              restricted=True)
    file = clerk.upload(f"cong-van-{tag}.pdf", text_pdf("De nghi Khoa ra soat chuong trinh dao tao nam hoc 2026-2027",
                                                        f"Ma kiem tra noi dung NOIDUNG{tag}"))
    ok(f"văn thư tải công văn lên, quét sạch ({file['sha256'][:12]}…)")
    incoming = {
        "type_code": "CV", "symbol": f"123/ĐHCN-ĐT{tag}", "issuer_name": "Trường Đại học Công nghiệp",
        "issued_on": datetime.now(timezone(timedelta(hours=7))).date().isoformat(), "urgency": "khan",   # giờ Việt Nam
        "summary": f"Về việc rà soát chương trình đào tạo năm học 2026–2027 (kiểm tra {tag})", "file_ids": [file["id"]],
    }
    receive = "mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id document { status files { role } } } }"
    secret_id = clerk.gql(receive, {"d": {
        **incoming, "symbol": f"124/ĐHCN-TC{tag}", "restricted": True, "urgency": "normal",
        "summary": f"Về việc nâng lương trước hạn (kiểm tra {tag})", "file_ids": [secret_pdf["id"]],
    }})["receiveIncoming"]["document_id"]
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
    # F3.12: mỗi đơn vị mẫu đúng một Organization trong Keycloak mang tenant_id của nó; tài khoản của đơn vị là thành
    # viên Organization đó và không thuộc Organization nào khác; danh bạ core.users khớp Keycloak (moc tenant check)
    seeded = ("CNTT", "KT")
    checked = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent / "moc.py"), "tenant",
                              "check", *seeded, "--json"], capture_output=True, text=True)
    try:
        orgs = json.loads(checked.stdout)
    except json.JSONDecodeError:
        fail(f"moc tenant check không chạy được: {checked.stderr.strip() or checked.stdout.strip()}")
    checked.returncode == 0 and orgs["ok"] \
        or fail(f"đơn vị và Keycloak Organizations lệch nhau (make seed đã chạy lại chưa?): "
                f"{orgs.get('problems') or orgs.get('error')}")
    units = {t["code"]: t for t in orgs["tenants"]}
    all(units[c]["organization"] and units[c]["members"] == units[c]["accounts"] >= 1 for c in seeded) \
        or fail(f"Organization của đơn vị mẫu chưa đủ thành viên: {orgs['tenants']}")
    ok("mỗi đơn vị một Organization Keycloak mang đúng tenant_id ("
       + ", ".join(f"{units[c]['organization']}: {units[c]['members']} thành viên" for c in seeded)
       + "); không tài khoản nào lạc sang Organization của đơn vị khác")

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

    # F4.5: bản phát hành ký PAdES bằng khóa của đơn vị trong Transit, chứng thư do CA nội bộ trong két cấp — chỉ minh
    # họa. Két khởi tạo trước F4.5 (chưa có PKI nội bộ) hay MOC_SIGN_ENABLED=false thì phát hành không ký: bỏ qua
    print("Ký số văn bản đi (F4.5, chỉ minh họa)")
    signature = found["document"].get("signature")
    # cùng bộ giá trị tắt với config.py của svc-files (_flag)
    if signature is None and ENV.get("MOC_SIGN_ENABLED", "true").strip().lower() in ("0", "false", "no", "off"):
        print(f"  – bỏ qua: MOC_SIGN_ENABLED={ENV['MOC_SIGN_ENABLED']}, phát hành không ký")
    elif signature is None and vault_ca_pem() is None:
        print("  – bỏ qua: két khởi tạo trước F4.5 chưa có CA nội bộ, ký số tự tắt (docs/van-hanh.md mục Két bí mật)")
    else:
        signature or fail("két có CA nội bộ mà bản phát hành không có chữ ký số — xem nhật ký svc-files"
                          " (office.document.sign_failed, office.signing.disabled)")
        (signature.get("level"), signature.get("illustrative")) == ("PAdES-B-B", True) and signature.get("signed_at") \
            and (signature.get("signer") or "").startswith("Khoa Công nghệ thông tin") \
            and "chỉ minh họa" in (signature.get("ca") or "") \
            and b"/ETSI.CAdES.detached" in released and byte_range_end(released) == len(released) \
            or fail(f"bản phát hành chưa có chữ ký PAdES phủ cả tệp, hoặc khối chữ ký ở cổng xác thực sai: {signature}")
        ok(f"cổng xác thực: chữ ký {signature['level']} của {signature['signer']}, CA \"{signature['ca']}\""
           " (illustrative); chữ ký phủ tới byte cuối bản phát hành")
        code, lines = signature_cli(released)
        code == 0 and lines and lines[0].startswith("Chữ ký hợp lệ") \
            or fail(f"pyHanko trong svc-files không xác nhận chữ ký bản phát hành (thoát {code}): {lines[:3]}")
        ok("python -m svc_files.signing verify (pyHanko, chỉ tin CA của két): hợp lệ, thoát 0")
        edited = compose("exec", "-T", "svc-files", "python", "-c", INCREMENTAL_EDIT, stdin=released)
        code, lines = signature_cli(edited)
        signed = edited[:byte_range_end(edited) or 0]
        whole = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={hashlib.sha256(edited).hexdigest()}")[0]["result"]
        part = call_json("GET", f"{PUBLIC_URL}/api/verify?sha256={hashlib.sha256(signed).hexdigest()}")[0]["result"]
        code == 1 and lines and lines[0].startswith("Văn bản đã bị sửa sau khi ký") \
            and (whole, part) == ("not_found", "valid") \
            or fail(f"thêm lớp sửa sau khi ký: CLI thoát {code} {lines[:1]}, tra cả tệp {whole}, phần đã ký {part}")
        ok("thêm một chú thích ghi nối sau chữ ký: CLI báo đã bị sửa sau khi ký (thoát 1); tra băm cả tệp → không khớp,"
           " băm phần đã ký → đúng bản phát hành")
        code, lines = signature_cli(flip_in_signed_stream(released))
        code == 1 and lines and lines[0].startswith("Chữ ký không khớp nội dung") \
            or fail(f"lật một bit trong phần đã ký: CLI thoát {code} {lines[:1]}")
        ok("lật một bit trong phần đã ký: CLI báo chữ ký không khớp nội dung (thoát 1)")
        tenant = clerk.gql("{ core_tenants { id } }")["core_tenants"][0]["id"]
        stored = compose("exec", "-T", "postgres", "psql", "-X", "-q", "-t", "-A", "-U",
                         ENV.get("POSTGRES_USER", "moc"), "-d", ENV.get("POSTGRES_DB", "moc"), "-c",
                         f"select key_name, serial, (select count(*) from core.file_signatures x join"
                         f" office.document_files df on df.file_id = x.file_id join office.documents d on d.id ="
                         f" df.document_id where d.restricted) from core.file_signatures"
                         f" where file_id = '{issued['files'][0]['file_id']}'").decode().strip()
        stored == f"moc-ky-so-{tenant}|{signature['serial']}|0" \
            or fail(f"CSDL: dòng core.file_signatures của bản phát hành chưa đúng (khóa|sê-ri|chữ ký văn bản hạn chế):"
                    f" {stored}")
        # văn bản hạn chế: lượt smoke đầu chưa phát hành văn bản đi hạn chế nào (màn demo-ky-so bước 7 kiểm thật); các
        # lượt sau trên cùng kho (sau khôi phục, từ bản cài) thì có, nên phép đếm toàn kho mới có nghĩa
        ok("CSDL: chữ ký của bản phát hành ghi khóa moc-ky-so-<đơn vị> (Transit), cùng số sê-ri với cổng xác thực;"
           " trong kho không chữ ký nào gắn với văn bản hạn chế")

    # F3.12: công văn gửi Khoa Kinh tế trong hệ thống — phát hành xong thì văn thư bên nhận tự có văn bản đến kèm đúng
    # bản phát hành. svc-workflow chép ngay sau lần phát hành; trượt thì vòng đối soát nền làm lại
    print("Liên thông trong hệ thống")
    sent = staff.gql(
        "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }",
        {"o": {"type_code": "CV", "recipients": ["Khoa Kinh tế"], "recipient_tenant_ids": [TENANT_KT],
               "summary": f"Về việc phối hợp tổ chức hội thảo khoa học liên khoa (kiểm tra {tag})",
               "body": "Khoa Công nghệ thông tin đề nghị Khoa Kinh tế cử cán bộ tham gia ban tổ chức hội thảo."}},
    )["insert_office_documents_one"]["id"]
    staff.gql("mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }",
              {"d": sent, "s": signer})
    manager.complete(manager.wait_task(sent, "vbdi.duyetPhong"), "approve", {})
    director.complete(director.wait_task(sent, "vbdi.duyetDonVi"), "approve", {})
    clerk.complete(clerk.wait_task(sent, "vbdi.phatHanh"), "issue", {"is_public": False})
    source = clerk.gql("query ($id: uuid!) { office_documents_by_pk(id: $id) { status symbol content_sha256 } }",
                       {"id": sent})["office_documents_by_pk"]
    source["status"] == "issued" or fail(f"công văn gửi Khoa Kinh tế chưa phát hành: {source}")
    sender = clerk.gql("{ core_tenants { name } }")["core_tenants"][0]["name"]
    arrived_q = """query ($s: uuid!) { office_documents(where: {source_id: {_eq: $s}}) { id direction status symbol
        issuer_name files { role file_id file { sha256 } } } }"""
    started, arrived = time.time(), []
    while not arrived and time.time() - started < 90:
        arrived = other_tenant.gql(arrived_q, {"s": sent})["office_documents"]
        arrived or time.sleep(2)
    len(arrived) == 1 or fail(f"sau {time.time() - started:.0f} giây văn thư Khoa Kinh tế chưa có đúng một văn bản đến"
                              f" từ công văn vừa phát hành: {arrived}")
    got = arrived[0]
    (got["direction"], got["status"], got["symbol"], got["issuer_name"]) == ("in", "received", source["symbol"], sender) \
        and [(f["role"], (f["file"] or {}).get("sha256")) for f in got["files"]] == [("main", source["content_sha256"])] \
        or fail(f"văn bản đến liên thông chưa đúng (cần received, cùng số ký hiệu, tệp chính cùng băm): {got}")
    seen = clerk.gql("query ($id: uuid!) { office_documents_by_pk(id: $id) { id } }", {"id": got["id"]})
    seen["office_documents_by_pk"] is None or fail("Khoa CNTT đọc được văn bản đến của Khoa Kinh tế")
    try:
        request("GET", f"{PUBLIC_URL}/api/files/{got['files'][0]['file_id']}", headers=clerk.auth)
        fail("Khoa CNTT tải được bản sao nằm trong kho của Khoa Kinh tế")
    except HTTPError as exc:
        exc.status == 404 or fail(f"tải bản sao của đơn vị khác trả {exc.status}")
    ok(f"công văn {source['symbol']} gửi Khoa Kinh tế: {time.time() - started:.0f} giây sau phát hành văn thư bên nhận có"
       " văn bản đến (chờ vào sổ), tệp chính cùng SHA-256 bản phát hành; Khoa CNTT không đọc được văn bản, tệp bên nhận")

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

    # F4.2: trợ lý moc-assistant trả lời bằng câu trích nguyên văn kèm số ký hiệu và trang, chỉ trong văn bản người hỏi
    # được xem. Vòng nền svc-files đọc chữ từng trang rồi đưa đoạn vào chỉ mục chunks (MOC_ASK_SYNC_INTERVAL_S); CI
    # không bật mô hình nên đây là đường extract
    print("Hỏi đáp trên kho văn bản (F4.2)")

    def ask(session: Session, question: str) -> dict:
        _, _, raw = request("POST", f"{PUBLIC_URL}/api/documents/ask", data=json.dumps({"question": question}).encode(),
                            headers={**session.auth, "Content-Type": "application/json"}, timeout=60)
        return json.loads(raw)

    def sql(query: str) -> str:
        return compose("exec", "-T", "postgres", "psql", "-X", "-q", "-t", "-A", "-U", ENV.get("POSTGRES_USER", "moc"),
                       "-d", ENV.get("POSTGRES_DB", "moc"), "-c", query).decode().strip()

    audit_before = int(sql("select coalesce(max(id), 0) from core.audit_log") or 0)
    # Mỗi trang ≥ 40 ký tự không trắng, không thì bộ chia đoạn bỏ trang (assist/chunks.py MIN_CHARS); chỉ trang 2 có
    # dấu TRANG2 và hạn nộp (trang 1 không có từ nào gần giống, kể cả khi Meilisearch chịu gõ sai)
    paged = clerk.upload(f"hai-trang-{tag}.pdf", text_pages(
        ["De nghi cac don vi to chuc tu danh gia chuong trinh dao tao nam hoc 2026-2027.",
         "Noi dung cu the xem phu luc kem theo."],
        ["Cac don vi gui bao cao tong hop ve Phong Dao tao theo mau kem theo.", f"TRANG2{tag} han nop 12/12/2026"]))
    paged_id = clerk.gql(receive, {"d": {
        **incoming, "symbol": f"126/ĐHCN-ĐT{tag}", "urgency": "normal", "file_ids": [paged["id"]],
        "summary": f"Về việc tổ chức tự đánh giá chương trình đào tạo (kiểm tra {tag})",
    }})["receiveIncoming"]["document_id"]
    clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": paged_id})
    question = f"TRANG2{tag} hạn nộp là ngày nào?"
    started, got = time.time(), {}
    while time.time() - started < 120:
        got = ask(director, question)
        if any(s["document_id"] == paged_id for s in got["sources"]):
            break
        time.sleep(3)
    first = (got.get("sources") or [{}])[0]
    (got.get("status"), first.get("document_id"), first.get("kind"), first.get("page")) \
        == ("answered", paged_id, "page", 2) and "12/12/2026" in ((got.get("answer") or {}).get("text") or "") \
        or fail(f"sau {time.time() - started:.0f} giây trợ lý chưa trả câu trích ở trang 2 công văn hai trang: {got}")
    ok(f"lãnh đạo hỏi “{question}” → câu trích có 12/12/2026, nguồn [1] {first.get('symbol')} · tr. 2 (sau"
       f" {time.time() - started:.0f} giây, svc-files trả lời trong {got.get('duration_ms')} ms)")
    # Câu chỉ có từ của riêng văn bản này: đơn vị khác không thấy gì, kể cả văn bản của mình có chữ "hạn", "ngày"
    other = ask(other_tenant, f"TRANG2{tag} là gì?")
    other["status"] == "no_evidence" and not any(s.get("document_id") == paged_id for s in other["sources"]) \
        or fail(f"văn thư Khoa Kinh tế hỏi ra văn bản của Khoa CNTT: {other}")
    sealed_ask = ask(clerk, f"MATKIN{tag} là gì?")
    sealed_ask["status"] == "no_evidence" and sealed_ask["sources"] == [] \
        or fail(f"hỏi nội dung văn bản hạn chế bằng chính người tạo vẫn có nguồn: {sealed_ask}")
    ok("văn thư Khoa Kinh tế hỏi → no_evidence; nội dung văn bản hạn chế, hỏi bằng chính người tạo → no_evidence")
    rows = [r.split("|", 3) for r in sql(
        "select actor_kind, actor_id, entity, diff::text from core.audit_log where action = 'assistant.answered'"
        f" and id > {audit_before} order by id").splitlines()]
    len(rows) >= 3 and all(r[:3] == ["agent", "moc-assistant", "ai.questions"] for r in rows) \
        or fail(f"sổ kiểm toán chưa có dòng assistant.answered của tác tử moc-assistant cho mỗi lượt hỏi: {rows}")
    leaked = [r[3] for r in rows if f"TRANG2{tag}".casefold() in r[3].casefold() or f"MATKIN{tag}".casefold()
              in r[3].casefold() or "12/12/2026" in r[3]]
    leaked == [] or fail(f"diff của dòng sổ hỏi đáp có chữ của câu hỏi hoặc câu trả lời: {leaked}")
    ok(f"{len(rows)} dòng sổ assistant.answered do moc-assistant (agent) ghi; diff không có câu hỏi, câu trả lời")

    # F4.3: văn bản vừa vào sổ thì tác tử moc-assigner (nhánh BPMN song song với bước chỉ đạo) tìm các văn bản tương tự
    # đã giao, gợi ý đơn vị chủ trì + hạn kèm căn cứ; make seed đã giao 88/CTSV (học bổng) cho Tổ Đào tạo. Trích yếu
    # thử không có "học kỳ II": Meilisearch (matchingStrategy frequency) luôn giữ từ hiếm nhất của câu tìm, mà "II" chỉ
    # có ở vài văn bản seed khác — 88/CTSV là "học kỳ I"
    print("Gợi ý giao việc (F4.3)")
    suggestion_query = """query ($id: uuid!) { office_assignment_suggestions_by_pk(document_id: $id) {
      status reason department_id confidence due_on evidence created_at } }"""

    def kept() -> tuple[int, int]:
        rows = director.gql("{ office_v_assignment_suggestion_accuracy { decided kept_unit } }")[
            "office_v_assignment_suggestion_accuracy"]
        return sum(r["decided"] for r in rows), sum(r["kept_unit"] for r in rows)

    scholarship = director.gql('{ office_documents(where: {direction: {_eq: "in"}, symbol: {_eq: "88/CTSV"}}) { id } }'
                               )["office_documents"]
    scholarship or fail("không có văn bản 88/CTSV của make seed")
    scholarship_id = scholarship[0]["id"]
    started = time.time()
    while not any(s.get("document_id") == scholarship_id
                  for s in ask(director, "xét cấp học bổng khuyến khích học tập").get("sources") or []):
        time.time() - started < 90 or fail("sau 90 giây chỉ mục đoạn chưa có 88/CTSV — vòng nền svc-files có chạy"
                                           " không?")
        time.sleep(3)
    bare = {**incoming, "urgency": "normal", "file_ids": [], "issuer_name": "Phòng Công tác sinh viên"}
    sealed_id = clerk.gql(receive, {"d": {
        **bare, "symbol": f"130/CTSV-GV{tag}", "restricted": True,
        "summary": f"Về việc xét cấp học bổng khuyến khích học tập cho sinh viên khó khăn (kiểm tra {tag})",
    }})["receiveIncoming"]["document_id"]
    clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": sealed_id})
    case_summary = f"Về việc xét cấp học bổng khuyến khích học tập năm học 2026–2027 (kiểm tra {tag})"
    case_id = clerk.gql(receive, {"d": {**bare, "symbol": f"131/CTSV-GV{tag}", "summary": case_summary}})[
        "receiveIncoming"]["document_id"]
    clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": case_id})
    started, hint = time.time(), None
    while hint is None and time.time() - started < 20:
        hint = director.gql(suggestion_query, {"id": case_id})["office_assignment_suggestions_by_pk"]
        hint or time.sleep(1)
    found_at = time.time()
    evidence = (hint or {}).get("evidence") or []
    evidence_ids = [str(e.get("document_id")) for e in evidence]
    # 88/CTSV là văn bản học bổng duy nhất make seed đã giao. Kho đã chạy make demo-giao-viec (hay bản cài khôi phục từ
    # sao lưu của kho đó), hay đã chạy smoke nhiều lần (văn bản kiểm tra của lần trước cũng đã giao Tổ Đào tạo), có thêm
    # văn bản học bổng giao Tổ Đào tạo giống bằng hoặc hơn: 5 chỗ căn cứ có thể đầy bằng chúng mà không có 88/CTSV — khi
    # đó cả 5 phải là văn bản đến học bổng không hạn chế, cùng thuê ước, có giao Tổ Đào tạo chủ trì (đối chiếu bảng giao
    # việc, không tin dòng gợi ý). Chỉ uuid đã kiểm mới vào câu SQL
    ids = [i for i in evidence_ids if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", i)]
    crowded = len(ids) == 5 and all(e.get("department_id") == DEPT_DT for e in evidence) and sql(
        "select count(*) from office.documents d where d.direction = 'in' and not d.restricted"
        f" and d.summary ilike '%học bổng%' and d.id = any('{{{','.join(ids)}}}'::uuid[])"
        f" and d.tenant_id = (select tenant_id from office.documents where id = '{case_id}')"
        " and exists (select 1 from office.assignments a left join core.users u on u.id = a.user_id"
        " where a.tenant_id = d.tenant_id and a.document_id = d.id and a.role = 'lead' and a.parent_id is null"
        f" and a.status <> 'cancelled' and coalesce(a.department_id, u.department_id) = '{DEPT_DT}')") == "5"
    hint and hint["status"] == "suggested" and hint["department_id"] == DEPT_DT \
        and (scholarship_id in evidence_ids or crowded) \
        or fail(f"sau {found_at - started:.0f} giây chưa có gợi ý Tổ Đào tạo với căn cứ 88/CTSV (hoặc 5 căn cứ học bổng"
                f" giao Tổ Đào tạo): {hint}")
    basis = "căn cứ có 88/CTSV" if scholarship_id in evidence_ids else \
        "5 căn cứ đều là văn bản học bổng giao Tổ Đào tạo (kho đã có văn bản học bổng khác giao Tổ Đào tạo," \
        " 88/CTSV ngoài top 5)"
    ok(f"văn bản mới về học bổng → sau {found_at - started:.0f} giây tác tử gợi ý Tổ Đào tạo (độ tin cậy"
       f" {hint['confidence']}), {basis}")
    sealed_evidence = sql(
        "select count(*) from office.assignment_suggestions s cross join lateral jsonb_array_elements(s.evidence) e"
        " join office.documents d on d.tenant_id = s.tenant_id and d.id = (e->>'document_id')::uuid where d.restricted")
    sealed_evidence == "0" or fail(f"{sealed_evidence} căn cứ gợi ý là văn bản hạn chế")
    ok("không gợi ý nào lấy văn bản hạn chế làm căn cứ (psql, mọi dòng office.assignment_suggestions)")
    rows = [r.split("|", 2) for r in sql(
        "select actor_kind, actor_id, diff::text from core.audit_log where action = 'assignment.suggested'"
        f" and entity_id = '{case_id}'").splitlines()]
    allowed = {"outcome", "outcome_reason", "department_id", "due_days", "confidence", "evidence", "candidates",
               "semantic", "duration_ms"}
    len(rows) == 1 and rows[0][:2] == ["agent", "moc-assigner"] and set(json.loads(rows[0][2])) <= allowed \
        and not any(w in rows[0][2].casefold() for w in ("học bổng", "khuyến khích", f"kiểm tra {tag}".casefold())) \
        or fail(f"dòng sổ assignment.suggested chưa đúng (một dòng của moc-assigner, không chữ văn bản): {rows}")
    ok("một dòng sổ assignment.suggested do moc-assigner (agent) ghi; diff chỉ có đơn vị, độ tin cậy, số đếm")
    before = kept()
    director.complete(director.wait_task(case_id, "vbden.chiDao"), "direct", {
        "instruction": "Giao Tổ Đào tạo chủ trì thực hiện, báo cáo đúng hạn.",
        "lead_department_id": hint["department_id"], "supports": [],
        "due_on": hint["due_on"] or (date.today() + timedelta(days=7)).isoformat()})
    after = kept()
    after == (before[0] + 1, before[1] + 1) or fail(f"view đo gợi ý chưa đếm lần giữ: trước {before}, sau {after}")
    ok("lãnh đạo khoa giao theo gợi ý → office_v_assignment_suggestion_accuracy: decided +1, kept_unit +1")
    time.sleep(max(0.0, 3 - (time.time() - found_at)))
    sql(f"select (select count(*) from office.assignment_suggestions where document_id = '{sealed_id}'),"
        f" (select count(*) from core.audit_log where action = 'assignment.suggested' and entity_id = '{sealed_id}')"
        ) == "0|0" or fail("văn bản hạn chế có dòng gợi ý hoặc dòng sổ assignment.suggested")
    ok("văn bản hạn chế (cùng chủ đề học bổng) không có dòng gợi ý, không có dòng sổ của tác tử")

    # F4.1: tác tử moc-doc-reader đọc tệp văn thư vừa tải lên, trả gợi ý cho form tiếp nhận — không ghi vào văn bản
    print("Đọc văn bản đến (F4.1)")

    def read_status(session: Session, file_id: str) -> tuple[int, str | None]:
        try:
            request("POST", f"{PUBLIC_URL}/api/files/{file_id}/read", data=b"", headers=session.auth, timeout=90)
        except HTTPError as exc:
            try:
                return exc.status, (json.loads(exc.body).get("detail") or {}).get("code")
            except (ValueError, AttributeError):
                return exc.status, None
        return 200, None

    notice = clerk.upload(f"thong-bao-{tag}.pdf", text_pdf(
        "CONG HOA XA HOI CHU NGHIA VIET NAM", f"So: 99/TB-SMK{tag}", "Ha Noi, ngay 15 thang 10 nam 2026", "THONG BAO",
        f"Lich hop giao ban thang 11 {tag}"))
    _, _, raw = request("POST", f"{PUBLIC_URL}/api/files/{notice['id']}/read", data=b"", headers=clerk.auth,
                        timeout=90)
    suggested = json.loads(raw)
    values = {k: v["value"] for k, v in (suggested.get("fields") or {}).items()}
    (suggested.get("method"), values.get("symbol"), values.get("issued_on"), values.get("type_code")) \
        == ("text", f"99/TB-SMK{tag}", "2026-10-15", "TB") or fail(f"tác tử đọc thông báo chưa đúng: {suggested}")
    ok("tác tử đọc lớp chữ PDF vừa tải lên, gợi ý đúng số ký hiệu, ngày ban hành, loại (POST /api/files/{id}/read)")
    sealed = clerk.upload(f"han-che-doc-{tag}.pdf", text_pdf(f"So: 98/TB-SMK{tag}"), restricted=True)
    read_status(clerk, sealed["id"]) == (409, "restricted") \
        or fail(f"tệp của văn bản hạn chế không bị chặn đọc: {read_status(clerk, sealed['id'])}")
    read_status(other_tenant, notice["id"]) == (404, "not_found") \
        or fail(f"văn thư đơn vị khác gọi đọc tệp: {read_status(other_tenant, notice['id'])}")
    ok("tệp hạn chế không bị đọc (409 restricted); văn thư Khoa Kinh tế gọi đọc tệp của Khoa CNTT → 404")
    rows = director.gql("""query ($f: String!) { core_audit_log(where: {action: {_eq: "intake.suggested"},
        entity_id: {_eq: $f}}) { actor_id actor_kind overview } }""", {"f": notice["id"]})["core_audit_log"]
    [(r["actor_id"], r["actor_kind"]) for r in rows] == [("moc-doc-reader", "agent")] \
        and f"SMK{tag}" not in json.dumps(rows) \
        or fail(f"sổ kiểm toán chưa có đúng một dòng intake.suggested của tác tử: {rows}")
    ok("sổ kiểm toán: một dòng intake.suggested, người thực hiện moc-doc-reader (agent), không có chữ của văn bản")

    print("Văn bản hạn chế: tệp mã hóa, danh sách người được xem (F3.7)")
    secret_pdf.get("encrypted") is True or fail(f"tệp tải lên ở chế độ hạn chế không được mã hóa: {secret_pdf}")
    key = compose("exec", "-T", "postgres", "psql", "-X", "-q", "-t", "-A", "-U", ENV.get("POSTGRES_USER", "moc"),
                  "-d", ENV.get("POSTGRES_DB", "moc"), "-c",
                  f"select object_key from core.files where id = '{secret_pdf['id']}'").decode().strip()
    peek = (
        "import os, sys\n"
        "from svc_files.config import Settings\n"
        "from svc_files.openbao import with_secrets\n"
        "from svc_files.storage import s3_client\n"
        "s = Settings.from_env(with_secrets(os.environ))\n"
        "c = s3_client(s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_region)\n"
        "b = c.get_object(Bucket=s.bucket, Key=sys.argv[1])['Body'].read()\n"
        "print(b[:4].decode('latin-1'), b'%PDF' in b, sys.argv[2].encode() in b)\n"
    )
    stored = compose("exec", "-T", "svc-files", "python", "-c", peek, key, f"MATKIN{tag}").decode().split()
    stored == ["MOC1", "False", "False"] or fail(f"tệp của văn bản hạn chế nằm trong kho chưa mã hóa: {stored}")
    ok("trong kho tệp chỉ có bản mã (MOC1, AES-256-GCM, khóa riêng từng tệp bọc bằng OpenBao): không đầu PDF, "
       "không chữ")
    _, got, opened = request("GET", f"{PUBLIC_URL}/api/files/{secret_pdf['id']}", headers=clerk.auth)
    opened.startswith(b"%PDF") and hashlib.sha256(opened).hexdigest() != secret_pdf["sha256"] \
        and "no-store" in (header(got, "Cache-Control") or "") and header(got, "ETag") is None \
        or fail(f"văn thư mở tệp hạn chế chưa đúng: {header(got, 'Cache-Control')} {header(got, 'ETag')}")
    ok("văn thư mở tệp: giải mã trong bộ nhớ, đóng dấu tên người xem (khác bản gốc), cấm lưu đệm")
    # vào sổ → quy trình giao lãnh đạo khoa cho ý kiến chỉ đạo; svc-workflow thêm người nhận việc vào danh sách được xem
    clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": secret_id})
    users = clerk.gql('{ core_users(where: {username: {_in: ["vanthu", "truongkhoa"]}}) { id username } }')["core_users"]
    uid = {u["username"]: u["id"] for u in users}
    viewers_q = "query ($d: uuid!) { office_document_acl(where: {document_id: {_eq: $d}}) { user_id granted_by } }"
    viewers = clerk.gql(viewers_q, {"d": secret_id})["office_document_acl"]
    (uid["truongkhoa"], uid["vanthu"]) in [(v["user_id"], v["granted_by"]) for v in viewers] \
        or fail(f"lãnh đạo nhận việc chỉ đạo mà chưa có tên trong danh sách được xem: {viewers}")

    def opens(who: Session) -> bool:
        try:
            request("GET", f"{PUBLIC_URL}/api/files/{secret_pdf['id']}", headers=who.auth)
            return True
        except HTTPError as exc:
            exc.status == 404 or fail(f"tải tệp hạn chế trả {exc.status}")
            return False

    opens(director) or fail("lãnh đạo có tên trong danh sách mà không mở được tệp")
    ok("lãnh đạo nhận việc chỉ đạo tự có tên trong danh sách được xem, mở được tệp")
    started, notes = time.time(), []
    while not notes and time.time() - started < 15:
        notes = director.gql("query ($d: uuid!) { core_notifications(where: {document_id: {_eq: $d}}) { data } }",
                             {"d": secret_id})["core_notifications"]
        notes or time.sleep(1)
    notes and all(n["data"].get("restricted") is True and not {"summary", "symbol", "issuer_name"} & set(n["data"])
                  for n in notes) or fail(f"thông báo về văn bản hạn chế mang nội dung: {notes}")
    ok("thông báo về văn bản hạn chế không mang số ký hiệu, trích yếu, cơ quan ban hành")
    grant = "mutation ($d: uuid!, $u: String!) { %s(args: {document_id: $d, user_id: $u}) { user_id } }"
    clerk.gql(grant % "office_revoke_document_access", {"d": secret_id, "u": uid["truongkhoa"]})
    revoked = opens(director)
    clerk.gql(grant % "office_grant_document_access", {"d": secret_id, "u": uid["truongkhoa"]})
    (opens(staff), revoked, opens(director)) == (False, False, True) \
        or fail(f"quyền xem chưa đúng: chuyên viên {opens(staff)}, lãnh đạo sau khi bị gỡ {revoked}")
    ok("chuyên viên không có tên → 404; văn thư gỡ tên lãnh đạo → 404, cấp lại → mở được")
    opened_by = director.gql("""query ($e: String!) { core_audit_log(where: {action: {_eq: "file.decrypted"},
        entity_id: {_eq: $e}}) { actor_id } }""", {"e": secret_pdf["id"]})["core_audit_log"]
    sorted(r["actor_id"] for r in opened_by) == sorted([uid["vanthu"], uid["truongkhoa"], uid["truongkhoa"]]) \
        or fail(f"sổ kiểm toán chưa đúng các lần mở tệp hạn chế: {opened_by}")
    ok("mỗi lần mở là một dòng file.decrypted trong sổ kiểm toán (văn thư 1, lãnh đạo 2; lần bị chặn không ghi)")
    plain = rejected({**incoming, "symbol": f"125/ĐHCN-TC{tag}", "restricted": True})
    (plain.get("code"), plain.get("fields")) == ("invalid", {"file_ids": "not_sealed"}) \
        or fail(f"văn bản hạn chế kèm tệp chưa mã hóa không bị chặn: {plain}")
    try:
        clerk.upload(f"han-che-{tag}.txt", b"Danh sach nang luong", mime="text/plain", restricted=True)
        fail("tải tệp không phải PDF ở chế độ hạn chế không bị chặn")
    except HTTPError as exc:
        exc.status == 415 or fail(f"tải tệp không phải PDF ở chế độ hạn chế trả {exc.status}")
    ok("văn bản hạn chế chỉ kèm tệp PDF tải lên ở chế độ hạn chế (tệp thường bị trả về form, tệp khác PDF 415)")
    # Sau diễn tập sao lưu ở CI, tệp cũ nhất có từ trước lần khôi phục: mở được nghĩa là két khóa được khôi phục cùng
    oldest = clerk.gql("""{ core_files(where: {encrypted: {_eq: true}, document_files: {}},
        order_by: {created_at: asc}, limit: 1) { id created_at } }""")["core_files"][0]
    _, _, old_pdf = request("GET", f"{PUBLIC_URL}/api/files/{oldest['id']}", headers=clerk.auth)
    old_pdf.startswith(b"%PDF") or fail(f"tệp mã hóa cũ nhất không mở được: {oldest}")
    ok(f"tệp mã hóa cũ nhất (tải lên {oldest['created_at'][:16].replace('T', ' ')}) vẫn mở được")

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

    print("Dashboard điều hành")
    board = director.gql("""{ office_v_document_counts { direction restricted documents }
        office_v_overdue_by_department { in_progress }
        office_v_processing_time { documents }
        office_v_outgoing_by_month { month documents }
        readable: office_documents_aggregate(where: {direction: {_eq: "in"}, restricted: {_eq: false}}) {
          aggregate { count } }
        working: office_documents_aggregate(where: {direction: {_eq: "in"}, status: {_eq: "in_progress"},
          restricted: {_eq: false}}) { aggregate { count } } }""")
    counted = sum(r["documents"] for r in board["office_v_document_counts"] if r["direction"] == "in" and not r["restricted"])
    hidden = sum(r["documents"] for r in board["office_v_document_counts"] if r["direction"] == "in" and r["restricted"])
    by_department = sum(r["in_progress"] for r in board["office_v_overdue_by_department"])
    month = datetime.now(timezone(timedelta(hours=7))).date().replace(day=1).isoformat()
    this_month = sum(r["documents"] for r in board["office_v_outgoing_by_month"] if r["month"] == month)
    # Số chia khớp đúng văn bản lãnh đạo đọc được; văn bản hạn chế vừa tiếp nhận chỉ vào con số tổng
    counted == board["readable"]["aggregate"]["count"] and hidden >= 1 \
        and by_department == board["working"]["aggregate"]["count"] and this_month >= 1 \
        and board["office_v_processing_time"] \
        or fail(f"dashboard chưa đúng: {board}")
    ok(f"lãnh đạo khoa xem dashboard: {counted} văn bản đến, tổng theo phòng khớp {by_department} văn bản đang xử "
       f"lý, {this_month} văn bản đi phát hành tháng này; {hidden} văn bản hạn chế chỉ có con số tổng")
    try:
        clerk.gql("{ office_v_document_counts { documents } }")
        fail("văn thư đọc được số liệu dashboard")
    except RuntimeError:
        ok("dashboard chỉ cho lãnh đạo đơn vị: văn thư không đọc được")

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
        "import os\n"
        "from svc_files.config import Settings\n"
        "from svc_files.openbao import with_secrets\n"
        "from svc_files.storage import s3_client\n"
        "s = Settings.from_env(with_secrets(os.environ))\n"
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

    # F3.8: công văn vừa phát hành vào hồ sơ, đóng, nộp lưu ngay — vẫn xác thực được, phòng đọc đọc lại từ bucket lạnh
    print("Nộp lưu (nóng → lạnh)")
    case_file = staff.gql("""mutation ($o: office_case_files_insert_input!) {
        insert_office_case_files_one(object: $o) { id } }""", {"o": {
        "year": datetime.now().year, "code": f"HS-SMOKE-{tag}", "title": f"Hồ sơ kiểm tra nhanh {tag}",
        "retention_years": 5}})["insert_office_case_files_one"]["id"]
    staff.gql("""mutation ($o: office_case_file_documents_insert_input!) {
        insert_office_case_file_documents_one(object: $o) { document_id } }""",
              {"o": {"case_file_id": case_file, "document_id": out_id}})
    staff.gql("""mutation ($id: uuid!) { update_office_case_files(where: {id: {_eq: $id}},
        _set: {status: "closed"}) { affected_rows } }""", {"id": case_file})
    archived = json.loads(compose("exec", "-T", "svc-files", "python", "-m", "svc_files.archive", "now",
                                  "--case-file", case_file).decode().strip().splitlines()[-1])
    "archived" in archived or fail(f"nộp lưu lỗi: {archived}")
    doc = clerk.gql("""query ($id: uuid!) { office_documents_by_pk(id: $id) { status files { file_id }
        assignments { id } events { id } } }""", {"id": out_id})["office_documents_by_pk"]
    doc["status"] == "archived" and not doc["files"] and not doc["events"] \
        or fail(f"văn bản đã nộp lưu vẫn còn dòng thời gian, liên kết tệp trong CSDL: {doc}")
    found, _ = call_json("GET", f"{PUBLIC_URL}/api/verify/{issued['verify_code']}")
    found["result"] == "valid" and found["document"]["status"] == "archived" \
        or fail(f"cổng xác thực không còn khớp văn bản đã nộp lưu: {found}")
    room, _ = call_json("GET", f"{PUBLIC_URL}/api/case-files/{case_file}/archive", headers=clerk.auth)
    room["manifest_sha256"] == archived["archived"][0]["archive_sha256"] \
        and [d["id"] for d in room["documents"]] == [out_id] and room["files"] and room["hidden"] == 0 \
        or fail(f"phòng đọc không đọc lại được gói lưu trữ: {room}")
    ok(f"hồ sơ nộp lưu thành gói Parquet + {len(room['files'])} tệp + manifest trên bucket lạnh khóa ghi; CSDL chỉ"
       " còn bản ghi rút gọn; quét QR vẫn khớp; phòng đọc kiểm băm, DuckDB đọc lại danh sách văn bản")

    # F3.9: lượt nộp lưu vừa rồi có phả hệ OpenLineage — run cha + 4 bước, bảng Parquet đã qua kiểm chất lượng
    print("Phả hệ dữ liệu")
    pkg = archived["archived"][0]
    runs = director.gql("""query ($r: uuid!) { core_lineage_events(where: {run_id: {_eq: $r},
        event_type: {_eq: "COMPLETE"}}) { run_id outputs } }""", {"r": pkg["run_id"]})["core_lineage_events"]
    runs and runs[0]["outputs"][0].endswith(f"{pkg['archive_key']}manifest-{pkg['archive_sha256']}.json") \
        or fail(f"không có phả hệ của lượt nộp lưu vừa rồi: {runs}")
    steps = director.gql("""query ($r: uuid!) { core_lineage_events(where: {parent_run_id: {_eq: $r}},
        order_by: {id: asc}) { job event_type quality_ok } }""", {"r": runs[0]["run_id"]})["core_lineage_events"]
    [(e["job"].rsplit(".", 1)[1], e["event_type"]) for e in steps] == [
        ("files", "COMPLETE"), ("tables", "COMPLETE"), ("manifest", "COMPLETE"), ("commit", "COMPLETE")] \
        and steps[1]["quality_ok"] is True or fail(f"phả hệ thiếu bước hoặc bảng chưa qua kiểm chất lượng: {steps}")
    ok("lượt nộp lưu là một run OpenLineage với 4 bước (tệp, bảng, manifest, CSDL); bảng Parquet đạt kiểm số dòng, null")

    # Không dùng hết giới hạn đăng nhập ở đây: nó tính theo IP, make e2e chạy ngay sau từ cùng máy
    print("Giới hạn tốc độ")
    _, headers = user_login("vanthu")
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

    # F3.13: Prometheus thu được chỉ số của cổng API (lưu lượng của chính lượt smoke này), Grafana có bảng điều khiển
    print("Giám sát")

    def prometheus(expr: str) -> list:
        try:
            raw = compose("exec", "-T", "prometheus", "wget", "-q", "-O", "-",
                          f"http://localhost:9090/api/v1/query?query={urllib.parse.quote(expr)}")
            return json.loads(raw)["data"]["result"]
        except (subprocess.CalledProcessError, ValueError, KeyError):  # chưa sẵn sàng: thử lại ở vòng sau
            return []

    for _ in range(10):  # lần thu chỉ số kế tiếp cách tối đa 15 giây
        up, total = prometheus('up{job="apisix"}'), prometheus("sum(apisix_http_status)")
        routes = {r["metric"].get("route") for r in prometheus("sum by (route) (apisix_http_status)")}
        if up and up[0]["value"][1] == "1" and total and float(total[0]["value"][1]) > 0 \
                and {"graphql", "svc-files"} <= routes:
            break
        time.sleep(5)
    else:
        fail(f"Prometheus chưa đọc được chỉ số của APISIX theo route: up={up}, yêu cầu={total},"
             f" route={sorted(map(str, routes))}")
    try:
        dashboards = json.loads(compose("exec", "-T", "grafana", "wget", "-q", "-O", "-",
                                        "http://localhost:3000/api/search?type=dash-db"))
    except (subprocess.CalledProcessError, ValueError) as exc:
        fail(f"không hỏi được Grafana: {exc}")
    [d["title"] for d in dashboards] == ["Signet — cổng API"] or fail(f"Grafana thiếu bảng điều khiển: {dashboards}")
    ok(f"Prometheus đọc chỉ số cổng API ({float(total[0]['value'][1]):.0f} yêu cầu, {len(routes)} route); Grafana"
       " có bảng điều khiển cho người xem ẩn danh")

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
