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

văn thư tải công văn lên (qua ClamAV) → nhập văn bản → vào sổ, có số đến → lãnh đạo khoa chỉ đạo, giao
Tổ Đào tạo chủ trì → tổ trưởng phân công chuyên viên → chuyên viên báo xong. Kèm các kiểm tra chặn: tệp
EICAR, không token, đường quản trị, đơn vị khác không thấy văn bản.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta

from moc_env import ENV, PUBLIC_URL, REALM, HTTPError, Session, call_json, request

DEPT_DT = "5cc372aa-304d-4574-896c-4f3e781a2ce7"
DEPT_KTPM = "7ee31261-b14c-4c42-8e1b-9a7e99935412"
# Chuỗi kiểm thử chuẩn EICAR (không phải mã độc thật), ghép từ hai nửa để chính tệp này không bị chặn
EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode()
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n" \
      b"trailer<</Root 1 0 R>>\n%%EOF\n"

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

    print("Trạm kiểm dịch")
    try:
        clerk.upload("eicar.pdf", EICAR)
        fail("tệp EICAR không bị chặn")
    except HTTPError as exc:
        exc.status == 422 or fail(f"tệp EICAR trả {exc.status}")
    ok("tệp EICAR bị ClamAV chặn (422), không lưu")

    print("Luồng văn bản đến")
    file = clerk.upload(f"cong-van-{tag}.pdf", PDF)
    ok(f"văn thư tải công văn lên, quét sạch ({file['sha256'][:12]}…)")
    doc = clerk.gql(
        """mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id status } }""",
        {"o": {
            "type_code": "CV", "symbol": f"123/ĐHCN-ĐT{tag}", "issuer_name": "Trường Đại học Công nghiệp",
            "issued_on": date.today().isoformat(), "urgency": "khan",
            "summary": f"Về việc rà soát chương trình đào tạo năm học 2026–2027 (kiểm tra {tag})",
            "files": {"data": [{"file_id": file["id"], "role": "main"}]},
        }},
    )["insert_office_documents_one"]
    doc_id = doc["id"]
    doc["status"] == "received" or fail("văn bản mới không ở trạng thái received")
    ok("văn thư nhập văn bản đến kèm tệp")

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

    print(f"Đạt {passed} kiểm tra.")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, RuntimeError) as exc:
        fail(str(exc))
