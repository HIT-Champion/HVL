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

"""Văn bản đến và văn bản đi mẫu ở đủ các bước của quy trình, tạo bằng chính các thao tác người dùng gọi qua APISIX.

Nội dung là văn bản giả lập của một khoa trong trường đại học, không phải văn bản thật. Chạy lại được:
văn bản đã có (cùng số ký hiệu) thì bỏ qua.
"""

from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from moc_env import Session, compose

DEPT = {
    "ĐT": "5cc372aa-304d-4574-896c-4f3e781a2ce7",
    "KTPM": "7ee31261-b14c-4c42-8e1b-9a7e99935412",
    "HTTT": "8dec217d-fa1e-4fb3-9505-5f6033ba340e",
    "VP": "ecd87efb-e9a1-4113-a46a-f599a9d15574",
}
# người duyệt dự thảo cấp phòng của mỗi người soạn mẫu (cùng phòng trong seed/users.csv)
MANAGER = {"chuyenviendt": "totruongdt", "giamkhao": "totruongdt", "giangvienktpm": "truongbmktpm"}
TYPE_NAMES = {"CV": "Công văn", "TB": "Thông báo", "KH": "Kế hoạch", "GM": "Giấy mời", "BC": "Báo cáo"}


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
    body: str = ""       # nội dung in trong tệp PDF (tìm được theo nội dung — F2.7); trống thì dùng câu chung


