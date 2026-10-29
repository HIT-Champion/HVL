#!/usr/bin/env python3
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

"""Kho văn bản mẫu và bộ câu hỏi kèm đáp án để thử, đo trợ lý hỏi đáp trên kho văn bản (F4.2).

Mọi văn bản đều giả lập: cơ quan hư cấu "Trường Đại học Mẫu", người ký "Nguyễn Văn A", chân trang mỗi trang "Văn
bản giả lập để chạy thử Mộc, không phải văn bản thật"; không có dữ liệu cá nhân thật. Đầu ra (commit vào kho mã):

    seed/hoi-dap/01-hoc-bong.pdf … 05-nghi-tet.pdf    5 văn bản nhiều trang (PDF có lớp chữ, WeasyPrint, thể thức NĐ 30)
    seed/hoi-dap/06-han-che.pdf                       văn bản hạn chế có cụm từ riêng "phương án XANH LAM"
    seed/hoi-dap/cau-hoi.json                         văn bản (số ký hiệu, trang, giao việc) + câu hỏi, đáp án đúng

Mỗi câu hỏi có loại (``loai``) và đường bộ định tuyến phải chọn (``route``, #423): ``van_ban`` tra cứu văn bản,
``noi_tiep`` câu nối tiếp (kèm ``previous``, vẫn đi ``van_ban``), ``gioi_thieu``, ``huong_dan`` (đáp án là mục của
tệp Giới thiệu trợ lý hay docs/huong-dan: ``{"guide": "<tệp>#<neo>"}``), ``ngoai_pham_vi`` (phải từ chối).

Trang 2 trở đi bắt đầu bằng ngắt trang tường minh (``break-before: page``) nên số trang và trang chứa từng câu trả
lời là tất định; mỗi thông tin cần hỏi nằm trong đúng một câu, trên đúng một trang. Câu hỏi về văn bản mẫu của make
seed (88/CTSV, 131/ĐT-ĐH, công văn đi cử giảng viên dự hội thảo đã phát hành) lấy nguyên câu trong
scripts/seed_documents.py.

Cách chạy:

    make hoi-dap-mau
        = python3 scripts/hoi_dap_mau.py --mode container: in trong container svc-files đang chạy. Cần make up.
    cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt \\
        python ../../scripts/hoi_dap_mau.py --mode local
        in ngay trên máy bằng WeasyPrint của môi trường test svc-files (cần phông Liberation Serif).
    … hoi_dap_mau.py --mode local --check
        không ghi gì: in lại trong bộ nhớ, so từng byte với tệp đã commit (chạy lại ra đúng các byte cũ — cùng
        WeasyPrint, cùng phông) và kiểm bằng pypdf.

Sau khi in, mọi chế độ đều kiểm bằng pypdf: số trang đúng, câu trả lời nằm đúng trang và chỉ ở trang đó, từ khóa có
trên trang, siêu dữ liệu chỉ có Producer, không có đường dẫn máy. Chỉ dùng thư viện chuẩn ở phía máy chủ; khi chạy
trong container, chính tệp này được gửi qua stdin cho ``python -c`` (``--inside``), kết quả về lại qua stdout.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date

# tên cũ của sản phẩm: PDF mẫu đã commit và số đo trợ lý dựng từ chuỗi này — đổi là in lại, đo lại
NOTE = "Văn bản giả lập để chạy thử Mộc, không phải văn bản thật."
ISSUER = "Trường Đại học Mẫu"
MOTTO = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
MOTTO2 = "Độc lập - Tự do - Hạnh phúc"
SIGNER = "Nguyễn Văn A"
PLACE = "Hà Nội"
MAX_TOTAL = 1024 * 1024
# Chuỗi không được có trong tệp PDF: đường dẫn máy người in, tên người dùng
LEAKS = (*(f"/{d}/".encode() for d in ("home", "Users", "tmp")), b"file://", b"C:\\")


@dataclass(frozen=True)
class Assign:
    """Giao việc khi nạp kho (demo.py hoi-dap): lãnh đạo khoa chỉ đạo đơn vị chủ trì, trưởng đơn vị phân công."""

    lead: str                         # mã phòng trong seed/tenants.sql: ĐT, KTPM, HTTT, VP
    handler: str | None = None        # tài khoản được phân công; None: dừng ở bước chỉ đạo


@dataclass(frozen=True)
class Doc:
    """Một văn bản đến mẫu nhiều trang. ``pages``: mỗi trang một bộ đoạn; đoạn bắt đầu bằng "# " là đề mục (in
    đậm), "= " là dòng giữa trang in đậm (QUYẾT ĐỊNH:). Chữ ký và nơi nhận in cuối trang cuối."""

    file: str
    type_code: str
    symbol: str
    issued: date
    summary: str
    title: str
    trich_yeu: str
    pages: tuple[tuple[str, ...], ...]
    signer: tuple[str, ...]
    receivers: tuple[str, ...]
    authority: str | None = None
    to: tuple[str, ...] = ()
    restricted: bool = False
    assign: Assign | None = None


@dataclass(frozen=True)
class Question:
    """``expect``: "none" (không được có câu trả lời) hoặc các nguồn đúng — khớp một trong số đó trong 3 nguồn đầu là
    đúng. ``forbid``: số ký hiệu không bao giờ được xuất hiện trong nguồn. ``evidence``: câu chứa câu trả lời,
    nguyên văn trên trang mong đợi (để kiểm mẫu và để người đọc kết quả đo đối chiếu). ``loai``: loại câu (khóa của
    ``ROUTES``); ``previous``: câu hỏi của lượt trước, chỉ ở câu ``noi_tiep``."""

    id: str
    user: str
    question: str
    expect: tuple[dict, ...] | str
    keywords: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    evidence: str | None = None
    loai: str = "van_ban"
    previous: str | None = None


# loại câu → đường bộ định tuyến của trợ lý phải chọn (services/svc-files/src/svc_files/assist/route.py)
ROUTES = {"van_ban": "van_ban", "noi_tiep": "van_ban", "gioi_thieu": "gioi_thieu", "huong_dan": "huong_dan",
          "ngoai_pham_vi": "ngoai_pham_vi", "viec_cua_toi": "viec_cua_toi", "dem_van_ban": "dem_van_ban",
          # câu về văn bản thật của nguồn công khai (#446): tìm như van_ban, đếm riêng để 19 câu van_ban giữ nguyên
          "cong_khai": "van_ban"}
INTRO = "services/svc-files/src/svc_files/assist/gioi_thieu"


DOCS = (
    Doc("01-hoc-bong.pdf", "QĐ", "15/QĐ-ĐHM", date(2026, 9, 15),
        "Quyết định ban hành Quy định xét, cấp học bổng tài trợ cho sinh viên đại học chính quy",
        "QUYẾT ĐỊNH", "Về việc xét, cấp học bổng tài trợ cho sinh viên đại học chính quy",
        authority="HIỆU TRƯỞNG TRƯỜNG ĐẠI HỌC MẪU",
        pages=(
            ("Căn cứ Luật Giáo dục đại học;",
             "Căn cứ Quy chế tổ chức và hoạt động của Trường Đại học Mẫu;",
             "Theo đề nghị của Trưởng phòng Công tác sinh viên.",
             "= QUYẾT ĐỊNH:",
             "# Điều 1. Đối tượng áp dụng",
             "Quyết định này áp dụng đối với sinh viên đại học chính quy đang theo học tại Trường.",
             "# Điều 2. Tiêu chuẩn xét chọn",
             "Sinh viên được xét học bổng khi đăng ký tối thiểu 15 tín chỉ trong học kỳ.",
             "Trong học kỳ xét, sinh viên không có học phần nào bị điểm F và không bị kỷ luật từ mức khiển trách "
             "trở lên.",
             "Sinh viên thuộc diện hưởng chính sách miễn, giảm học phí vẫn được xét như sinh viên khác."),
            ("# Điều 3. Mức học bổng",
             "Mức học bổng được tính theo học phí sinh viên phải nộp trong học kỳ xét.",
             "Học bổng loại Xuất sắc bằng 120% mức học phí của học kỳ.",
             "Học bổng loại Giỏi bằng 110% mức học phí của học kỳ.",
             "Học bổng loại Khá bằng 100% mức học phí của học kỳ.",
             "# Điều 4. Quỹ học bổng",
             "Quỹ học bổng mỗi học kỳ bằng 8% tổng học phí thu được của sinh viên đại học chính quy.",
             "Khoa được phân bổ quỹ theo tỉ lệ số sinh viên của Khoa trên tổng số sinh viên toàn Trường."),
            ("# Điều 5. Hồ sơ và chi trả",
             "Khoa lập danh sách đề nghị kèm biên bản họp xét của Khoa, gửi Phòng Công tác sinh viên.",
             "Học bổng được chuyển khoản cho sinh viên trong vòng 20 ngày kể từ ngày ký quyết định công nhận.",
             "Sinh viên chưa có tài khoản ngân hàng đăng ký bổ sung tại Phòng Kế hoạch – Tài chính.",
             "# Điều 6. Hiệu lực thi hành",
             "Quyết định này có hiệu lực kể từ ngày ký.",
             "Trưởng phòng Công tác sinh viên, Trưởng các khoa và sinh viên chịu trách nhiệm thi hành Quyết định "
             "này./.")),
        signer=("KT. HIỆU TRƯỞNG", "PHÓ HIỆU TRƯỞNG"), receivers=("- Như Điều 6;", "- Lưu: VT, CTSV."),
        assign=Assign("ĐT", "chuyenviendt")),
    Doc("02-thi-ket-thuc.pdf", "KH", "22/KH-ĐHM", date(2026, 10, 2),
        "Kế hoạch tổ chức thi kết thúc học phần học kỳ I năm học 2026–2027",
        "KẾ HOẠCH", "Tổ chức thi kết thúc học phần học kỳ I năm học 2026–2027",
        pages=(
            ("Căn cứ Quy chế đào tạo trình độ đại học của Trường, Phòng Đào tạo xây dựng Kế hoạch như sau:",
             "# I. MỤC ĐÍCH, YÊU CẦU",
             "Đánh giá khách quan kết quả học tập của sinh viên; tổ chức thi nghiêm túc, đúng quy chế.",
             "# II. LỊCH THI",
             "Kỳ thi kết thúc học phần học kỳ I diễn ra từ ngày 04/01/2027 đến ngày 16/01/2027.",
             "Lịch thi chi tiết của từng học phần được công bố trên cổng thông tin đào tạo trước 14 ngày.",
             "Sinh viên mang thẻ sinh viên và có mặt tại phòng thi trước giờ thi 15 phút."),
            ("# III. RA ĐỀ VÀ NỘP ĐỀ THI",
             "Mỗi học phần có ít nhất hai đề thi tương đương, kèm thang điểm chi tiết.",
             "Hạn nộp đề thi và đáp án về Tổ Đào tạo là ngày 14/12/2026.",
             "Đề thi được niêm phong trong phong bì có chữ ký của Trưởng bộ môn.",
             "Bộ môn chịu trách nhiệm bảo mật đề thi cho tới khi bàn giao."),
            ("# IV. CHẤM THI, NHẬP ĐIỂM",
             "Bài thi viết được chấm hai vòng độc lập bởi hai giảng viên.",
             "Giảng viên nhập điểm lên hệ thống trong vòng 10 ngày làm việc sau buổi thi.",
             "Sinh viên được phúc khảo bài thi trong vòng 5 ngày kể từ ngày công bố điểm.",
             "# V. TỔ CHỨC THỰC HIỆN",
             "Tổ Đào tạo chủ trì, phối hợp với các bộ môn triển khai Kế hoạch này./.")),
        signer=("KT. HIỆU TRƯỞNG", "PHÓ HIỆU TRƯỞNG"),
        receivers=("- Các khoa, bộ môn;", "- Lưu: VT, ĐT."), assign=Assign("ĐT", "chuyenviendt")),
    Doc("03-cong-tac-phi.pdf", "HD", "31/HD-ĐHM", date(2026, 9, 28),
        "Hướng dẫn thanh toán công tác phí trong nước năm 2026",
        "HƯỚNG DẪN", "Thanh toán công tác phí trong nước năm 2026",
        pages=(
            ("Căn cứ Quy chế chi tiêu nội bộ của Trường, Phòng Kế hoạch – Tài chính hướng dẫn như sau:",
             "# 1. Phụ cấp lưu trú",
             "Phụ cấp lưu trú khi đi công tác ngoài tỉnh là 200.000 đồng/ngày.",
             "Đi công tác trong tỉnh, cách Trường từ 15 km trở lên, được hưởng 100.000 đồng/ngày.",
             "Ngày đi và ngày về được tính là ngày công tác nếu có giấy đi đường hợp lệ."),
            ("# 2. Thuê phòng nghỉ",
             "Tiền thuê phòng nghỉ được thanh toán tối đa 1.200.000 đồng/ngày/phòng.",
             "Người đi công tác phải có hóa đơn hợp pháp của khách sạn, nhà nghỉ.",
             "# 3. Vé tàu, xe, máy bay",
             "Vé máy bay hạng phổ thông chỉ thanh toán cho chuyến đi từ 300 km trở lên.",
             "Đi xe của Trường thì không thanh toán tiền vé."),
            ("# 4. Hồ sơ thanh toán",
             "Hồ sơ gồm giấy đi đường có xác nhận của nơi đến, vé và hóa đơn.",
             "Hồ sơ thanh toán gửi Phòng Kế hoạch – Tài chính trong vòng 15 ngày sau chuyến công tác.",
             "Chứng từ nộp muộn được thanh toán vào tháng kế tiếp.",
             "Hướng dẫn này áp dụng từ ngày 01/10/2026./.")),
        signer=("KT. HIỆU TRƯỞNG", "PHÓ HIỆU TRƯỞNG"),
        receivers=("- Các đơn vị trong Trường;", "- Lưu: VT, KHTC.")),
    Doc("04-phong-may.pdf", "QC", "08/QC-ĐHM", date(2026, 10, 5),
        "Quy chế sử dụng phòng máy tính thực hành", "QUY CHẾ", "Sử dụng phòng máy tính thực hành",
        pages=(
            ("# Điều 1. Phạm vi áp dụng",
             "Quy chế này áp dụng cho các phòng máy tính thực hành do Bộ môn Kỹ thuật phần mềm phụ trách.",
             "# Điều 2. Thời gian mở cửa",
             "Phòng máy mở cửa từ 7 giờ 00 đến 21 giờ 00, từ thứ Hai đến thứ Bảy.",
             "Ngày Chủ nhật và ngày lễ, phòng máy chỉ mở khi có lịch thi hoặc lịch học bù.",
             "# Điều 3. Trách nhiệm của người sử dụng",
             "Người sử dụng đăng nhập bằng tài khoản cá nhân, giữ gìn thiết bị và vệ sinh chung."),
            ("# Điều 4. Xử lý vi phạm",
             "Tự ý cài đặt phần mềm bị đình chỉ sử dụng phòng máy 30 ngày.",
             "Làm hư hỏng thiết bị phải bồi thường theo giá trị còn lại của thiết bị.",
             "Mọi vi phạm được lập biên bản và báo cáo Trưởng bộ môn.",
             "# Điều 5. Hiệu lực",
             "Quy chế có hiệu lực từ ngày 01/11/2026./.")),
        signer=("TRƯỞNG BỘ MÔN",), receivers=("- Giảng viên, sinh viên;", "- Lưu: BM KTPM."),
        assign=Assign("KTPM", "giangvienktpm")),
    Doc("05-nghi-tet.pdf", "TB", "47/TB-ĐHM", date(2026, 10, 12),
        "Thông báo lịch nghỉ Tết Nguyên đán Đinh Mùi năm 2027",
        "THÔNG BÁO", "Lịch nghỉ Tết Nguyên đán Đinh Mùi năm 2027",
        to=("- Các đơn vị trong Trường;", "- Giảng viên, sinh viên."),
        pages=(
            ("Nhà trường thông báo lịch nghỉ Tết Nguyên đán Đinh Mùi năm 2027 như sau:",
             "# 1. Thời gian nghỉ",
             "Cán bộ, giảng viên nghỉ Tết từ thứ Năm ngày 04/02/2027 đến hết Chủ nhật ngày 14/02/2027.",
             "Sinh viên nghỉ học từ ngày 01/02/2027 đến hết ngày 21/02/2027.",
             "Các đơn vị hoàn thành công việc trước kỳ nghỉ, tắt điện và niêm phong phòng làm việc."),
            ("# 2. Trực cơ quan",
             "Trong thời gian nghỉ Tết, trực cơ quan đặt tại phòng 105 nhà C5.",
             "Lịch trực từng ngày do Phòng Tổ chức – Hành chính phân công.",
             "Cán bộ trực ghi sổ trực, báo cáo ngay sự cố về an ninh, cháy nổ.",
             "Nhà trường đề nghị các đơn vị phổ biến thông báo này tới toàn thể cán bộ, sinh viên./.")),
        signer=("TL. HIỆU TRƯỞNG", "TRƯỞNG PHÒNG TỔ CHỨC – HÀNH CHÍNH"), receivers=("- Như trên;", "- Lưu: VT, TCHC.")),
    Doc("06-han-che.pdf", "PA", "53/PA-ĐHM", date(2026, 10, 14),
        "Phương án sắp xếp tổ chức bộ máy khối hành chính năm 2027",
        "PHƯƠNG ÁN", "Sắp xếp tổ chức bộ máy khối hành chính năm 2027",
        pages=(
            ("Thực hiện chủ trương tinh gọn bộ máy, Nhà trường xây dựng phương án sắp xếp khối hành chính như sau:",
             "Theo phương án XANH LAM, Phòng Tổ chức – Hành chính và Phòng Quản trị thiết bị hợp nhất từ ngày "
             "01/03/2027.",
             "Viên chức của hai phòng được giữ nguyên vị trí việc làm trong thời gian chuyển tiếp.",
             "Phương án này lưu hành nội bộ, không phổ biến khi chưa có quyết định của Hội đồng trường./."),),
        signer=("HIỆU TRƯỞNG",), receivers=("- Ban Giám hiệu;", "- Lưu: VT."), restricted=True),
)

# Văn bản mẫu của make seed (scripts/seed_documents.py) mà bộ câu hỏi dùng: câu trả lời nguyên văn trong tệp PDF in lúc
# seed (1 trang). Văn bản đi lấy số ký hiệu lúc phát hành, không biết trước: nhận theo trích yếu.
SEED_EVIDENCE = {
    "88/CTSV": "Căn cứ Quy định về học bổng khuyến khích học tập của Trường, Phòng Công tác sinh viên đề nghị Khoa xét "
               "chọn sinh viên có điểm trung bình chung học kỳ từ 3,2 trở lên và điểm rèn luyện đạt loại Tốt.",
    "131/ĐT-ĐH": "Để chuẩn bị xét công nhận tốt nghiệp đợt tháng 12 năm 2026, Phòng Đào tạo đề nghị Khoa rà soát danh "
                 "sách sinh viên dự kiến tốt nghiệp, đối chiếu đủ các điều kiện: hoàn thành chương trình đào tạo; đạt "
                 "chuẩn đầu ra ngoại ngữ (chứng chỉ B1 theo Khung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam); có "
                 "chứng chỉ giáo dục quốc phòng – an ninh và chứng chỉ giáo dục thể chất.",
    # công văn đi không bị màn nóng → lạnh nộp lưu (thông báo họp giao ban thì có: tệp chuyển ra kho lạnh, chỉ còn
    # đoạn "trích yếu")
    "Về việc cử giảng viên tham dự hội thảo chuyển đổi số trong giáo dục đại học":
        "Phúc đáp Công văn số 47/KHCN của Phòng Khoa học và Hợp tác quốc tế, Khoa Công nghệ thông tin cử giảng viên "
        "Vũ Thị Mai, Bộ môn Kỹ thuật phần mềm, tham dự hội thảo và trình bày tham luận về ứng dụng nguồn mở trong "
        "quản lý văn bản.",
}


def _at(symbol: str, page: int) -> tuple[dict, ...]:
    return ({"symbol": symbol, "page": page},)


TASKS = ({"data": "tasks"},)


def _count(directions: tuple[str, ...], start: str | None = None, end: str | None = None,
           type_code: str | None = None) -> tuple[dict, ...]:
    """Đáp án câu đếm văn bản: hướng, khoảng ngày nửa mở [start, end), loại — demo.py đếm thẳng theo đúng bộ lọc này."""
    return ({"data": "documents", "directions": list(directions), "from": start, "to": end, "type_code": type_code},)


def _guide(path: str) -> tuple[dict, ...]:
    return ({"guide": path},)


QUESTIONS = (
    # Văn bản mẫu nhiều trang: mỗi câu một trang khác nhau, người hỏi ở nhiều vai trò
    Question("q01", "vanthu", "Phải đăng ký tối thiểu bao nhiêu tín chỉ để được xét học bổng?", _at("15/QĐ-ĐHM", 1),
             ("15 tín chỉ",), evidence="Sinh viên được xét học bổng khi đăng ký tối thiểu 15 tín chỉ trong học kỳ."),
    Question("q02", "chuyenviendt", "Mức học bổng loại Xuất sắc là bao nhiêu?", _at("15/QĐ-ĐHM", 2), ("120%",),
             evidence="Học bổng loại Xuất sắc bằng 120% mức học phí của học kỳ."),
    Question("q03", "vanthu", "Học bổng được chuyển khoản trong bao lâu?", _at("15/QĐ-ĐHM", 3), ("20 ngày",),
             evidence="Học bổng được chuyển khoản cho sinh viên trong vòng 20 ngày kể từ ngày ký quyết định "
                      "công nhận."),
    Question("q04", "totruongdt", "Kỳ thi kết thúc học phần học kỳ I diễn ra khi nào?", _at("22/KH-ĐHM", 1),
             ("04/01/2027",),
             evidence="Kỳ thi kết thúc học phần học kỳ I diễn ra từ ngày 04/01/2027 đến ngày 16/01/2027."),
    Question("q05", "totruongdt", "Hạn nộp đề thi và đáp án là ngày nào?", _at("22/KH-ĐHM", 2), ("14/12/2026",),
             evidence="Hạn nộp đề thi và đáp án về Tổ Đào tạo là ngày 14/12/2026."),
    Question("q06", "vanthu", "Nhập điểm lên hệ thống trong bao nhiêu ngày?", _at("22/KH-ĐHM", 3),
             ("10 ngày làm việc",),
             evidence="Giảng viên nhập điểm lên hệ thống trong vòng 10 ngày làm việc sau buổi thi."),
    Question("q07", "truongkhoa", "Phụ cấp lưu trú khi đi công tác là bao nhiêu?", _at("31/HD-ĐHM", 1),
             ("200.000 đồng",),
             evidence="Phụ cấp lưu trú khi đi công tác ngoài tỉnh là 200.000 đồng/ngày."),
    Question("q08", "truongkhoa", "Tiền thuê phòng nghỉ được thanh toán tối đa bao nhiêu?", _at("31/HD-ĐHM", 2),
             ("1.200.000 đồng",), evidence="Tiền thuê phòng nghỉ được thanh toán tối đa 1.200.000 đồng/ngày/phòng."),
    Question("q09", "vanthu", "Hồ sơ thanh toán gửi trong bao lâu?", _at("31/HD-ĐHM", 3), ("15 ngày",),
             evidence="Hồ sơ thanh toán gửi Phòng Kế hoạch – Tài chính trong vòng 15 ngày sau chuyến công tác."),
    # Câu quyền (dương): giảng viên KTPM chỉ được xem văn bản giao cho mình
    Question("q10", "giangvienktpm", "Phòng máy mở cửa từ mấy giờ?", _at("08/QC-ĐHM", 1), ("7 giờ 00",),
             evidence="Phòng máy mở cửa từ 7 giờ 00 đến 21 giờ 00, từ thứ Hai đến thứ Bảy."),
    Question("q11", "truongbmktpm", "Tự ý cài đặt phần mềm bị xử lý thế nào?", _at("08/QC-ĐHM", 2), ("30 ngày",),
             evidence="Tự ý cài đặt phần mềm bị đình chỉ sử dụng phòng máy 30 ngày."),
    Question("q12", "truongkhoa", "Cán bộ nghỉ Tết từ ngày nào?", _at("47/TB-ĐHM", 1), ("04/02/2027",),
             evidence="Cán bộ, giảng viên nghỉ Tết từ thứ Năm ngày 04/02/2027 đến hết Chủ nhật ngày 14/02/2027."),
    Question("q13", "vanthu", "Trực cơ quan dịp nghỉ Tết ở đâu?", _at("47/TB-ĐHM", 2), ("nhà C5",),
             evidence="Trong thời gian nghỉ Tết, trực cơ quan đặt tại phòng 105 nhà C5."),
    # Văn bản mẫu của make seed (một trang): công văn đến 88/CTSV, 131/ĐT-ĐH, thông báo đi đã phát hành
    Question("q14", "vanthu", "Điều kiện xét học bổng khuyến khích học tập là gì?", _at("88/CTSV", 1), ("3,2",),
             evidence=SEED_EVIDENCE["88/CTSV"]),
    Question("q15", "vanthu", "Chuẩn đầu ra ngoại ngữ xét tốt nghiệp cần chứng chỉ gì?", _at("131/ĐT-ĐH", 1), ("B1",),
             evidence=SEED_EVIDENCE["131/ĐT-ĐH"]),
    Question("q16", "vanthu", "Khoa cử giảng viên nào tham dự hội thảo chuyển đổi số?",
             ({"summary_contains": "cử giảng viên tham dự hội thảo chuyển đổi số", "page": 1},), ("Vũ Thị Mai",),
             evidence=SEED_EVIDENCE["Về việc cử giảng viên tham dự hội thảo chuyển đổi số trong giáo dục đại học"]),
    # Nguồn công khai A (#446): thông tư thật của Bộ GD&ĐT mà make seed nạp từ seed/du-lieu-mo/cong-bao-gddt; trang là
    # trang của tệp PDF bản Công báo (test_hoi_dap kiểm câu bằng chứng trên đúng trang đó)
    Question("c01", "vanthu", "Thí sinh được đăng ký tối đa bao nhiêu nguyện vọng?", _at("06/2026/TT-BGDĐT", 18),
             ("15 nguyện vọng",), evidence="Thí sinh được đăng ký tối đa 15 nguyện vọng vào các chương trình đào tạo, "
                                         "các cơ sở giáo dục đại học khác nhau", loai="cong_khai"),
    Question("c02", "vanthu", "Còn ngành đào tạo giáo viên thì sao?", _at("06/2026/TT-BGDĐT", 18), ("01 đến 05",),
             evidence="Các chương trình đào tạo giáo viên chỉ xét tuyển thí sinh đăng ký ở các nguyện vọng có thứ tự "
                      "từ 01 đến 05", loai="noi_tiep",
             previous="Thí sinh được đăng ký tối đa bao nhiêu nguyện vọng?"),
    Question("c03", "vanthu", "Thông tư số 10/2020/TT-BGDĐT hết hiệu lực từ ngày nào?", _at("58/2026/TT-BGDĐT", 5),
             ("01 tháng 11 năm 2026",), evidence="hết hiệu lực kể từ ngày 01 tháng 11 năm 2026", loai="cong_khai"),
    # Câu âm: không văn bản nào trả lời được; nội dung văn bản hạn chế (không bao giờ vào chỉ mục)
    Question("q17", "vanthu", "Thủ tục cấp hộ chiếu công vụ?", "none"),
    Question("q18", "vanthu", "Phương án XANH LAM là gì?", "none", forbid=("53/PA-ĐHM",)),
    # Câu quyền (cấm): công văn học bổng giao Tổ Đào tạo, giảng viên Bộ môn KTPM không được xem
    Question("q19", "giangvienktpm", "Điều kiện xét học bổng khuyến khích học tập là gì?", "none",
             forbid=("15/QĐ-ĐHM", "88/CTSV")),
    # Câu nối tiếp (#423): ghép với câu trước rồi tìm như câu văn bản; câu trả lời khác câu trả lời của câu trước
    Question("n01", "chuyenviendt", "Thế còn loại Giỏi?", _at("15/QĐ-ĐHM", 2), ("110%",),
             evidence="Học bổng loại Giỏi bằng 110% mức học phí của học kỳ.", loai="noi_tiep",
             previous="Mức học bổng loại Xuất sắc là bao nhiêu?"),
    Question("n02", "chuyenviendt", "Còn loại Khá thì sao?", _at("15/QĐ-ĐHM", 2), ("100%",),
             evidence="Học bổng loại Khá bằng 100% mức học phí của học kỳ.", loai="noi_tiep",
             previous="Mức học bổng loại Xuất sắc là bao nhiêu?"),
    Question("n03", "truongkhoa", "Còn vé máy bay thì sao?", _at("31/HD-ĐHM", 2), ("300 km",),
             evidence="Vé máy bay hạng phổ thông chỉ thanh toán cho chuyến đi từ 300 km trở lên.", loai="noi_tiep",
             previous="Tiền thuê phòng nghỉ được thanh toán tối đa bao nhiêu?"),
    Question("n04", "giangvienktpm", "Còn ngày Chủ nhật thì sao?", _at("08/QC-ĐHM", 1), ("lịch học bù",),
             evidence="Ngày Chủ nhật và ngày lễ, phòng máy chỉ mở khi có lịch thi hoặc lịch học bù.",
             loai="noi_tiep", previous="Phòng máy mở cửa từ mấy giờ?"),
    Question("n05", "vanthu", "Còn lịch trực từng ngày thì sao?", _at("47/TB-ĐHM", 2),
             ("Phòng Tổ chức – Hành chính",), evidence="Lịch trực từng ngày do Phòng Tổ chức – Hành chính phân công.",
             loai="noi_tiep", previous="Trực cơ quan dịp nghỉ Tết ở đâu?"),
    # Câu về chính trợ lý: đáp án là mục của tệp Giới thiệu trợ lý, không tìm trong kho, không gọi mô hình
    Question("g01", "vanthu", "Bạn làm được gì?", _guide(f"{INTRO}/vi.md#lam-duoc-gi"), loai="gioi_thieu"),
    Question("g02", "giangvienktpm", "Xin chào", _guide(f"{INTRO}/vi.md#gioi-thieu"), loai="gioi_thieu"),
    Question("g03", "truongkhoa", "Bạn là ai?", _guide(f"{INTRO}/vi.md#gioi-thieu"), loai="gioi_thieu"),
    Question("g04", "chuyenviendt", "Trợ lý dùng mô hình nào?", _guide(f"{INTRO}/vi.md#mo-hinh"), loai="gioi_thieu"),
    Question("g05", "vanthu", "Tôi nên hỏi bạn thế nào?", _guide(f"{INTRO}/vi.md#cach-hoi"), loai="gioi_thieu"),
    Question("g06", "vanthu", "What can you do?", _guide(f"{INTRO}/en.md#lam-duoc-gi"), loai="gioi_thieu"),
    # Cách dùng Signet: đáp án là mục của hướng dẫn sử dụng (docs/huong-dan)
    Question("h01", "giangvienktpm", "Nộp đơn nghỉ phép ở đâu?", _guide("docs/huong-dan/viec-chung.md#đơn-nghỉ-phép"),
             loai="huong_dan"),
    Question("h02", "chuyenviendt", "Làm thế nào để soạn văn bản đi?",
             _guide("docs/huong-dan/chuyen-vien.md#soạn-và-trình-văn-bản-đi"), loai="huong_dan"),
    Question("h03", "truongkhoa", "Làm thế nào để ký số văn bản đi?",
             _guide("docs/huong-dan/lanh-dao-don-vi.md#ký-duyệt-văn-bản-đi"), loai="huong_dan"),
    Question("h04", "truongkhoa", "Xem sổ kiểm toán ở đâu?", _guide("docs/huong-dan/quan-tri.md#sổ-kiểm-toán"),
             loai="huong_dan"),
    Question("h05", "vanthu", "Đổi mật khẩu ở đâu?", _guide("docs/huong-dan/README.md#đăng-nhập"), loai="huong_dan"),
    # Ngoài phạm vi: câu cố định nói trợ lý làm được gì, không nguồn, không tìm
    Question("o01", "vanthu", "Thời tiết Hà Nội hôm nay thế nào?", "none", loai="ngoai_pham_vi"),
    Question("o02", "giangvienktpm", "Giá vàng hôm nay bao nhiêu?", "none", loai="ngoai_pham_vi"),
    Question("o03", "truongkhoa", "Tỷ giá đô la hôm nay là bao nhiêu?", "none", loai="ngoai_pham_vi"),
    Question("o04", "chuyenviendt", "Kết quả bóng đá tối qua thế nào?", "none", loai="ngoai_pham_vi"),
    Question("o05", "vanthu", "Viết giúp tôi một bài thơ", "none", loai="ngoai_pham_vi"),
    Question("o06", "vanthu", "Write me a poem", "none", loai="ngoai_pham_vi"),
    # Việc của người hỏi (#441): số việc trong Hộp việc phải bằng myTasks đếm thẳng qua GraphQL bằng token người hỏi
    Question("v01", "vanthu", "Việc nào của tôi sắp quá hạn?", TASKS, loai="viec_cua_toi"),
    Question("v02", "truongkhoa", "Tôi có bao nhiêu việc quá hạn?", TASKS, loai="viec_cua_toi"),
    Question("v03", "giangvienktpm", "Tôi được giao những việc gì?", TASKS, loai="viec_cua_toi"),
    Question("v04", "totruongdt", "Có việc nào của mình đến hạn hôm nay không?", TASKS, loai="viec_cua_toi"),
    Question("v05", "chuyenviendt", "Which of my tasks are almost overdue?", TASKS, loai="viec_cua_toi"),
    # Đếm văn bản (#441): số phải bằng office_documents_aggregate với đúng bộ lọc ghi ở đây, bằng token người hỏi.
    # Mốc thời gian ghi rõ tháng, năm để đáp án không đổi theo ngày đo
    Question("d01", "vanthu", "Có bao nhiêu văn bản đến trong tháng 10/2026?",
             _count(("in",), "2026-10-01", "2026-11-01"), loai="dem_van_ban"),
    Question("d02", "truongkhoa", "Thống kê số văn bản đi năm 2026",
             _count(("out",), "2026-01-01", "2027-01-01"), loai="dem_van_ban"),
    Question("d03", "vanthu", "Có bao nhiêu quyết định đến trong năm 2026?",
             _count(("in",), "2026-01-01", "2027-01-01", "QĐ"), loai="dem_van_ban"),
    Question("d04", "giangvienktpm", "Có bao nhiêu văn bản?", _count(("in", "out")), loai="dem_van_ban"),
    Question("d05", "chuyenviendt", "How many incoming documents arrived in September 2026?",
             _count(("in",), "2026-09-01", "2026-10-01"), loai="dem_van_ban"),
)


def questions_json() -> dict:
    """cau-hoi.json: văn bản (để nạp kho) và câu hỏi kèm đáp án — demo.py hoi-dap, do-hoi-dap đọc tệp này."""
    docs = []
    for d in DOCS:
        assign = None if d.assign is None else {"lead": d.assign.lead, "handler": d.assign.handler}
        docs.append({"file": d.file, "symbol": d.symbol, "type_code": d.type_code, "issuer_name": ISSUER,
                     "issued_on": d.issued.isoformat(), "summary": d.summary, "pages": len(d.pages),
                     "restricted": d.restricted, "assign": assign})
    questions = []
    for q in QUESTIONS:
        item: dict = {"id": q.id, "user": q.user, "loai": q.loai, "route": ROUTES[q.loai], "question": q.question,
                      "expect": q.expect if isinstance(q.expect, str) else list(q.expect)}
        if q.previous:
            item["previous"] = q.previous
        if q.keywords:
            item["keywords"] = list(q.keywords)
        if q.forbid:
            item["forbid"] = list(q.forbid)
        if q.evidence:
            item["evidence"] = q.evidence
        questions.append(item)
    return {"version": 1, "note": NOTE, "documents": docs, "questions": questions}


def date_line(d: date) -> str:
    """"Hà Nội, ngày 05 tháng 3 năm 2026": ngày dưới 10, tháng 1, 2 có số 0 ở trước (NĐ 30, Phụ lục I)."""
    month = f"{d.month:02d}" if d.month <= 2 else str(d.month)
    return f"{PLACE}, ngày {d.day:02d} tháng {month} năm {d.year}"


# ---------------------------------------------------------------------------------------------------------------
# PDF có lớp chữ (WeasyPrint): thể thức như van_ban_mau.py; số trang ở giữa đầu trang từ trang 2 (NĐ 30), chân trang
# ghi rõ văn bản giả lập; mỗi trang sau bắt đầu bằng ngắt trang tường minh

CSS = """
@page { size: A4; margin: 20mm 15mm 20mm 30mm;
  @top-center { content: counter(page); font-family: "Liberation Serif", serif; font-size: 13pt; }
  @bottom-center { content: "%s"; font-family: "Liberation Serif", serif; font-size: 9pt; color: #555; } }
@page :first { @top-center { content: none; } }
body { font-family: "Liberation Serif", serif; font-size: 13pt; line-height: 1.3; color: #000; }
table { width: 100%%; border-collapse: collapse; }
td { vertical-align: top; padding: 0; }
table.head td { text-align: center; font-size: 12.5pt; }
.b { font-weight: bold; } .i { font-style: italic; }
.rule { width: 34%%; margin: 1pt auto 5pt; border-top: 0.8pt solid #000; }
h1 { font-size: 14pt; text-align: center; margin: 18pt 0 0; }
.ty { text-align: center; font-weight: bold; margin: 0 10%%; }
.auth { text-align: center; font-weight: bold; margin-top: 12pt; }
.to-list { margin: 14pt 0 10pt 22%%; }
.gap { height: 10pt; }
.page { break-before: page; }
p { text-indent: 10mm; text-align: justify; margin: 0 0 5pt; }
p.h { text-indent: 0; font-weight: bold; margin-top: 6pt; }
p.c { text-indent: 0; text-align: center; font-weight: bold; }
table.foot { margin-top: 14pt; break-inside: avoid; }
.recv { font-size: 11pt; } .recv .h { font-weight: bold; font-style: italic; font-size: 12pt; }
.sign { text-align: center; } .sgap { height: 20mm; }
""" % NOTE


def doc_html(d: Doc) -> str:
    import html

    e = html.escape
    left = f'<div class="b">{e(ISSUER.upper())}</div><div class="rule"></div><div>Số: {e(d.symbol)}</div>'
    right = (f'<div class="b">{MOTTO}</div><div class="b">{MOTTO2}</div><div class="rule"></div>'
             f'<div class="i">{e(date_line(d.issued))}</div>')
    head = (f'<table class="head"><tr><td style="width: 42%">{left}</td><td>{right}</td></tr></table>'
            f'<h1>{e(d.title)}</h1><div class="ty">{e(d.trich_yeu)}</div><div class="rule"></div>')
    if d.authority:
        head += f'<div class="auth">{e(d.authority)}</div>'
    if d.to:
        head += '<div class="to-list"><div>Kính gửi:</div>' + "".join(f"<div>{e(t)}</div>" for t in d.to) + "</div>"
    else:
        head += '<div class="gap"></div>'

    def para(text: str) -> str:
        if text.startswith("# "):
            return f'<p class="h">{e(text[2:])}</p>'
        if text.startswith("= "):
            return f'<p class="c">{e(text[2:])}</p>'
        return f"<p>{e(text)}</p>"

    pages = []
    for i, paragraphs in enumerate(d.pages):
        body = "".join(para(t) for t in paragraphs)
        pages.append(body if i == 0 else f'<div class="page">{body}</div>')
    recv = '<div class="h">Nơi nhận:</div>' + "".join(f"<div>{e(t)}</div>" for t in d.receivers)
    sign = "".join(f'<div class="b">{e(t)}</div>' for t in d.signer)
    sign += f'<div class="i">(Đã ký)</div><div class="sgap"></div><div class="b">{SIGNER}</div>'
    foot = (f'<table class="foot"><tr><td class="recv" style="width: 50%">{recv}</td>'
            f'<td class="sign">{sign}</td></tr></table>')
    return (f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
            f"{head}{''.join(pages)}{foot}</body></html>")


def render_pdf(d: Doc) -> bytes:
    from weasyprint import HTML

    return HTML(string=doc_html(d)).write_pdf()


# ---------------------------------------------------------------------------------------------------------------
# Kiểm bằng pypdf (có trong môi trường test và image svc-files)


def flat(text: str) -> str:
    """So chữ trên trang: NFC, gộp mọi khoảng trắng (pypdf xuống dòng ở mỗi dòng in), không phân biệt hoa thường."""
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def page_texts(data: bytes) -> list[str]:
    from pypdf import PdfReader

    return [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]


def verify(files: dict[str, bytes]) -> list[str]:
    """Các lỗi của bộ mẫu (rỗng: đạt): số trang, câu trả lời đúng trang và chỉ ở trang đó, từ khóa trên trang, siêu
    dữ liệu chỉ có Producer, không lộ đường dẫn máy, tổng cỡ."""
    from pypdf import PdfReader

    problems: list[str] = []
    texts: dict[str, list[str]] = {}
    for d in DOCS:
        data = files.get(d.file)
        if data is None:
            problems.append(f"{d.file}: không có tệp")
            continue
        reader = PdfReader(io.BytesIO(data))
        texts[d.symbol] = [flat(t) for t in page_texts(data)]
        if len(reader.pages) != len(d.pages):
            problems.append(f"{d.file}: {len(reader.pages)} trang, cần {len(d.pages)} (một phần tràn sang trang sau?)")
        meta = dict(reader.metadata or {})
        if set(meta) != {"/Producer"}:
            problems.append(f"{d.file}: siêu dữ liệu ngoài Producer: {sorted(meta)}")
        problems += [f"{d.file}: có chuỗi {leak!r}" for leak in LEAKS if leak in data]
        if not all(flat(NOTE) in t for t in texts[d.symbol]):
            problems.append(f"{d.file}: thiếu chân trang giả lập ở một trang")
    for q in QUESTIONS:
        if isinstance(q.expect, str):
            continue
        for want in q.expect:
            pages = texts.get(want.get("symbol", ""))
            if pages is None:
                continue                              # văn bản của make seed: kiểm ở scripts/tests/test_hoi_dap.py
            sentence = flat(q.evidence or "")
            where = [(sym, i + 1) for sym, ps in texts.items() for i, t in enumerate(ps) if sentence in t]
            if where != [(want["symbol"], want["page"])]:
                problems.append(f"{q.id}: câu trả lời nằm ở {where or 'không trang nào'}, cần {want['symbol']} "
                                f"tr. {want['page']}")
            page = pages[want["page"] - 1] if want["page"] <= len(pages) else ""
            problems += [f"{q.id}: từ khóa {k!r} không có trên {want['symbol']} tr. {want['page']}"
                         for k in q.keywords if flat(k) not in page or flat(k) not in sentence]
    total = sum(len(v) for v in files.values())
    if total > MAX_TOTAL:
        problems.append(f"tổng {total} byte, quá {MAX_TOTAL}")
    return problems


def render_all() -> dict:
    """Mọi tệp mẫu (base64) và kết quả kiểm — chạy được trong container hoặc trên máy."""
    files = {d.file: render_pdf(d) for d in DOCS}
    return {"files": {k: base64.b64encode(v).decode() for k, v in files.items()}, "problems": verify(files),
            "pages": {d.file: len(d.pages) for d in DOCS}}


# Chạy trong container: stdin là JSON {source, argv}; tệp này chạy như __main__
INSIDE = ("import json, sys; d = json.load(sys.stdin); sys.argv = ['hoi_dap_mau', *d['argv']]; "
          "exec(compile(d['source'], 'hoi_dap_mau.py', 'exec'), {'__name__': '__main__'})")


def run_in_container() -> dict:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from moc_env import compose      # đọc .env khi nhập: chỉ cần ở chế độ container

    payload = {"source": pathlib.Path(__file__).read_text(encoding="utf-8"), "argv": ["--inside"]}
    try:
        out = compose("exec", "-T", "svc-files", "python", "-c", INSIDE, stdin=json.dumps(payload).encode())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Không in được trong container svc-files (make up chưa?): "
                         f"{exc.stderr.decode(errors='replace')[-400:]}") from exc
    return json.loads(out)


def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent if "__file__" in globals() else pathlib.Path.cwd()
    parser = argparse.ArgumentParser(prog="hoi_dap_mau", description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=("auto", "local", "container"), default="auto",
                        help="local: WeasyPrint trên máy; container: trong svc-files đang chạy; "
                             "auto: local nếu nhập được weasyprint và pypdf")
    parser.add_argument("--out", default=str(root / "seed" / "hoi-dap"), help="thư mục ghi mẫu")
    parser.add_argument("--check", action="store_true",
                        help="không ghi: in lại, so từng byte với tệp trong --out và kiểm bằng pypdf")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.inside:                  # trong container: in kết quả ra stdout cho phía máy chủ
        sys.stdout.write(json.dumps(render_all()))
        return 0
    mode = args.mode
    if mode == "auto":
        try:
            import pypdf  # noqa: F401
            import weasyprint  # noqa: F401
            mode = "local"
        except (ImportError, OSError):
            mode = "container"
    result = render_all() if mode == "local" else run_in_container()
    files = {name: base64.b64decode(data) for name, data in result["files"].items()}
    labels = json.dumps(questions_json(), ensure_ascii=False, indent=2) + "\n"
    out = pathlib.Path(args.out)
    problems = list(result["problems"])

    if args.check:
        for name, data in files.items():
            path = out / name
            if not path.is_file() or path.read_bytes() != data:
                problems.append(f"{name}: khác tệp trong {out} — chạy lại không ra đúng các byte đã commit "
                                f"(khác phiên bản WeasyPrint, phông?) hoặc mẫu đã sửa mà chưa in lại")
        if not (out / "cau-hoi.json").is_file() or (out / "cau-hoi.json").read_text(encoding="utf-8") != labels:
            problems.append("cau-hoi.json: khác bản sinh từ hoi_dap_mau.py — chạy lại không kèm --check")
    else:
        out.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (out / name).write_bytes(data)
        (out / "cau-hoi.json").write_text(labels, encoding="utf-8")
    total = sum(len(v) for v in files.values())
    for name, data in files.items():
        print(f"  {name:22s} {result['pages'][name]} trang {len(data) / 1024:7.1f} KB")
    print(f"  {'cau-hoi.json':22s} {len(DOCS)} văn bản, {len(QUESTIONS)} câu hỏi")
    for problem in problems:
        print(f"✗ {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"{'Khớp' if args.check else 'Tổng'} {total / 1024:.0f} KB ({mode}) — số trang, câu trả lời đúng trang, "
          f"siêu dữ liệu đã kiểm bằng pypdf → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
