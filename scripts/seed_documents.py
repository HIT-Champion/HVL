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

"""Văn bản mẫu ở đủ các bước của quy trình, tạo bằng chính các thao tác người dùng gọi qua APISIX.

Nội dung là văn bản giả lập của một khoa trong trường đại học, không phải văn bản thật. Chạy lại được:
văn bản đã có (cùng số ký hiệu) thì bỏ qua.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from moc_env import Session

DEPT = {
    "ĐT": "5cc372aa-304d-4574-896c-4f3e781a2ce7",
    "KTPM": "7ee31261-b14c-4c42-8e1b-9a7e99935412",
    "HTTT": "8dec217d-fa1e-4fb3-9505-5f6033ba340e",
    "VP": "ecd87efb-e9a1-4113-a46a-f599a9d15574",
}
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n" \
      b"trailer<</Root 1 0 R>>\n%%EOF\n"


@dataclass
class Sample:
    symbol: str
    issuer: str
    type_code: str
    summary: str
    days_ago: int
    urgency: str = "normal"
    # bước dừng lại: received | registered | directed | assigned | done | filed
    stop: str = "registered"
    lead: str = "ĐT"
    supports: tuple[str, ...] = ()
    handler: str = "chuyenviendt"
    due_in: int = 7


CNTT = [
    Sample("128/ĐT-ĐH", "Phòng Đào tạo", "TB", "Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027", 1, "khan", "received"),
    Sample("57/KT&ĐBCL", "Phòng Khảo thí và Đảm bảo chất lượng", "KH", "Kế hoạch tự đánh giá chương trình đào tạo ngành Hệ thống thông tin", 1, stop="received"),
    Sample("12/CV-CTD", "Công ty Cổ phần Công nghệ Mẫu", "CV", "Về việc tiếp nhận sinh viên thực tập tốt nghiệp đợt tháng 1 năm 2027", 2, stop="received"),
    Sample("131/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc rà soát danh sách sinh viên đủ điều kiện xét tốt nghiệp đợt tháng 12", 2, "hoa_toc", "registered"),
    Sample("44/KHCN", "Phòng Khoa học và Hợp tác quốc tế", "TB", "Thông báo đăng ký đề tài nghiên cứu khoa học cấp trường năm 2027", 3, "khan", "registered"),
    Sample("209/TCHC", "Phòng Tổ chức – Hành chính", "GM", "Giấy mời dự hội nghị viên chức, người lao động năm 2026", 3, stop="registered"),
    Sample("135/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc xây dựng kế hoạch giảng dạy học kỳ hè năm học 2026–2027", 5, stop="directed", lead="ĐT", supports=("KTPM", "HTTT")),
    Sample("61/KT&ĐBCL", "Phòng Khảo thí và Đảm bảo chất lượng", "CV", "Về việc nộp đề thi kết thúc học phần học kỳ I", 4, "khan", "directed", lead="KTPM", handler="giangvienktpm"),
    Sample("88/CTSV", "Phòng Công tác sinh viên", "CV", "Về việc xét cấp học bổng khuyến khích học tập học kỳ I năm học 2026–2027", 6, stop="assigned", lead="ĐT"),
    Sample("47/KHCN", "Phòng Khoa học và Hợp tác quốc tế", "CV", "Về việc cử giảng viên tham gia hội thảo chuyển đổi số trong giáo dục đại học", 7, stop="assigned", lead="KTPM", handler="giangvienktpm"),
    Sample("140/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc cập nhật đề cương chi tiết học phần theo chuẩn đầu ra mới", 8, "khan", "assigned", lead="ĐT", supports=("KTPM",)),
    Sample("95/CTSV", "Phòng Công tác sinh viên", "TB", "Thông báo tổ chức tuần sinh hoạt công dân cho sinh viên khóa mới", 12, stop="done"),
    Sample("118/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc báo cáo khối lượng giảng dạy năm học 2025–2026", 15, stop="done", lead="ĐT"),
    Sample("38/KHCN", "Phòng Khoa học và Hợp tác quốc tế", "CV", "Về việc nghiệm thu đề tài nghiên cứu khoa học sinh viên năm 2026", 20, stop="done", lead="KTPM", handler="giangvienktpm"),
    Sample("201/TCHC", "Phòng Tổ chức – Hành chính", "TB", "Thông báo lịch nghỉ Tết Dương lịch năm 2027 của cán bộ, giảng viên", 9, stop="filed"),
]
KT = [
    Sample("129/ĐT-ĐH", "Phòng Đào tạo", "TB", "Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027 (Khoa Kinh tế)", 1, stop="received"),
    Sample("89/CTSV", "Phòng Công tác sinh viên", "CV", "Về việc xét cấp học bổng khuyến khích học tập (Khoa Kinh tế)", 4, stop="registered"),
]


def _exists(clerk: Session, symbol: str) -> bool:
    data = clerk.gql("query ($s: String!) { office_documents(where: {symbol: {_eq: $s}}, limit: 1) { id } }", {"s": symbol})
    return bool(data["office_documents"])


def _receive(clerk: Session, s: Sample) -> str:
    file = clerk.upload(f"{s.symbol.replace('/', '-')}.pdf", PDF)
    doc = clerk.gql(
        "mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) { id } }",
        {"o": {
            "type_code": s.type_code, "symbol": s.symbol, "issuer_name": s.issuer, "summary": s.summary,
            "issued_on": (date.today() - timedelta(days=s.days_ago)).isoformat(), "urgency": s.urgency,
            "files": {"data": [{"file_id": file["id"], "role": "main"}]},
        }},
    )
    return doc["insert_office_documents_one"]["id"]


def _run(clerk_name: str, director_name: str, samples: list[Sample]) -> int:
    clerk, director = Session(clerk_name), Session(director_name)
    people: dict[str, Session] = {}

    def person(name: str) -> Session:
        if name not in people:
            people[name] = Session(name)
        return people[name]

    created = 0
    for s in samples:
        if _exists(clerk, s.symbol):
            continue
        doc_id = _receive(clerk, s)
        created += 1
        if s.stop == "received":
            continue
        clerk.gql("mutation ($id: uuid!) { registerIncoming(documentId: $id) { register_number } }", {"id": doc_id})
        if s.stop == "registered":
            continue
        task = director.wait_task(doc_id, "vbden.chiDao")
        if s.stop == "filed":
            director.complete(task, "file", {"note": "Lưu để biết, không cần xử lý."})
            continue
        director.complete(task, "direct", {
            "instruction": f"Giao {'Tổ Đào tạo' if s.lead == 'ĐT' else 'Bộ môn ' + s.lead} chủ trì thực hiện, báo cáo đúng hạn.",
            "lead_department_id": DEPT[s.lead], "supports": [DEPT[d] for d in s.supports],
            "due_on": (date.today() + timedelta(days=s.due_in)).isoformat(),
        })
        if s.stop == "directed":
            continue
        manager = person("totruongdt" if s.lead == "ĐT" else "truongbmktpm")
        handler = person(s.handler)
        handler_id = manager.gql("query ($u: String!) { core_users(where: {username: {_eq: $u}}) { id } }",
                                 {"u": s.handler})["core_users"][0]["id"]
        manager.complete(manager.wait_task(doc_id, "vbden.phanCong"), "assign",
                         {"user_id": handler_id, "note": "Đề nghị xử lý và báo cáo kết quả."})
        if s.stop == "assigned":
            continue
        handler.complete(handler.wait_task(doc_id, "vbden.xuLy"), "done",
                         {"result_note": "Đã thực hiện xong, gửi báo cáo kết quả cho lãnh đạo khoa."})
    return created


def run() -> None:
    created = _run("vanthu", "truongkhoa", CNTT) + _run("vanthukt", "truongkhoakt", KT)
    print(f"  văn bản mẫu: {created} văn bản mới (văn bản đã có thì bỏ qua)")