CNTT = [
    Sample("128/ĐT-ĐH", "Phòng Đào tạo", "TB", "Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027", 1, "khan", "received"),
    Sample("57/KT&ĐBCL", "Phòng Khảo thí và Đảm bảo chất lượng", "KH", "Kế hoạch tự đánh giá chương trình đào tạo ngành Hệ thống thông tin", 1, stop="received"),
    Sample("12/CV-CTD", "Công ty Cổ phần Công nghệ Mẫu", "CV", "Về việc tiếp nhận sinh viên thực tập tốt nghiệp đợt tháng 1 năm 2027", 2, stop="received"),
    Sample("131/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc rà soát danh sách sinh viên đủ điều kiện xét tốt nghiệp đợt tháng 12", 2, "hoa_toc", "registered",
           body="Để chuẩn bị xét công nhận tốt nghiệp đợt tháng 12 năm 2026, Phòng Đào tạo đề nghị Khoa rà soát danh "
                "sách sinh viên dự kiến tốt nghiệp, đối chiếu đủ các điều kiện: hoàn thành chương trình đào tạo; đạt "
                "chuẩn đầu ra ngoại ngữ (chứng chỉ B1 theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam); có chứng "
                "chỉ giáo dục quốc phòng – an ninh và chứng chỉ giáo dục thể chất.\nDanh sách gửi về Phòng Đào tạo trước "
                "ngày 10/11/2026, kèm bản chụp chứng chỉ của các trường hợp còn thiếu minh chứng."),
    Sample("44/KHCN", "Phòng Khoa học và Hợp tác quốc tế", "TB", "Thông báo đăng ký đề tài nghiên cứu khoa học cấp trường năm 2027", 3, "khan", "registered"),
    Sample("209/TCHC", "Phòng Tổ chức – Hành chính", "GM", "Giấy mời dự hội nghị viên chức, người lao động năm 2026", 3, stop="registered"),
    Sample("135/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc xây dựng kế hoạch giảng dạy học kỳ hè năm học 2026–2027", 5, stop="directed", lead="ĐT", supports=("KTPM", "HTTT")),
    Sample("61/KT&ĐBCL", "Phòng Khảo thí và Đảm bảo chất lượng", "CV", "Về việc nộp đề thi kết thúc học phần học kỳ I", 4, "khan", "directed", lead="KTPM", handler="giangvienktpm"),
    Sample("88/CTSV", "Phòng Công tác sinh viên", "CV", "Về việc xét cấp học bổng khuyến khích học tập học kỳ I năm học 2026–2027", 6, stop="assigned", lead="ĐT",
           body="Căn cứ Quy định về học bổng khuyến khích học tập của Trường, Phòng Công tác sinh viên đề nghị Khoa xét "
                "chọn sinh viên có điểm trung bình chung học kỳ từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.\nBiên bản "
                "họp xét của Khoa và danh sách đề nghị gửi về Phòng trước ngày 15/11/2026."),
    Sample("47/KHCN", "Phòng Khoa học và Hợp tác quốc tế", "CV", "Về việc cử giảng viên tham gia hội thảo chuyển đổi số trong giáo dục đại học", 7, stop="assigned", lead="KTPM", handler="giangvienktpm"),
    Sample("140/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc cập nhật đề cương chi tiết học phần theo chuẩn đầu ra mới", 8, "khan", "assigned", lead="ĐT", supports=("KTPM",)),
    # giám khảo đăng nhập là thấy ngay một việc khẩn chờ xử lý (cùng dự thảo phúc đáp bị trả lại ở OUT_CNTT)
    Sample("152/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc góp ý dự thảo Quy định đào tạo trình độ đại học theo hệ thống tín chỉ", 2, "khan", "assigned", lead="ĐT", handler="giamkhao", due_in=5,
           body="Phòng Đào tạo gửi kèm dự thảo Quy định đào tạo trình độ đại học theo hệ thống tín chỉ (sửa đổi), đề "
                "nghị Khoa lấy ý kiến giảng viên, chuyên viên.\nÝ kiến tập trung vào: điều kiện đăng ký học vượt, cách "
                "tính điểm trung bình tích lũy, xử lý học vụ. Văn bản góp ý gửi về Phòng Đào tạo trước ngày 06/11/2026."),
    Sample("95/CTSV", "Phòng Công tác sinh viên", "TB", "Thông báo tổ chức tuần sinh hoạt công dân cho sinh viên khóa mới", 12, stop="done"),
    Sample("118/ĐT-ĐH", "Phòng Đào tạo", "CV", "Về việc báo cáo khối lượng giảng dạy năm học 2025–2026", 15, stop="done", lead="ĐT"),
    Sample("38/KHCN", "Phòng Khoa học và Hợp tác quốc tế", "CV", "Về việc nghiệm thu đề tài nghiên cứu khoa học sinh viên năm 2026", 20, stop="done", lead="KTPM", handler="giangvienktpm"),
    Sample("201/TCHC", "Phòng Tổ chức – Hành chính", "TB", "Thông báo lịch nghỉ Tết Dương lịch năm 2027 của cán bộ, giảng viên", 9, stop="filed"),
]
KT = [
    Sample("129/ĐT-ĐH", "Phòng Đào tạo", "TB", "Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027 (Khoa Kinh tế)", 1, stop="received"),
    Sample("89/CTSV", "Phòng Công tác sinh viên", "CV", "Về việc xét cấp học bổng khuyến khích học tập (Khoa Kinh tế)", 4, stop="registered"),
]


@dataclass
class Draft:
    """Văn bản đi mẫu: chuyên viên soạn rồi đi qua quy trình van-ban-di tới bước `stop`."""

    type_code: str
    summary: str
    body: str
    recipients: tuple[str, ...]
    # bước dừng lại: draft | in_review | returned | approved | issued
    stop: str = "issued"
    drafter: str = "chuyenviendt"
    is_public: bool = False
    reply_to: str | None = None   # số ký hiệu của văn bản đến được trả lời
    return_note: str = "Bổ sung số liệu giảng viên thỉnh giảng, ghi rõ số tiết quy đổi."   # ý kiến khi stop="returned"


OUT_CNTT = [
    Draft("TB", "Thông báo lịch họp giao ban tháng 11 năm 2026",
          "Khoa Công nghệ thông tin thông báo lịch họp giao ban tháng 11 năm 2026 như sau:\n"
          "1. Thời gian: 14 giờ 00, thứ Hai ngày 02/11/2026.\n"
          "2. Địa điểm: Phòng họp tầng 3, nhà A1.\n"
          "3. Thành phần: Trưởng các bộ môn, Tổ trưởng Tổ Đào tạo, giáo vụ khoa.\n"
          "Đề nghị các đơn vị chuẩn bị báo cáo kết quả công tác tháng 10 và gửi về Văn phòng khoa trước ngày 30/10/2026.",
          ("Các bộ môn", "Tổ Đào tạo"), is_public=True),
    Draft("CV", "Về việc cử giảng viên tham dự hội thảo chuyển đổi số trong giáo dục đại học",
          "Phúc đáp Công văn số 47/KHCN của Phòng Khoa học và Hợp tác quốc tế, Khoa Công nghệ thông tin cử giảng viên "
          "Vũ Thị Mai, Bộ môn Kỹ thuật phần mềm, tham dự hội thảo và trình bày tham luận về ứng dụng nguồn mở trong "
          "quản lý văn bản.\nKhoa trân trọng đề nghị Phòng tổng hợp, báo cáo Ban Giám hiệu.",
          ("Phòng Khoa học và Hợp tác quốc tế",), drafter="giangvienktpm", reply_to="47/KHCN"),
    Draft("KH", "Kế hoạch tổ chức seminar khoa học tháng 12 năm 2026",
          "Nhằm đẩy mạnh hoạt động nghiên cứu khoa học của giảng viên và sinh viên, Khoa xây dựng kế hoạch tổ chức "
          "seminar khoa học tháng 12 năm 2026.\nMỗi bộ môn đăng ký ít nhất hai báo cáo, gửi về Tổ Đào tạo trước ngày 20/11/2026.",
          ("Các bộ môn",), stop="approved"),
    Draft("CV", "Về việc báo cáo kết quả rà soát đề cương chi tiết học phần",
          "Thực hiện Công văn số 140/ĐT-ĐH của Phòng Đào tạo, Khoa đã rà soát đề cương chi tiết 42 học phần theo chuẩn "
          "đầu ra mới.\nKết quả rà soát chi tiết gửi kèm theo công văn này.",
          ("Phòng Đào tạo",), stop="in_review"),
    Draft("BC", "Báo cáo khối lượng giảng dạy học kỳ I năm học 2026–2027",
          "Khoa Công nghệ thông tin báo cáo khối lượng giảng dạy học kỳ I năm học 2026–2027 của giảng viên cơ hữu và "
          "thỉnh giảng như bảng tổng hợp kèm theo.",
          ("Phòng Đào tạo",), stop="returned"),
    Draft("TB", "Thông báo tuyển sinh viên tham gia nhóm nghiên cứu phần mềm nguồn mở",
          "Bộ môn Kỹ thuật phần mềm thông báo tuyển sinh viên năm thứ ba, năm thứ tư tham gia nhóm nghiên cứu phần mềm "
          "nguồn mở năm học 2026–2027.",
          ("Sinh viên các khóa",), stop="draft", drafter="giangvienktpm"),
    # việc thứ hai trong hộp việc của giám khảo: sửa dự thảo theo ý kiến tổ trưởng
    Draft("CV", "Về việc góp ý dự thảo Quy định đào tạo trình độ đại học theo hệ thống tín chỉ",
          "Phúc đáp Công văn số 152/ĐT-ĐH của Phòng Đào tạo, Khoa Công nghệ thông tin tổng hợp ý kiến góp ý như sau:\n"
          "1. Điều kiện đăng ký học vượt: đề nghị giữ mức điểm trung bình tích lũy từ 2,5 trở lên.\n"
          "2. Xử lý học vụ: đề nghị thêm một lần cảnh báo trước khi buộc thôi học.\n"
          "Khoa trân trọng đề nghị Phòng Đào tạo tổng hợp.",
          ("Phòng Đào tạo",), stop="returned", drafter="giamkhao", reply_to="152/ĐT-ĐH",
          return_note="Bổ sung ý kiến của Bộ môn Kỹ thuật phần mềm về cách tính điểm trung bình tích lũy rồi trình lại."),
]


def today():
    """Hôm nay theo giờ Việt Nam, như svc-workflow so ngày ban hành và hạn — không theo múi giờ của máy chạy seed."""
    return datetime.now(timezone(timedelta(hours=7))).date()


def _exists(clerk: Session, symbol: str) -> bool:
    data = clerk.gql("query ($s: String!) { office_documents(where: {symbol: {_eq: $s}}, limit: 1) { id } }", {"s": symbol})
    return bool(data["office_documents"])


def _letter_html(s: Sample, issued: date, recipient: str, parent: str | None) -> str:
    """Công văn đến dạng HTML để in ra PDF có lớp chữ: tiêu đề theo thể thức NĐ 30, nội dung, chữ ký."""
    e = html.escape
    kind = TYPE_NAMES.get(s.type_code, "Văn bản")
    what = s.summary.removeprefix(kind + " ")
    body = s.body or (f"Thực hiện kế hoạch năm học 2026–2027, {s.issuer} gửi {recipient} {kind.lower()} "
                      f"{what[0].lower() + what[1:]}.\nĐề nghị {recipient} phân công cán bộ đầu mối, triển khai và báo "
                      f"cáo kết quả về {s.issuer} đúng thời hạn.")
    own = f"<div>{e(parent.upper())}</div>" if parent and s.issuer.startswith("Phòng") else ""
    title = (f'<div class="vv">V/v {e(s.summary.removeprefix("Về việc "))}</div>' if s.type_code == "CV" else "")
    heading = ("" if s.type_code == "CV" else
               f'<h1>{e(kind.upper())}</h1><div class="sum">{e(what)}</div>')
    month = f"{issued.month:02d}" if issued.month <= 2 else str(issued.month)
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 20mm 15mm 20mm 30mm; }}
body {{ font-family: "Liberation Serif", serif; font-size: 13pt; line-height: 1.35; }}
table.head {{ width: 100%; border-collapse: collapse; }}
table.head td {{ vertical-align: top; text-align: center; font-size: 12pt; }}
.b {{ font-weight: bold; }} .rule {{ width: 30%; margin: 1pt auto 4pt; border-top: 0.8pt solid #000; }}
.vv {{ font-size: 12pt; margin-top: 4pt; }} .date {{ font-style: italic; margin-top: 6pt; }}
h1 {{ font-size: 14pt; text-align: center; margin: 14pt 0 0; }} .sum {{ text-align: center; font-weight: bold; }}
.to {{ text-align: center; margin: 12pt 0; }} p {{ text-indent: 10mm; text-align: justify; margin: 0 0 6pt; }}
.sign {{ margin: 18pt 0 0 55%; text-align: center; }} .note {{ margin-top: 30pt; font-size: 9pt; color: #555; }}
</style></head><body>
<table class="head"><tr>
<td style="width: 40%">{own}<div class="b">{e(s.issuer.upper())}</div><div class="rule"></div>
<div>Số: {e(s.symbol)}</div>{title}</td>
<td><div class="b">CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</div><div class="b">Độc lập - Tự do - Hạnh phúc</div>
<div class="rule"></div><div class="date">Hà Nội, ngày {issued.day:02d} tháng {month} năm {issued.year}</div></td>
</tr></table>
{heading}<div class="to">Kính gửi: {e(recipient)}</div>
{"".join(f"<p>{e(line)}</p>" for line in body.split(chr(10)))}
<p>Trân trọng./.</p>
<div class="sign"><div class="b">TRƯỞNG PHÒNG</div><div style="margin-top: 22mm">(Đã ký)</div></div>
<div class="note">Văn bản giả lập để chạy thử Signet, không phải văn bản thật.</div>
</body></html>"""


def render_pdfs(pages: list[str]) -> list[bytes]:
    """In các trang HTML ra PDF bằng WeasyPrint có sẵn trong container svc-files (phông tiếng Việt đã cài)."""
    if not pages:
        return []
    script = ("import base64, json, sys\nfrom weasyprint import HTML\n"
              "print(json.dumps([base64.b64encode(HTML(string=h).write_pdf()).decode() for h in json.load(sys.stdin)]))")
    out = compose("exec", "-T", "svc-files", "python", "-c", script, stdin=json.dumps(pages).encode())
    return [base64.b64decode(p) for p in json.loads(out)]


def _receive(clerk: Session, s: Sample, pdf: bytes) -> str:
    file = clerk.upload(f"{s.symbol.replace('/', '-')}.pdf", pdf)
    doc = clerk.gql(
        "mutation ($d: jsonb!) { receiveIncoming(data: $d) { document_id } }",
        {"d": {
            "type_code": s.type_code, "symbol": s.symbol, "issuer_name": s.issuer, "summary": s.summary,
            "issued_on": (today() - timedelta(days=s.days_ago)).isoformat(), "urgency": s.urgency,
            "file_ids": [file["id"]],
        }},
    )
    return doc["receiveIncoming"]["document_id"]


def _run(clerk_name: str, director_name: str, samples: list[Sample]) -> int:
    clerk, director = Session(clerk_name), Session(director_name)
    people: dict[str, Session] = {}

    def person(name: str) -> Session:
        if name not in people:
            people[name] = Session(name)
        return people[name]

    tenant = clerk.gql("{ core_tenants { name parent_name } }")["core_tenants"][0]
    todo = [s for s in samples if not _exists(clerk, s.symbol)]
    pdfs = render_pdfs([_letter_html(s, today() - timedelta(days=s.days_ago), tenant["name"], tenant["parent_name"])
                        for s in todo])
    created = 0
    for s, pdf in zip(todo, pdfs, strict=True):
        doc_id = _receive(clerk, s, pdf)
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
            "due_on": (today() + timedelta(days=s.due_in)).isoformat(),
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


def _user_id(session: Session, username: str) -> str:
    return session.gql("query ($u: String!) { core_users(where: {username: {_eq: $u}}) { id } }",
                       {"u": username})["core_users"][0]["id"]


def _run_outgoing(clerk_name: str, director_name: str, drafts: list[Draft]) -> int:
    clerk, director = Session(clerk_name), Session(director_name)
    people: dict[str, Session] = {}

    def person(name: str) -> Session:
        if name not in people:
            people[name] = Session(name)
        return people[name]

    signer = _user_id(clerk, director_name)
    created = 0
    for d in drafts:
        drafter = person(d.drafter)
        found = drafter.gql("query ($s: String!) { office_documents(where: {direction: {_eq: \"out\"}, "
                            "summary: {_eq: $s}}, limit: 1) { id } }", {"s": d.summary})["office_documents"]
        if found:
            continue
        draft: dict = {"type_code": d.type_code, "summary": d.summary, "body": d.body, "recipients": list(d.recipients)}
        if d.reply_to:
            reply = clerk.gql("query ($s: String!) { office_documents(where: {symbol: {_eq: $s}}, limit: 1) { id } }",
                              {"s": d.reply_to})["office_documents"]
            if reply:
                draft["reply_to_id"] = reply[0]["id"]
        doc_id = drafter.gql("mutation ($o: office_documents_insert_input!) { insert_office_documents_one(object: $o) "
                             "{ id } }", {"o": draft})["insert_office_documents_one"]["id"]
        created += 1
        if d.stop == "draft":
            continue
        drafter.gql("mutation ($d: uuid!, $s: String!) { submitOutgoing(documentId: $d, signerId: $s) { status } }",
                    {"d": doc_id, "s": signer})
        if d.stop == "in_review":
            continue
        manager = person(MANAGER[d.drafter])
        task = manager.wait_task(doc_id, "vbdi.duyetPhong")
        if d.stop == "returned":
            manager.complete(task, "return", {"note": d.return_note})
            continue
        manager.complete(task, "approve", {"note": "Đồng ý, trình lãnh đạo khoa ký."})
        director.complete(director.wait_task(doc_id, "vbdi.duyetDonVi"), "approve", {})
        if d.stop == "approved":
            continue
        clerk.complete(clerk.wait_task(doc_id, "vbdi.phatHanh"), "issue", {"is_public": d.is_public})
    return created


def run() -> None:
    created = _run("vanthu", "truongkhoa", CNTT) + _run("vanthukt", "truongkhoakt", KT)
    print(f"  văn bản đến mẫu: {created} văn bản mới (văn bản đã có thì bỏ qua)")
    created = _run_outgoing("vanthu", "truongkhoa", OUT_CNTT)
    print(f"  văn bản đi mẫu: {created} văn bản mới, đủ các bước soạn → duyệt → phát hành")
