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

"""Văn bản đến mẫu để thử và đo tác tử đọc văn bản (F4.1): 15 PDF có lớp chữ + 7 ảnh/bản scan, kèm nhãn đúng.

Mọi văn bản đều giả lập: cơ quan hư cấu có chữ "Mẫu", người ký "Nguyễn Văn A" (văn bản liên tịch thêm "Nguyễn Văn B"),
chân trang "Văn bản giả lập để chạy thử Mộc, không phải văn bản thật"; không có dữ liệu cá nhân thật. Đầu ra (commit
vào kho mã):

    seed/van-ban-den/01-cong-van.pdf … 10-cong-van-tphcm.pdf     PDF có lớp chữ (WeasyPrint, thể thức NĐ 30)
    seed/van-ban-den/11-…jpg, 12-…jpg, 13-…pdf, 14-…png           "bản scan" của 01, 02, 03, 06
    seed/van-ban-den/15-huong-dan.pdf … 19-cong-van-benh-vien.pdf PDF có lớp chữ: hướng dẫn hai trang, nghị quyết
                                                                  HĐND, thông báo kết luận, kế hoạch liên tịch, công
                                                                  văn của bệnh viện
    seed/van-ban-den/20-…jpg, 21-…jpg, 22-…pdf                    chỉ có bản ảnh: công điện chụp bằng điện thoại,
                                                                  công văn ngân hàng scan nền xám, quyết định scan
                                                                  3 trang
    seed/van-ban-den/nhan.json                                    nhãn đúng của từng tệp (đo độ chính xác)
    services/svc-files/tests/fixtures/ocr/<tệp>.tsv              TSV của Tesseract cho 7 bản scan (trang 1; nếu có
                                                                  tesseract)

Mẫu 15–22 thêm sau (đo "Hoàn thành khi" của Phase 4 trên ít nhất 20 văn bản) và khó hơn: ký hiệu có năm, ba đoạn, số
có chữ cái phụ; ngày viết không theo NĐ 30 ("ngày 5 tháng 03", "ngày 12/10/2026"); địa danh khác; tên cơ quan ba dòng
(chủ quản viết hai dòng), văn bản liên tịch hai cơ quan, cơ quan ngoài ngành giáo dục; tên loại "KẾ HOẠCH LIÊN TỊCH".
Thêm mẫu thì thêm ở cuối, không sửa nội dung mẫu cũ (mỗi bản scan một hạt giống riêng; nhan.json xếp theo tên tệp
nên nhãn cũ đứng nguyên chỗ). Tệp đã commit in bằng make van-ban-mau (image svc-files): chạy lại trong cùng image ra
đúng từng byte. Byte của PDF phụ thuộc bản phông và WeasyPrint: in bằng --mode local trên máy khác thì phông nhúng
khác byte, có chỗ ngắt dòng khác (mẫu 04) — số đo phải lấy trên bản in trong image.

Ảnh "scan" KHÔNG chụp từ PDF (svc-files không có bộ dựng ảnh từ PDF: không poppler, không pdfium) mà vẽ lại cùng nội
dung bằng Pillow (phông Liberation Serif), rồi xoay 0,5–1,5°, làm mờ nhẹ, thêm hạt nhiễu, nén JPEG — hạt giống cố định
nên chạy lại ra đúng các byte cũ (cùng phiên bản Pillow, cùng phông). Bản ảnh của 20–22 không có PDF cùng nội dung
(``source`` null trong nhan.json): 20 là tờ giấy chụp nghiêng 3,2° trên mặt bàn, hơi phối cảnh, sáng không đều; 21 nền
xám, mực nhạt, tối dần về mép gáy; 22 là PDF máy scan 150 dpi, mỗi trang một ảnh, số ký hiệu ở trang 1.

Cách chạy:

    make van-ban-mau
        = python3 scripts/van_ban_mau.py --mode container: in trong container svc-files đang chạy (phông, WeasyPrint,
          tesseract của image), ghi cả TSV. Cần make up.
    python3 scripts/van_ban_mau.py --mode container --tsv-only
        chỉ ghi TSV Tesseract của 7 bản scan đang có trong seed/van-ban-den, không in lại mẫu (giữ nguyên các byte
        đã commit) — dùng khi image svc-files vừa có tesseract.
    cd services/svc-files && uv run --no-project --with-requirements requirements-dev.txt \\
        python ../../scripts/van_ban_mau.py --mode local
        in ngay trên máy bằng WeasyPrint + Pillow của môi trường test svc-files; máy không có tesseract thì bỏ qua TSV.

Chỉ dùng thư viện chuẩn ở phía máy chủ; khi chạy trong container, chính tệp này (kèm ảnh cần OCR) được gửi qua stdin
cho ``python -c`` (``--inside``), kết quả về lại qua stdout.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime

# tên cũ của sản phẩm: PDF mẫu đã commit và số đo đọc văn bản dựng từ chuỗi này — đổi là in lại, đo lại
NOTE = "Văn bản giả lập để chạy thử Mộc, không phải văn bản thật."
MOTTO = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
MOTTO2 = "Độc lập - Tự do - Hạnh phúc"
SIGNER = "Nguyễn Văn A"
SIGNER2 = "Nguyễn Văn B"                          # người ký thứ hai của văn bản liên tịch
HEADINGS = ("QUYẾT ĐỊNH:", "QUYẾT NGHỊ:")          # dòng giữa trang, in đậm trước các điều
MAX_TOTAL = 3 * 1024 * 1024
FIXED_TIME = datetime(2026, 10, 1, 8, 0, 0)       # mốc thời gian trong siêu dữ liệu PDF của Pillow: chạy lại ra cùng byte


@dataclass(frozen=True)
class Mau:
    """Một văn bản đến mẫu. Chữ in hoa như trên văn bản; nhãn (``*_label``) là điều văn thư nhập."""

    file: str
    type_code: str | None             # nhãn; None: loại chưa có trong danh mục (Thông tư)
    issuer: tuple[str, ...]           # dòng tên cơ quan (in hoa), trên cùng là cơ quan chủ quản nếu có
    issuer_label: str
    symbol: str
    place: str
    issued: date
    summary_label: str
    title: str | None = None          # tên loại in hoa giữa trang; None: công văn
    trich_yeu: str | None = None      # dòng dưới tên loại
    vv: str | None = None             # công văn: phần sau "V/v"
    authority: str | None = None      # quyết định: dòng thẩm quyền ban hành
    to: tuple[str, ...] = ()          # nơi nhận sau "Kính gửi"
    body: tuple[str, ...] = ()
    signer: tuple[str, ...] = ("GIÁM ĐỐC",)
    receivers: tuple[str, ...] = ("- Như trên;", "- Lưu: VT.")
    urgency: str = "normal"
    stamp: str | None = None          # dấu độ khẩn in trên văn bản
    # thêm cho mẫu 15–22; mặc định giữ đúng cách in của mẫu cũ
    date_text: str | None = None      # dòng địa danh, ngày in nguyên văn (cách viết khác NĐ 30); None: date_line()
    head_bold: int = 0                # số dòng cuối của tên cơ quan in đậm; 0: như cũ
    signer2: tuple[str, ...] = ()     # văn bản liên tịch: khối chữ ký thứ hai, cột trái (chỉ PDF có lớp chữ)
    annex: tuple[str, ...] = ()       # phụ lục, sang trang mới (chỉ bản ảnh): "= " giữa trang đậm, "~ " giữa trang
    #                                   nghiêng, "# " đề mục đậm, còn lại là đoạn văn
    numbered: bool = False            # nhiều trang: số trang giữa lề trên, không hiện ở trang 1 (NĐ 30; phụ lục
    #                                   đánh số riêng)


@dataclass(frozen=True)
class Scan:
    file: str
    source: str | None                # tệp PDF có cùng nội dung; None: chỉ có bản ảnh (nội dung ở ``content``)
    dpi: int
    fmt: str                          # jpg | png | pdf
    angle: float
    blur: float
    grain: float                      # tỉ lệ trộn hạt nhiễu
    color: bool = False
    quality: int = 70
    seed: int = 7
    extra: dict = field(default_factory=dict)
    content: Mau | None = None        # nội dung khi không có PDF cùng nội dung
    tone: tuple[int, int] | None = None   # (mực, nền) của bản scan độ tương phản thấp, tối dần về mép gáy
    photo: bool = False               # ảnh chụp điện thoại: giấy nghiêng ``angle`` trên mặt bàn, sáng không đều

    def mau(self, by_file: dict[str, Mau]) -> Mau:
        return self.content if self.content is not None else by_file[str(self.source)]


SAMPLES = (
    Mau("01-cong-van.pdf", "CV", ("TRƯỜNG ĐẠI HỌC MẪU", "PHÒNG ĐÀO TẠO"), "Phòng Đào tạo", "131/ĐT-ĐHM", "Hà Nội",
        date(2026, 10, 15),
        "Về việc rà soát danh sách sinh viên đủ điều kiện xét tốt nghiệp đợt tháng 12 năm 2026",
        vv="rà soát danh sách sinh viên đủ điều kiện xét tốt nghiệp đợt tháng 12 năm 2026",
        to=("Khoa Công nghệ thông tin",),
        body=("Để chuẩn bị xét công nhận tốt nghiệp đợt tháng 12 năm 2026, Phòng Đào tạo đề nghị Khoa rà soát danh sách "
              "sinh viên dự kiến tốt nghiệp, đối chiếu đủ các điều kiện: hoàn thành chương trình đào tạo; đạt chuẩn đầu "
              "ra ngoại ngữ; có chứng chỉ giáo dục quốc phòng - an ninh và giáo dục thể chất.",
              "Danh sách gửi về Phòng Đào tạo trước ngày 10/11/2026, kèm bản chụp chứng chỉ của các trường hợp còn "
              "thiếu minh chứng.", "Trân trọng./."),
        signer=("TL. HIỆU TRƯỞNG", "TRƯỞNG PHÒNG ĐÀO TẠO")),
    Mau("02-quyet-dinh.pdf", "QĐ", ("ỦY BAN NHÂN DÂN", "TỈNH MẪU"), "Ủy ban nhân dân tỉnh Mẫu", "123/QĐ-UBND", "Mẫu",
        date(2026, 10, 5),
        "Quyết định về việc ban hành Quy chế quản lý, sử dụng hệ thống văn phòng điện tử tỉnh Mẫu",
        title="QUYẾT ĐỊNH",
        trich_yeu="Về việc ban hành Quy chế quản lý, sử dụng hệ thống văn phòng điện tử tỉnh Mẫu",
        authority="ỦY BAN NHÂN DÂN TỈNH MẪU",
        body=("Căn cứ Luật Tổ chức chính quyền địa phương;",
              "Căn cứ Nghị định số 30/2020/NĐ-CP ngày 05 tháng 3 năm 2020 của Chính phủ về công tác văn thư;",
              "Theo đề nghị của Giám đốc Sở Thông tin và Truyền thông.", "QUYẾT ĐỊNH:",
              "Điều 1. Ban hành kèm theo Quyết định này Quy chế quản lý, sử dụng hệ thống văn phòng điện tử tỉnh Mẫu.",
              "Điều 2. Quyết định này có hiệu lực kể từ ngày ký.",
              "Điều 3. Chánh Văn phòng Ủy ban nhân dân tỉnh, Giám đốc các sở, ban, ngành và Chủ tịch Ủy ban nhân dân "
              "các huyện chịu trách nhiệm thi hành Quyết định này./."),
        signer=("TM. ỦY BAN NHÂN DÂN", "KT. CHỦ TỊCH", "PHÓ CHỦ TỊCH"),
        receivers=("- Như Điều 3;", "- Lưu: VT, VP.")),
    Mau("03-thong-bao.pdf", "TB", ("TRƯỜNG ĐẠI HỌC MẪU",), "Trường Đại học Mẫu", "128/TB-ĐHM", "Hà Nội",
        date(2026, 10, 12), "Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027",
        title="THÔNG BÁO", trich_yeu="Lịch đăng ký học phần học kỳ II năm học 2026–2027",
        to=("- Các khoa đào tạo;", "- Phòng Công tác sinh viên."),
        body=("Nhà trường thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027 như sau:",
              "1. Thời gian đăng ký: từ ngày 02/11/2026 đến hết ngày 15/11/2026.",
              "2. Hình thức: sinh viên đăng ký trực tuyến trên cổng thông tin đào tạo của Trường.",
              "3. Các khoa phổ biến thông báo này tới sinh viên và cố vấn học tập./."),
        signer=("KT. HIỆU TRƯỞNG", "PHÓ HIỆU TRƯỞNG")),
    Mau("04-ke-hoach.pdf", "KH", ("UBND TỈNH MẪU", "SỞ KHOA HỌC VÀ CÔNG NGHỆ"), "Sở Khoa học và Công nghệ tỉnh Mẫu",
        "57/KH-SKHCN", "Mẫu", date(2026, 9, 30),
        "Kế hoạch tổ chức Ngày hội khởi nghiệp đổi mới sáng tạo tỉnh Mẫu năm 2026",
        title="KẾ HOẠCH", trich_yeu="Tổ chức Ngày hội khởi nghiệp đổi mới sáng tạo tỉnh Mẫu năm 2026",
        body=("Thực hiện Chương trình hỗ trợ khởi nghiệp đổi mới sáng tạo giai đoạn 2026–2030, Sở Khoa học và Công "
              "nghệ xây dựng Kế hoạch tổ chức Ngày hội như sau:", "I. MỤC ĐÍCH, YÊU CẦU",
              "Kết nối các nhóm khởi nghiệp với nhà đầu tư, doanh nghiệp và cơ sở giáo dục đại học trên địa bàn tỉnh.",
              "II. THỜI GIAN, ĐỊA ĐIỂM",
              "Từ ngày 20 đến ngày 22 tháng 11 năm 2026 tại Trung tâm Hội nghị tỉnh Mẫu.",
              "III. TỔ CHỨC THỰC HIỆN",
              "Phòng Quản lý khoa học chủ trì, phối hợp với các đơn vị liên quan triển khai Kế hoạch này./."),
        signer=("KT. GIÁM ĐỐC", "PHÓ GIÁM ĐỐC"), receivers=("- UBND tỉnh (để b/c);", "- Lưu: VT, QLKH.")),
    Mau("05-thong-tu.pdf", None, ("BỘ TÀI NGUYÊN MẪU",), "Bộ Tài nguyên Mẫu", "45/2026/TT-BTN", "Hà Nội",
        date(2026, 9, 25), "Thông tư quy định kỹ thuật về số hóa tài liệu lưu trữ",
        title="THÔNG TƯ", trich_yeu="Quy định kỹ thuật về số hóa tài liệu lưu trữ",
        body=("Căn cứ Luật Lưu trữ;", "Theo đề nghị của Cục trưởng Cục Lưu trữ Mẫu;",
              "Bộ trưởng Bộ Tài nguyên Mẫu ban hành Thông tư quy định kỹ thuật về số hóa tài liệu lưu trữ.",
              "Điều 1. Phạm vi điều chỉnh",
              "Thông tư này quy định yêu cầu kỹ thuật đối với việc số hóa tài liệu lưu trữ trên giấy.",
              "Điều 2. Hiệu lực thi hành", "Thông tư này có hiệu lực từ ngày 01 tháng 12 năm 2026./."),
        signer=("KT. BỘ TRƯỞNG", "THỨ TRƯỞNG"), receivers=("- Các cơ quan thuộc Bộ;", "- Lưu: VT, CLT.")),
    Mau("06-giay-moi.pdf", "GM", ("CÔNG TY CỔ PHẦN CÔNG NGHỆ MẪU",), "Công ty Cổ phần Công nghệ Mẫu", "209/GM-CNM",
        "Hà Nội", date(2026, 10, 14), "Giấy mời dự Hội thảo ứng dụng phần mềm nguồn mở trong chuyển đổi số",
        title="GIẤY MỜI", to=("Khoa Công nghệ thông tin, Trường Đại học Mẫu",),
        body=("Công ty Cổ phần Công nghệ Mẫu trân trọng kính mời đại diện lãnh đạo Khoa tham dự Hội thảo “Ứng dụng phần "
              "mềm nguồn mở trong chuyển đổi số”.", "Thời gian: 8 giờ 30, thứ Năm ngày 05/11/2026.",
              "Địa điểm: Hội trường tầng 2, tòa nhà Mẫu, Hà Nội.", "Rất mong được đón tiếp./."),
        signer=("GIÁM ĐỐC",)),
    Mau("07-cong-van-khan.pdf", "CV", ("UBND TỈNH MẪU", "SỞ GIÁO DỤC VÀ ĐÀO TẠO"), "Sở Giáo dục và Đào tạo tỉnh Mẫu",
        "1205/SGDĐT-VP", "Mẫu", date(2026, 10, 16),
        "Về việc triển khai hệ thống quản lý văn bản điện tử trong các cơ sở giáo dục năm học 2026–2027",
        vv="triển khai hệ thống quản lý văn bản điện tử trong các cơ sở giáo dục năm học 2026–2027",
        to=("- Các trường đại học, cao đẳng trên địa bàn tỉnh;", "- Các phòng chuyên môn thuộc Sở."),
        body=("Thực hiện Kế hoạch chuyển đổi số ngành giáo dục năm 2026, Sở Giáo dục và Đào tạo đề nghị các đơn vị khẩn "
              "trương triển khai hệ thống quản lý văn bản điện tử, bảo đảm văn bản đi, đến được xử lý trên môi trường "
              "mạng.", "Báo cáo kết quả triển khai gửi về Sở (qua Văn phòng Sở) trước ngày 30/10/2026.",
              "Trân trọng./."),
        signer=("KT. GIÁM ĐỐC", "PHÓ GIÁM ĐỐC"), urgency="khan", stamp="KHẨN"),
    Mau("08-to-trinh.pdf", "TTr", ("TRƯỜNG ĐẠI HỌC MẪU", "KHOA CÔNG NGHỆ THÔNG TIN"), "Khoa Công nghệ thông tin",
        "08/TTr-KCNTT", "Hà Nội", date(2026, 10, 8),
        "Tờ trình về việc đề nghị phê duyệt danh mục học phần tự chọn năm học 2026–2027",
        title="TỜ TRÌNH", trich_yeu="Về việc đề nghị phê duyệt danh mục học phần tự chọn năm học 2026–2027",
        to=("Hiệu trưởng Trường Đại học Mẫu",),
        body=("Căn cứ chương trình đào tạo ngành Công nghệ thông tin ban hành năm 2025, Khoa Công nghệ thông tin kính "
              "trình Hiệu trưởng phê duyệt danh mục 12 học phần tự chọn áp dụng từ năm học 2026–2027 (danh mục kèm "
              "theo).", "Kính trình Hiệu trưởng xem xét, phê duyệt./."),
        signer=("TRƯỞNG KHOA",), receivers=("- Như trên;", "- Lưu: VP Khoa.")),
    Mau("09-bao-cao.pdf", "BC", ("VIỆN NGHIÊN CỨU MẪU",), "Viện Nghiên cứu Mẫu", "15/BC-VNC", "Hà Nội",
        date(2026, 10, 19),
        "Báo cáo kết quả khảo sát nhu cầu đào tạo nguồn nhân lực công nghệ thông tin năm 2026",
        title="BÁO CÁO", trich_yeu="Kết quả khảo sát nhu cầu đào tạo nguồn nhân lực công nghệ thông tin năm 2026",
        to=("Sở Khoa học và Công nghệ tỉnh Mẫu",),
        body=("Thực hiện Hợp đồng nghiên cứu số 21/2026/HĐ-SKHCN, Viện Nghiên cứu Mẫu báo cáo kết quả khảo sát như sau:",
              "1. Đã khảo sát 120 doanh nghiệp và 8 cơ sở đào tạo trên địa bàn tỉnh.",
              "2. Nhu cầu tuyển dụng kỹ sư phần mềm tăng khoảng 18% so với năm 2025.",
              "3. Kiến nghị mở rộng chương trình thực tập tại doanh nghiệp./."),
        signer=("VIỆN TRƯỞNG",)),
    Mau("10-cong-van-tphcm.pdf", "CV", ("CÔNG TY TNHH PHẦN MỀM MẪU",), "Công ty TNHH Phần mềm Mẫu", "12/CV-PMM",
        "TP. Hồ Chí Minh", date(2026, 2, 1), "Về việc đề nghị tiếp nhận sinh viên thực tập tốt nghiệp",
        vv="đề nghị tiếp nhận sinh viên thực tập tốt nghiệp",
        to=("Khoa Công nghệ thông tin, Trường Đại học Mẫu",),
        body=("Công ty TNHH Phần mềm Mẫu có nhu cầu tiếp nhận 10 sinh viên ngành Công nghệ thông tin thực tập tốt nghiệp "
              "từ tháng 3 năm 2026.", "Đề nghị Khoa giới thiệu sinh viên và gửi danh sách về Công ty trước ngày "
              "20/02/2026.", "Trân trọng./."),
        signer=("GIÁM ĐỐC",)),
    # --- mẫu 15–19 (thêm sau, khó hơn): hai trang, ký hiệu ba đoạn / có năm / số có chữ cái phụ, ngày không theo
    # NĐ 30, cơ quan chủ quản hai dòng, văn bản liên tịch, cơ quan ngoài ngành giáo dục
    Mau("15-huong-dan.pdf", "HD", ("UBND THÀNH PHỐ MẪU", "SỞ GIÁO DỤC VÀ ĐÀO TẠO"),
        "Sở Giáo dục và Đào tạo thành phố Mẫu", "118/HD-SGDĐT-GDĐH", "Thành phố Mẫu", date(2026, 10, 5),
        "Hướng dẫn phối hợp tổ chức Ngày hội tư vấn tuyển sinh, hướng nghiệp năm 2027",
        title="HƯỚNG DẪN", trich_yeu="Phối hợp tổ chức Ngày hội tư vấn tuyển sinh, hướng nghiệp năm 2027",
        date_text="Thành phố Mẫu, ngày 5 tháng 10 năm 2026",
        body=("Căn cứ Kế hoạch số 1520/KH-UBND ngày 15 tháng 8 năm 2026 của Ủy ban nhân dân thành phố về công tác giáo "
              "dục hướng nghiệp và định hướng phân luồng học sinh năm học 2026–2027, Sở Giáo dục và Đào tạo hướng dẫn "
              "các cơ sở giáo dục đại học, cao đẳng phối hợp tổ chức Ngày hội tư vấn tuyển sinh, hướng nghiệp năm 2027 "
              "(sau đây gọi là Ngày hội) như sau:",
              "I. MỤC ĐÍCH, YÊU CẦU",
              "1. Cung cấp cho học sinh lớp 12 và cha mẹ học sinh thông tin chính xác, đầy đủ về phương thức tuyển sinh, "
              "ngành đào tạo, học phí, học bổng và cơ hội việc làm của các cơ sở đào tạo trên địa bàn.",
              "2. Ngày hội được tổ chức thiết thực, an toàn, tiết kiệm; không thu phí của học sinh; thông tin tư vấn "
              "thống nhất với đề án tuyển sinh đã công bố.",
              "II. THỜI GIAN, ĐỊA ĐIỂM, HÌNH THỨC",
              "1. Thời gian: ngày 06 và ngày 07 tháng 3 năm 2027.",
              "2. Địa điểm: Nhà Văn hóa Thanh niên thành phố Mẫu.",
              "3. Hình thức: tư vấn trực tiếp tại gian của từng trường, kết hợp phát trực tuyến các buổi tư vấn chung "
              "trên kênh thông tin của Sở.",
              "III. TRÁCH NHIỆM CỦA CÁC ĐƠN VỊ",
              "1. Phòng Giáo dục đại học và Giáo dục thường xuyên: chủ trì xây dựng chương trình, phân bổ gian tư vấn, "
              "tổng hợp đăng ký của các trường.",
              "2. Các cơ sở giáo dục đại học, cao đẳng: đăng ký tham gia bằng văn bản gửi về Sở trước ngày 15 tháng 11 "
              "năm 2026; cử cán bộ tư vấn am hiểu đề án tuyển sinh; chuẩn bị tài liệu giới thiệu ngành, chương trình "
              "đào tạo.",
              "3. Các trường trung học phổ thông: thông báo tới học sinh lớp 12 và cha mẹ học sinh; tổ chức cho học sinh "
              "tham gia Ngày hội theo lịch được phân công, bảo đảm an toàn.",
              "IV. TỔ CHỨC THỰC HIỆN",
              "Sở Giáo dục và Đào tạo đề nghị các đơn vị nghiêm túc triển khai Hướng dẫn này. Trong quá trình thực hiện, "
              "nếu có vướng mắc, các đơn vị phản ánh về Phòng Giáo dục đại học và Giáo dục thường xuyên để được hướng "
              "dẫn./."),
        signer=("KT. GIÁM ĐỐC", "PHÓ GIÁM ĐỐC"),
        receivers=("- Các cơ sở giáo dục đại học, cao đẳng;", "- Các trường THPT;", "- Giám đốc Sở (để b/c);",
                   "- Lưu: VT, GDĐH."), numbered=True),
    Mau("16-nghi-quyet-hdnd.pdf", "NQ", ("HỘI ĐỒNG NHÂN DÂN", "TỈNH MẪU"), "Hội đồng nhân dân tỉnh Mẫu",
        "05/2026/NQ-HĐND", "Mẫu", date(2026, 3, 5),
        "Nghị quyết quy định chính sách hỗ trợ học phí cho sinh viên các ngành công nghệ chiến lược tại cơ sở giáo dục "
        "đại học trên địa bàn tỉnh Mẫu",
        title="NGHỊ QUYẾT",
        trich_yeu="Quy định chính sách hỗ trợ học phí cho sinh viên các ngành công nghệ chiến lược tại cơ sở giáo dục "
                  "đại học trên địa bàn tỉnh Mẫu",
        authority="HỘI ĐỒNG NHÂN DÂN TỈNH MẪU\nKHÓA XV, KỲ HỌP THỨ MƯỜI HAI",
        body=("Căn cứ Luật Tổ chức chính quyền địa phương;", "Căn cứ Luật Ban hành văn bản quy phạm pháp luật;",
              "Căn cứ Luật Giáo dục đại học;",
              "Xét Tờ trình số 41/TTr-UBND ngày 12 tháng 02 năm 2026 của Ủy ban nhân dân tỉnh; Báo cáo thẩm tra của Ban "
              "Văn hóa - Xã hội Hội đồng nhân dân tỉnh; ý kiến thảo luận của đại biểu Hội đồng nhân dân tỉnh tại kỳ "
              "họp.", "QUYẾT NGHỊ:",
              "Điều 1. Phạm vi, đối tượng áp dụng",
              "1. Nghị quyết này quy định chính sách hỗ trợ học phí cho sinh viên đại học chính quy các ngành vi mạch "
              "bán dẫn, trí tuệ nhân tạo, an toàn thông tin tại các cơ sở giáo dục đại học trên địa bàn tỉnh Mẫu.",
              "2. Đối tượng: sinh viên có nơi thường trú tại tỉnh Mẫu, trúng tuyển từ năm 2026, cam kết làm việc tại "
              "tỉnh ít nhất 03 năm sau khi tốt nghiệp.",
              "Điều 2. Mức hỗ trợ",
              "Hỗ trợ 50% học phí theo mức thu thực tế của cơ sở giáo dục đại học, tối đa 1.500.000 đồng/tháng, không "
              "quá 10 tháng/năm học.",
              "Điều 3. Tổ chức thực hiện",
              "1. Giao Ủy ban nhân dân tỉnh tổ chức thực hiện Nghị quyết này.",
              "2. Thường trực Hội đồng nhân dân, các Ban, các Tổ đại biểu và đại biểu Hội đồng nhân dân tỉnh giám sát "
              "việc thực hiện Nghị quyết.",
              "Nghị quyết này đã được Hội đồng nhân dân tỉnh Mẫu khóa XV, kỳ họp thứ mười hai thông qua ngày 05 tháng 3 "
              "năm 2026 và có hiệu lực từ ngày 15 tháng 3 năm 2026./."),
        signer=("CHỦ TỊCH",),
        receivers=("- Thường trực HĐND, UBND tỉnh;", "- Các sở, ban, ngành tỉnh;",
                   "- Các cơ sở giáo dục đại học trên địa bàn;", "- Lưu: VT."), head_bold=2, numbered=True),
    Mau("17-thong-bao-ket-luan.pdf", "TB", ("UBND TỈNH MẪU", "VĂN PHÒNG"), "Văn phòng Ủy ban nhân dân tỉnh Mẫu",
        "152a/TB-VP", "Mẫu", date(2026, 10, 14),
        "Thông báo kết luận của Phó Chủ tịch Ủy ban nhân dân tỉnh Nguyễn Văn A tại cuộc họp về công tác chuẩn bị Ngày "
        "hội việc làm sinh viên năm 2026",
        title="THÔNG BÁO",
        trich_yeu="Kết luận của Phó Chủ tịch Ủy ban nhân dân tỉnh Nguyễn Văn A tại cuộc họp về công tác chuẩn bị Ngày "
                  "hội việc làm sinh viên năm 2026",
        body=("Ngày 09 tháng 10 năm 2026, tại trụ sở Ủy ban nhân dân tỉnh, Phó Chủ tịch Ủy ban nhân dân tỉnh Nguyễn Văn A "
              "chủ trì cuộc họp về công tác chuẩn bị Ngày hội việc làm sinh viên năm 2026. Tham dự có đại diện lãnh đạo "
              "Sở Nội vụ, Sở Giáo dục và Đào tạo, Tỉnh đoàn, Trường Đại học Mẫu và một số doanh nghiệp trên địa bàn.",
              "Sau khi nghe Sở Nội vụ báo cáo và ý kiến của các đại biểu, Phó Chủ tịch Ủy ban nhân dân tỉnh kết luận "
              "như sau:",
              "1. Thống nhất tổ chức Ngày hội việc làm sinh viên năm 2026 vào ngày 21 tháng 11 năm 2026 tại Trường Đại "
              "học Mẫu.",
              "2. Giao Sở Nội vụ chủ trì, phối hợp với Trường Đại học Mẫu xây dựng kế hoạch chi tiết, trình Ủy ban nhân "
              "dân tỉnh trước ngày 25 tháng 10 năm 2026.",
              "3. Trường Đại học Mẫu bố trí địa điểm, bảo đảm an ninh trật tự, vận động sinh viên năm cuối tham gia; "
              "Tỉnh đoàn phối hợp mời doanh nghiệp tham gia tuyển dụng.",
              "Văn phòng Ủy ban nhân dân tỉnh thông báo để các cơ quan, đơn vị biết, thực hiện./."),
        signer=("TL. CHỦ TỊCH", "KT. CHÁNH VĂN PHÒNG", "PHÓ CHÁNH VĂN PHÒNG"),
        receivers=("- PCT UBND tỉnh Nguyễn Văn A;", "- Sở Nội vụ, Sở GD&ĐT;", "- Tỉnh đoàn;", "- Trường Đại học Mẫu;",
                   "- Lưu: VT, KGVX.")),
    Mau("18-ke-hoach-lien-tich.pdf", "KH", ("TỈNH ĐOÀN MẪU", "SỞ GIÁO DỤC VÀ ĐÀO TẠO TỈNH MẪU"),
        "Tỉnh đoàn Mẫu - Sở Giáo dục và Đào tạo tỉnh Mẫu", "27/KHLT-TĐ-SGDĐT", "Quy Nhơn", date(2026, 9, 28),
        "Kế hoạch liên tịch tổ chức Cuộc thi Sinh viên với ý tưởng khởi nghiệp tỉnh Mẫu năm 2026",
        title="KẾ HOẠCH LIÊN TỊCH", trich_yeu="Tổ chức Cuộc thi Sinh viên với ý tưởng khởi nghiệp tỉnh Mẫu năm 2026",
        body=("Thực hiện Chương trình phối hợp giữa Ban Thường vụ Tỉnh đoàn và Sở Giáo dục và Đào tạo giai đoạn "
              "2026–2030, hai cơ quan thống nhất ban hành Kế hoạch liên tịch tổ chức Cuộc thi như sau:",
              "I. MỤC ĐÍCH, YÊU CẦU",
              "Khơi dậy tinh thần khởi nghiệp, đổi mới sáng tạo trong sinh viên; phát hiện, hỗ trợ các ý tưởng khởi "
              "nghiệp có tính khả thi.",
              "II. ĐỐI TƯỢNG, THỜI GIAN",
              "1. Đối tượng: sinh viên các cơ sở giáo dục đại học, cao đẳng trên địa bàn tỉnh, dự thi cá nhân hoặc nhóm "
              "không quá 05 người.",
              "2. Nhận hồ sơ dự thi đến hết ngày 31 tháng 10 năm 2026; chung kết dự kiến trong tháng 12 năm 2026.",
              "III. TỔ CHỨC THỰC HIỆN",
              "Các cơ sở giáo dục đại học, cao đẳng phổ biến Kế hoạch tới sinh viên, cử cán bộ phụ trách và gửi danh "
              "sách đăng ký về Tỉnh đoàn (qua Ban Thanh niên trường học) trước ngày 20 tháng 10 năm 2026./."),
        signer=("TM. SỞ GIÁO DỤC VÀ ĐÀO TẠO", "GIÁM ĐỐC"), signer2=("TM. BAN THƯỜNG VỤ TỈNH ĐOÀN", "BÍ THƯ"),
        receivers=("- Thường trực Tỉnh ủy (để b/c);", "- Các cơ sở giáo dục đại học, cao đẳng;",
                   "- Lưu: VT Tỉnh đoàn, VT Sở GD&ĐT."), head_bold=2),
    Mau("19-cong-van-benh-vien.pdf", "CV", ("SỞ Y TẾ", "TỈNH MẪU", "BỆNH VIỆN ĐA KHOA KHU VỰC MẪU"),
        "Bệnh viện Đa khoa khu vực Mẫu", "1532/BVĐKKV-KHTH", "Buôn Ma Thuột", date(2026, 10, 12),
        "Về việc phối hợp khám sức khỏe đầu khóa cho sinh viên năm thứ nhất khóa 2026",
        vv="phối hợp khám sức khỏe đầu khóa cho sinh viên năm thứ nhất khóa 2026",
        date_text="Buôn Ma Thuột, ngày 12/10/2026",
        to=("Trường Đại học Mẫu",),
        body=("Thực hiện Hợp đồng số 86/2026/HĐ-BVĐKKV ngày 25 tháng 9 năm 2026 giữa Bệnh viện Đa khoa khu vực Mẫu và "
              "Trường Đại học Mẫu, Bệnh viện đề nghị Nhà trường phối hợp tổ chức khám sức khỏe đầu khóa cho sinh viên "
              "năm thứ nhất khóa 2026, cụ thể như sau:",
              "1. Thời gian: từ ngày 26/10/2026 đến hết ngày 06/11/2026, buổi sáng từ 7 giờ 00 đến 11 giờ 00.",
              "2. Địa điểm: Trạm Y tế của Nhà trường; Bệnh viện bố trí 02 tổ khám lưu động và xe chụp X-quang.",
              "3. Nhà trường lập danh sách sinh viên theo lớp, thông báo lịch khám, nhắc sinh viên nhịn ăn sáng để xét "
              "nghiệm máu và cử cán bộ phối hợp tại điểm khám.",
              "Kết quả khám được gửi Nhà trường trong 10 ngày làm việc kể từ ngày khám xong. Rất mong nhận được sự phối "
              "hợp của Quý Trường./."),
        signer=("KT. GIÁM ĐỐC", "PHÓ GIÁM ĐỐC"), receivers=("- Như trên;", "- Ban Giám đốc;", "- Lưu: VT, KHTH.")),
)
# Phụ lục của mẫu 22 (trang 2–3 của bản scan): tám nhiệm vụ, mỗi nhiệm vụ một đề mục và một đoạn
_TASKS = (
    ("Ứng dụng trí tuệ nhân tạo hỗ trợ chẩn đoán bệnh trên cây lúa tại tỉnh Bắc Mẫu",
     "nhận dạng 10 loại bệnh phổ biến trên lá lúa từ ảnh chụp điện thoại, độ chính xác từ 85% trở lên",
     "phần mềm, bộ dữ liệu ảnh có gán nhãn, báo cáo đánh giá", 24),
    ("Nghiên cứu giải pháp quản lý văn bản điện tử dùng phần mềm nguồn mở cho cấp xã",
     "đề xuất mô hình triển khai, thử nghiệm tại 05 xã, đánh giá chi phí so với phần mềm thương mại",
     "mô hình triển khai, bộ tài liệu hướng dẫn, báo cáo đánh giá", 18),
    ("Xây dựng bản đồ số nguy cơ sạt lở đất các huyện miền núi tỉnh Bắc Mẫu",
     "bản đồ tỷ lệ 1:10.000, cập nhật được theo dữ liệu mưa, cảnh báo sớm cho chính quyền cơ sở",
     "cơ sở dữ liệu không gian, bản đồ số, quy trình cập nhật", 24),
    ("Nghiên cứu chế tạo thiết bị đo chất lượng nước nuôi trồng thủy sản giá thấp",
     "đo nhiệt độ, độ pH, oxy hòa tan, gửi số liệu về điện thoại; giá thành dưới 5 triệu đồng một bộ",
     "05 bộ thiết bị hoàn chỉnh, bản vẽ thiết kế, phần mềm", 18),
    ("Đánh giá nhu cầu nhân lực ngành vi mạch bán dẫn tỉnh Bắc Mẫu giai đoạn 2027–2035",
     "dự báo nhu cầu theo trình độ, đề xuất chương trình hợp tác đào tạo với các cơ sở giáo dục đại học",
     "báo cáo dự báo, đề xuất chính sách", 12),
    ("Phát triển sản phẩm du lịch nông nghiệp gắn với chuyển đổi số tại tỉnh Bắc Mẫu",
     "xây dựng 03 sản phẩm du lịch mẫu, ứng dụng thuyết minh tự động trên điện thoại",
     "sản phẩm du lịch mẫu, ứng dụng di động, báo cáo hiệu quả", 24),
    ("Nghiên cứu mô hình xử lý rác thải sinh hoạt quy mô thôn, bản",
     "lựa chọn công nghệ phù hợp, thử nghiệm tại 02 thôn, giảm ít nhất 60% lượng rác phải chôn lấp",
     "mô hình thử nghiệm, quy trình vận hành, báo cáo đánh giá", 18),
    ("Ứng dụng dữ liệu lớn phân tích nhu cầu học tập suốt đời của người dân tỉnh Bắc Mẫu",
     "phân tích dữ liệu khảo sát và dữ liệu mở, đề xuất danh mục khóa học trực tuyến ưu tiên",
     "bộ dữ liệu, báo cáo phân tích, danh mục khóa học đề xuất", 12),
)
ANNEX_22 = ("= PHỤ LỤC", "= DANH MỤC NHIỆM VỤ KHOA HỌC VÀ CÔNG NGHỆ CẤP TỈNH ĐẶT HÀNG THỰC HIỆN TỪ NĂM 2027",
            "~ (Kèm theo Quyết định số 1875/QĐ-UBND ngày 05 tháng 3 năm 2026 của Chủ tịch Ủy ban nhân dân tỉnh Bắc Mẫu)",
            *(line for i, (name, goal, product, months) in enumerate(_TASKS, 1)
              for line in (f"# {i}. {name}", f"Định hướng mục tiêu: {goal}. Sản phẩm: {product}. Phương thức: tuyển "
                           f"chọn; thời gian thực hiện không quá {months} tháng.")))
SCANS = (
    Scan("11-cong-van-anh-300dpi.jpg", "01-cong-van.pdf", 300, "jpg", 0.8, 0.5, 0.05, color=True, quality=70, seed=11),
    Scan("12-quyet-dinh-anh-mo.jpg", "02-quyet-dinh.pdf", 200, "jpg", -1.2, 1.1, 0.06, quality=65, seed=12),
    Scan("13-thong-bao-ban-scan.pdf", "03-thong-bao.pdf", 200, "pdf", 0.5, 0.4, 0.04, quality=70, seed=13),
    Scan("14-giay-moi-xam.png", "06-giay-moi.pdf", 200, "png", 1.5, 0.3, 0.0, seed=14),
    # --- mẫu 20–22: chỉ có bản ảnh, khó hơn 11–14
    Scan("20-cong-dien-anh-chup.jpg", None, 200, "jpg", 3.2, 0.8, 0.05, quality=70, seed=20, photo=True,
         content=Mau("20-cong-dien-anh-chup.jpg", "CĐ", ("ỦY BAN NHÂN DÂN", "TỈNH MẪU"), "Ủy ban nhân dân tỉnh Mẫu",
                     "07/CĐ-UBND", "Mẫu", date(2026, 10, 16),
                     "Công điện về việc chủ động ứng phó với bão số 6 và mưa lũ sau bão",
                     title="CÔNG ĐIỆN", trich_yeu="Về việc chủ động ứng phó với bão số 6 và mưa lũ sau bão",
                     authority="CHỦ TỊCH ỦY BAN NHÂN DÂN TỈNH MẪU điện:",
                     body=("- Giám đốc các sở, ban, ngành tỉnh;",
                           "- Chủ tịch Ủy ban nhân dân các huyện, thị xã, thành phố;",
                           "- Hiệu trưởng các trường đại học, cao đẳng trên địa bàn tỉnh.",
                           "Theo Đài Khí tượng Thủy văn tỉnh Mẫu, đêm 17/10/2026 bão số 6 đổ bộ vào địa bàn tỉnh, gió "
                           "mạnh cấp 10, giật cấp 12; từ ngày 17 đến ngày 19/10 có mưa rất to, nguy cơ lũ quét, sạt lở "
                           "đất. Chủ tịch Ủy ban nhân dân tỉnh yêu cầu:",
                           "1. Các trường đại học, cao đẳng cho sinh viên nghỉ học trực tiếp từ ngày 17 đến hết ngày "
                           "19/10/2026, chuyển sang học trực tuyến nếu đủ điều kiện; bố trí chỗ ở an toàn cho sinh viên "
                           "nội trú.",
                           "2. Các sở, ngành, địa phương triển khai ngay phương án ứng phó, trực ban 24/24 giờ, báo cáo "
                           "về Văn phòng Ủy ban nhân dân tỉnh trước 16 giờ hằng ngày./."),
                     signer=("KT. CHỦ TỊCH", "PHÓ CHỦ TỊCH"),
                     receivers=("- Như trên;", "- TT Tỉnh ủy, TT HĐND tỉnh (để b/c);", "- Lưu: VT, KT."),
                     urgency="hoa_toc", stamp="HỎA TỐC")),
    Scan("21-cong-van-ngan-hang-xam.jpg", None, 200, "jpg", -0.7, 0.6, 0.06, quality=60, seed=21, tone=(80, 178),
         content=Mau("21-cong-van-ngan-hang-xam.jpg", "CV", ("NGÂN HÀNG TMCP MẪU", "CHI NHÁNH CẦN THƠ"),
                     "Ngân hàng TMCP Mẫu - Chi nhánh Cần Thơ", "2041/2026/CV-CNCT", "Cần Thơ", date(2026, 10, 9),
                     "Về việc phối hợp triển khai thẻ sinh viên liên kết năm học 2026–2027",
                     vv="phối hợp triển khai thẻ sinh viên liên kết năm học 2026–2027",
                     to=("Trường Đại học Mẫu",),
                     body=("Căn cứ Thỏa thuận hợp tác số 12/2025/TTHT-NHM ngày 15 tháng 8 năm 2025 giữa Ngân hàng TMCP "
                           "Mẫu và Trường Đại học Mẫu, Chi nhánh Cần Thơ đề nghị Nhà trường phối hợp triển khai thẻ "
                           "sinh viên liên kết cho sinh viên khóa 2026 như sau:",
                           "1. Thẻ sinh viên tích hợp chức năng thẻ thanh toán nội địa; sinh viên tự nguyện đăng ký, "
                           "không mất phí phát hành và phí thường niên năm đầu.",
                           "2. Ngân hàng cử cán bộ tiếp nhận hồ sơ tại Trường từ ngày 19/10/2026 đến ngày 30/10/2026; "
                           "Nhà trường cung cấp danh sách lớp và bố trí địa điểm.",
                           "3. Thông tin của sinh viên chỉ dùng để phát hành thẻ và được bảo vệ theo quy định về bảo vệ "
                           "dữ liệu cá nhân.", "Trân trọng cảm ơn sự hợp tác của Quý Trường./."),
                     signer=("TUQ. GIÁM ĐỐC", "TRƯỞNG PHÒNG KHÁCH HÀNG CÁ NHÂN"),
                     receivers=("- Như trên;", "- Lưu: VT, KHCN."))),
    Scan("22-quyet-dinh-scan-3-trang.pdf", None, 150, "pdf", 0.6, 0.5, 0.05, quality=60, seed=22,
         content=Mau("22-quyet-dinh-scan-3-trang.pdf", "QĐ", ("ỦY BAN NHÂN DÂN", "TỈNH BẮC MẪU"),
                     "Ủy ban nhân dân tỉnh Bắc Mẫu", "1875/QĐ-UBND", "Bắc Mẫu", date(2026, 3, 5),
                     "Quyết định về việc phê duyệt danh mục nhiệm vụ khoa học và công nghệ cấp tỉnh đặt hàng thực hiện "
                     "từ năm 2027",
                     title="QUYẾT ĐỊNH",
                     trich_yeu="Về việc phê duyệt danh mục nhiệm vụ khoa học và công nghệ cấp tỉnh đặt hàng thực hiện "
                               "từ năm 2027",
                     authority="CHỦ TỊCH ỦY BAN NHÂN DÂN TỈNH BẮC MẪU",
                     date_text="Bắc Mẫu, ngày 5 tháng 03 năm 2026",
                     body=("Căn cứ Luật Tổ chức chính quyền địa phương;",
                           "Căn cứ Luật Khoa học, công nghệ và đổi mới sáng tạo;",
                           "Theo đề nghị của Giám đốc Sở Khoa học và Công nghệ tại Tờ trình số 36/TTr-SKHCN ngày 20 "
                           "tháng 02 năm 2026.", "QUYẾT ĐỊNH:",
                           "Điều 1. Phê duyệt danh mục 08 nhiệm vụ khoa học và công nghệ cấp tỉnh đặt hàng để tuyển chọn "
                           "tổ chức, cá nhân chủ trì thực hiện từ năm 2027 (Phụ lục kèm theo).",
                           "Điều 2. Sở Khoa học và Công nghệ thông báo công khai danh mục, tổ chức tuyển chọn theo quy "
                           "định.",
                           "Điều 3. Quyết định này có hiệu lực kể từ ngày ký. Chánh Văn phòng Ủy ban nhân dân tỉnh, Giám "
                           "đốc Sở Khoa học và Công nghệ và thủ trưởng các cơ quan, đơn vị liên quan chịu trách nhiệm thi "
                           "hành Quyết định này./."),
                     signer=("KT. CHỦ TỊCH", "PHÓ CHỦ TỊCH"),
                     receivers=("- Như Điều 3;", "- Các cơ sở giáo dục đại học trên địa bàn;", "- Lưu: VT, KGVX."),
                     annex=ANNEX_22, numbered=True)),
)


def labels() -> dict:
    """nhan.json: nhãn đúng của mọi mẫu; urgency "normal" là không có dấu độ khẩn."""
    by_file = {m.file: m for m in SAMPLES}
    out = []
    for m in SAMPLES:
        out.append({"file": m.file, "kind": "text", "fields": _fields(m)})
    for s in SCANS:
        out.append({"file": s.file, "kind": "scan", "source": s.source, "fields": _fields(s.mau(by_file))})
    out.sort(key=lambda sample: sample["file"])        # theo số thứ tự tệp: mẫu thêm sau nằm cuối, nhãn cũ giữ nguyên
    return {"version": 1, "note": NOTE, "samples": out}


def _fields(m: Mau) -> dict:
    return {"type_code": m.type_code, "symbol": m.symbol, "issued_on": m.issued.isoformat(),
            "issuer_name": m.issuer_label, "urgency": m.urgency, "summary": m.summary_label}


def date_line(m: Mau) -> str:
    """"Hà Nội, ngày 05 tháng 3 năm 2026": ngày dưới 10, tháng 1, 2 có số 0 ở trước (NĐ 30, Phụ lục I)."""
    month = f"{m.issued.month:02d}" if m.issued.month <= 2 else str(m.issued.month)
    return f"{m.place}, ngày {m.issued.day:02d} tháng {month} năm {m.issued.year}"


# ---------------------------------------------------------------------------------------------------------------
# PDF có lớp chữ (WeasyPrint): mở rộng _letter_html() của seed_documents.py — tiêu đề loại, hai dòng tên cơ quan,
# dấu độ khẩn, ký hiệu có năm, dòng thẩm quyền, nơi nhận

CSS = """
@page { size: A4; margin: 20mm 15mm 20mm 30mm; }
body { font-family: "Liberation Serif", serif; font-size: 13pt; line-height: 1.3; color: #000; }
table { width: 100%; border-collapse: collapse; }
td { vertical-align: top; padding: 0; }
table.head td { text-align: center; font-size: 12.5pt; }
.b { font-weight: bold; } .i { font-style: italic; }
.rule { width: 34%; margin: 1pt auto 5pt; border-top: 0.8pt solid #000; }
.vv { font-size: 12pt; margin: 3pt 8% 0; }
.stamp { display: inline-block; margin-top: 10pt; padding: 1pt 10pt; border: 1.2pt solid #000; font-weight: bold; }
h1 { font-size: 14pt; text-align: center; margin: 18pt 0 0; }
.ty { text-align: center; font-weight: bold; margin: 0 10%; }
.auth { text-align: center; font-weight: bold; margin-top: 12pt; }
.to { text-align: center; margin: 14pt 0 10pt; }
.to-list { margin: 14pt 0 10pt 22%; }
p { text-indent: 10mm; text-align: justify; margin: 0 0 5pt; }
table.foot { margin-top: 14pt; }
.recv { font-size: 11pt; } .recv .h { font-weight: bold; font-style: italic; font-size: 12pt; }
.sign { text-align: center; } .gap { height: 20mm; }
.note { margin-top: 18pt; font-size: 9pt; color: #555; }
"""
# Số trang (NĐ 30): giữa lề trên, cỡ 13, không hiện ở trang 1 — chỉ chèn khi ``numbered`` (mẫu cũ giữ CSS cũ)
CSS_PAGES = """
@page { @top-center { content: counter(page); font-family: "Liberation Serif", serif; font-size: 13pt; } }
@page :first { @top-center { content: none; } }
"""


def bold_head(m: Mau, i: int) -> bool:
    """Dòng thứ i của tên cơ quan in đậm: tên cơ quan ban hành đậm, cơ quan chủ quản không (NĐ 30)."""
    if m.head_bold:
        return i >= len(m.issuer) - m.head_bold
    return i == len(m.issuer) - 1 or len(m.issuer) == 2 and m.issuer[0].startswith("ỦY BAN")


def letter_html(m: Mau) -> str:
    import html

    if m.annex:
        raise ValueError(f"{m.file}: phụ lục chỉ vẽ được ở bản ảnh (paint_annex)")
    e = html.escape
    left = "".join(f'<div class="b">{e(t)}</div>' if bold_head(m, i) else f"<div>{e(t)}</div>"
                   for i, t in enumerate(m.issuer))
    left += f'<div class="rule"></div><div>Số: {e(m.symbol)}</div>'
    if m.vv:
        left += f'<div class="vv">V/v {e(m.vv)}</div>'
    if m.stamp:
        left += f'<div class="stamp">{e(m.stamp)}</div>'
    right = (f'<div class="b">{MOTTO}</div><div class="b">{MOTTO2}</div><div class="rule"></div>'
             f'<div class="i">{e(m.date_text or date_line(m))}</div>')
    main = ""
    if m.title:
        main += f"<h1>{e(m.title)}</h1>"
        if m.trich_yeu:
            main += f'<div class="ty">{e(m.trich_yeu)}</div><div class="rule"></div>'
    if m.authority:              # nhiều dòng (nghị quyết: tên Hội đồng, khóa, kỳ họp) cách nhau bằng "\n"
        first, *more = m.authority.split("\n")
        main += f'<div class="auth">{e(first)}</div>'
        main += "".join(f'<div class="auth" style="margin-top: 0">{e(t)}</div>' for t in more)
    if len(m.to) == 1:
        main += f'<div class="to">Kính gửi: {e(m.to[0])}</div>'
    elif m.to:
        main += '<div class="to-list"><div>Kính gửi:</div>' + "".join(f"<div>{e(t)}</div>" for t in m.to) + "</div>"
    elif m.authority or m.title:
        main += '<div style="height: 8pt"></div>'
    for line in m.body:
        bold = line.isupper() or line.startswith("Điều ") and len(line) < 40 or line in HEADINGS
        style = ' style="text-indent: 0; text-align: center; font-weight: bold"' if line in HEADINGS else (
            ' class="b"' if bold else "")
        main += f"<p{style}>{e(line)}</p>"
    recv = '<div class="h">Nơi nhận:</div>' + "".join(f"<div>{e(t)}</div>" for t in m.receivers)
    sign = "".join(f'<div class="b">{e(t)}</div>' for t in m.signer)
    sign += f'<div class="i">(Đã ký)</div><div class="gap"></div><div class="b">{SIGNER}</div>'
    if m.signer2:                # liên tịch: cơ quan chủ trì ký bên phải, cơ quan kia bên trái; nơi nhận ở dưới
        sign2 = "".join(f'<div class="b">{e(t)}</div>' for t in m.signer2)
        sign2 += f'<div class="i">(Đã ký)</div><div class="gap"></div><div class="b">{SIGNER2}</div>'
        foot = (f'<table class="foot"><tr><td class="sign" style="width: 50%">{sign2}</td><td class="sign">{sign}</td>'
                f'</tr></table>\n<table class="foot"><tr><td class="recv">{recv}</td></tr></table>')
    else:
        foot = (f'<table class="foot"><tr><td class="recv" style="width: 50%">{recv}</td><td class="sign">{sign}</td>'
                f'</tr></table>')
    css = CSS + (CSS_PAGES if m.numbered else "")
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>{css}</style></head><body>
<table class="head"><tr><td style="width: 42%">{left}</td><td>{right}</td></tr></table>
{main}
{foot}
<div class="note">{NOTE}</div>
</body></html>"""


def render_pdf(m: Mau) -> bytes:
    from weasyprint import HTML

    return HTML(string=letter_html(m)).write_pdf()


# ---------------------------------------------------------------------------------------------------------------
# "Bản scan" vẽ bằng Pillow: cùng nội dung, bố cục gần như bản PDF

FONT_DIRS = ("/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/liberation2",
             "/usr/share/fonts/liberation", "/usr/share/fonts/liberation-serif")
FONT_FILES = {"r": "LiberationSerif-Regular.ttf", "b": "LiberationSerif-Bold.ttf", "i": "LiberationSerif-Italic.ttf",
              "bi": "LiberationSerif-BoldItalic.ttf"}
FALLBACK = {"r": "DejaVu Serif", "b": "DejaVu Serif:style=Bold", "i": "DejaVu Serif:style=Italic",
            "bi": "DejaVu Serif:style=Bold Italic"}


def font_file(style: str) -> str:
    """Phông Liberation Serif (có đủ dấu tiếng Việt); máy không có thì phông serif khác có dấu, qua fc-match."""
    for folder in FONT_DIRS:
        path = pathlib.Path(folder) / FONT_FILES[style]
        if path.is_file():
            return str(path)
    styles = {"r": "Regular", "b": "Bold", "i": "Italic", "bi": "Bold Italic"}
    for pattern in (f"Liberation Serif:style={styles[style]}", FALLBACK[style]):
        try:
            found = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True,
                                   timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            found = ""
        if found and pathlib.Path(found).is_file() and "Serif" in found:
            return found
    raise SystemExit("Không tìm thấy phông Liberation Serif hoặc DejaVu Serif để vẽ bản scan")


class Painter:
    """Vẽ một trang A4 theo bố cục của letter_html: lề NĐ 30, phần đầu hai cột, tiêu đề, thân, chữ ký."""

    def __init__(self, dpi: int) -> None:
        from PIL import Image, ImageDraw

        self.dpi = dpi
        self.mm = dpi / 25.4
        self.w, self.h = round(210 * self.mm), round(297 * self.mm)
        self.img = Image.new("L", (self.w, self.h), 255)
        self.draw = ImageDraw.Draw(self.img)
        self.left, self.right, self.top = 30 * self.mm, self.w - 15 * self.mm, 20 * self.mm
        self.fonts: dict[tuple[str, float], object] = {}

    def font(self, style: str, pt: float):
        from PIL import ImageFont

        key = (style, pt)
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(font_file(style), round(pt * self.dpi / 72))
        return self.fonts[key]

    def wrap(self, text: str, font, width: float, indent: float = 0) -> list[str]:
        lines, line = [], ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and font.getlength(trial) > width - (indent if not lines else 0):
                lines.append(line)
                line = word
            else:
                line = trial
        return lines + [line] if line else lines

    def centered(self, items: list[tuple[str, str, float]], x0: float, x1: float, y: float, pad: float = 0) -> float:
        """items: (kiểu, chữ, cỡ chữ); kiểu "rule" là gạch ngang ngắn, "stamp" là chữ có khung."""
        for style, text, pt in items:
            lh = pt * self.dpi / 72 * 1.3
            if style == "rule":
                mid, half = (x0 + x1) / 2, (x1 - x0) * 0.17
                self.draw.line([(mid - half, y + 1 * self.mm / 3), (mid + half, y + 1 * self.mm / 3)], fill=0,
                               width=max(1, round(self.dpi / 110)))
                y += 2 * self.mm
                continue
            font = self.font("b" if style == "stamp" else style, pt)
            if style == "stamp":
                y += 3 * self.mm
            for line in self.wrap(text, font, x1 - x0 - 2 * pad):
                tw = font.getlength(line)
                x = (x0 + x1 - tw) / 2
                self.draw.text((x, y), line, font=font, fill=0)
                if style == "stamp":
                    m = 1.2 * self.mm
                    self.draw.rectangle([x - 3 * m, y - m / 2, x + tw + 3 * m, y + lh], outline=0,
                                        width=max(1, round(self.dpi / 90)))
                y += lh
        return y

    def paragraph(self, text: str, y: float, *, bold: bool = False, center: bool = False, pt: float = 13) -> float:
        font = self.font("b" if bold else "r", pt)
        lh = pt * self.dpi / 72 * 1.3
        if center:
            return self.centered([("b" if bold else "r", text, pt)], self.left, self.right, y)
        indent = 10 * self.mm
        for i, line in enumerate(self.wrap(text, font, self.right - self.left, indent)):
            self.draw.text((self.left + (indent if i == 0 else 0), y), line, font=font, fill=0)
            y += lh
        return y + 1.8 * self.mm


def paint(m: Mau, dpi: int):
    """Trang 1 (cả văn bản trừ phụ lục)."""
    if m.signer2:
        raise ValueError(f"{m.file}: văn bản liên tịch chỉ in được ở PDF có lớp chữ (letter_html)")
    p = Painter(dpi)
    col = p.left + 0.42 * (p.right - p.left)
    left = [("b" if (bold_head(m, i) if m.head_bold else i == len(m.issuer) - 1 or m.issuer[0].startswith("ỦY BAN"))
             else "r", t, 12.5) for i, t in enumerate(m.issuer)]
    left += [("rule", "", 0), ("r", f"Số: {m.symbol}", 12.5)]
    if m.vv:
        left.append(("r", f"V/v {m.vv}", 12))
    if m.stamp:
        left.append(("stamp", m.stamp, 13))
    right = [("b", MOTTO, 12.5), ("b", MOTTO2, 12.5), ("rule", "", 0), ("i", m.date_text or date_line(m), 12.5)]
    y = max(p.centered(left, p.left, col, p.top, pad=0.08 * (col - p.left)), p.centered(right, col, p.right, p.top))
    if m.title:
        y = p.centered([("b", m.title, 14)], p.left, p.right, y + 6 * p.mm)
        if m.trich_yeu:
            y = p.centered([("b", m.trich_yeu, 13), ("rule", "", 0)], p.left, p.right, y,
                           pad=0.1 * (p.right - p.left))
    if m.authority:
        y = p.centered([("b", t, 13) for t in m.authority.split("\n")], p.left, p.right, y + 4 * p.mm)
    if len(m.to) == 1:
        y = p.centered([("r", f"Kính gửi: {m.to[0]}", 13)], p.left, p.right, y + 5 * p.mm) + 3 * p.mm
    elif m.to:
        y += 5 * p.mm
        x = p.left + 0.22 * (p.right - p.left)
        for line in ("Kính gửi:", *m.to):
            p.draw.text((x, y), line, font=p.font("r", 13), fill=0)
            y += 13 * dpi / 72 * 1.3
        y += 3 * p.mm
    else:
        y += 4 * p.mm
    for line in m.body:
        heading = line in HEADINGS
        y = p.paragraph(line, y, bold=heading or line.isupper() or (line.startswith("Điều ") and len(line) < 40),
                        center=heading)
    y += 4 * p.mm
    yr = y
    p.draw.text((p.left, y), "Nơi nhận:", font=p.font("bi", 12), fill=0)
    for line in m.receivers:
        yr += 12 * dpi / 72 * 1.3
        p.draw.text((p.left, yr), line, font=p.font("r", 11), fill=0)
    mid = (p.left + p.right) / 2
    signer = [("b", t, 13) for t in m.signer] + [("i", "(Đã ký)", 13)]
    ys = p.centered(signer, mid, p.right, y) + 18 * p.mm
    ys = p.centered([("b", SIGNER, 13)], mid, p.right, ys)
    end = p.centered([("r", NOTE, 9)], p.left, p.right, max(ys, yr) + 10 * p.mm)
    if end > p.h - 5 * p.mm:
        raise ValueError(f"{m.file}: nội dung tràn trang 1 của bản ảnh — rút gọn thân hoặc đưa vào phụ lục")
    return p.img


def paint_annex(m: Mau, dpi: int) -> list:
    """Các trang phụ lục, sau trang 1: phụ lục sang trang mới, số trang đánh riêng (trang đầu phụ lục không hiện)."""
    pages: list[Painter] = []
    lh = 13 * dpi / 72 * 1.3

    def new_page() -> Painter:
        q = Painter(dpi)
        pages.append(q)
        if m.numbered and len(pages) > 1:
            q.centered([("r", str(len(pages)), 13)], q.left, q.right, 10 * q.mm)
        return q

    p = new_page()
    y = p.top
    for line in m.annex:
        mark, text = (line[0], line[2:]) if line[:2] in ("= ", "~ ", "# ") else ("", line)
        style = {"=": "b", "~": "i", "#": "b"}.get(mark, "r")
        centered = mark in ("=", "~")
        lines = len(p.wrap(text, p.font(style, 13), p.right - p.left, 0 if centered else 10 * p.mm))
        if y + lines * lh > p.h - 20 * p.mm:        # không vừa lề dưới: sang trang
            p = new_page()
            y = p.top
        if centered:
            y = p.centered([(style, text, 13)], p.left, p.right, y, pad=0.05 * (p.right - p.left))
            y += 2 * p.mm if mark == "~" else 0
        else:
            y = p.paragraph(text, y, bold=mark == "#")
    p.centered([("r", NOTE, 9)], p.left, p.right, min(y + 10 * p.mm, p.h - 12 * p.mm))
    return [q.img for q in pages]


def _scan(img, s: Scan, rnd: random.Random, angle: float):
    """Một trang qua máy scan: mờ nhẹ, đặt lệch ``angle`` độ, (nền xám, mực nhạt), hạt nhiễu, vết bẩn, (giấy ngả vàng)."""
    from PIL import Image, ImageChops, ImageFilter

    if s.blur:
        img = img.filter(ImageFilter.GaussianBlur(s.blur))
    img = img.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
    if s.tone:               # tương phản thấp: trắng → nền xám, đen → mực xám; tối dần về mép gáy (bên trái)
        ink, paper = s.tone
        img = img.point(lambda v: ink + (paper - ink) * v // 255)
        edge = img.size[0] // 6
        row = bytes(255 - (70 * (edge - x) // edge if x < edge else 0) for x in range(img.size[0]))
        img = ImageChops.multiply(img, Image.frombytes("L", (img.size[0], 1), row).resize(
            img.size, Image.Resampling.NEAREST))
    if s.grain:
        noise = Image.frombytes("L", img.size, rnd.randbytes(img.size[0] * img.size[1]))
        noise = noise.filter(ImageFilter.BoxBlur(1))
        img = Image.blend(img, noise, s.grain)
    for _ in range(img.size[0] * img.size[1] // 40_000):        # vài vết bẩn nhỏ
        x, y = rnd.randrange(img.size[0]), rnd.randrange(img.size[1])
        r = rnd.choice((1, 1, 2))
        img.paste(rnd.randrange(60, 160), (x, y, min(x + r, img.size[0]), min(y + r, img.size[1])))
    if s.color:          # giấy hơi ngả vàng
        img = Image.merge("RGB", (img.point(lambda v: v * 250 // 255), img.point(lambda v: v * 246 // 255),
                                  img.point(lambda v: v * 232 // 255)))
    return img


def _photo(img, s: Scan, rnd: random.Random):
    """Ảnh chụp bằng điện thoại: tờ giấy ngả màu nằm nghiêng ``angle`` độ trên mặt bàn, chụp chếch (đầu trang xa máy
    hơn: cạnh trên hẹp hơn cạnh dưới), sáng không đều (tối dần về góc dưới phải), mờ, hạt nhiễu."""
    from PIL import Image, ImageChops, ImageFilter

    desk = (96, 80, 64)
    paper = Image.merge("RGB", (img.point(lambda v: 40 + v * 208 // 255), img.point(lambda v: 38 + v * 204 // 255),
                                img.point(lambda v: 34 + v * 192 // 255)))
    w, h = paper.size
    mx, my = round(0.08 * w), round(0.06 * h)
    photo = Image.new("RGB", (w + 2 * mx, h + 2 * my), desk)
    photo.paste(paper, (mx, my))
    photo = photo.rotate(s.angle, resample=Image.Resampling.BICUBIC, fillcolor=desk)
    pw, ph = photo.size
    k = 0.035 * pw
    photo = photo.transform(photo.size, Image.Transform.QUAD, (-k, 0, 0, ph, pw, ph, pw + k, 0),
                            resample=Image.Resampling.BICUBIC, fillcolor=desk)
    down = Image.linear_gradient("L").resize(photo.size)                                  # 0 trên → 255 dưới
    across = Image.linear_gradient("L").transpose(Image.Transpose.ROTATE_90).resize(photo.size)
    across = across.transpose(Image.Transpose.FLIP_LEFT_RIGHT)                            # 0 trái → 255 phải
    light = ImageChops.add(down, across, scale=2).point(lambda v: 255 - v * 80 // 255)
    photo = ImageChops.multiply(photo, Image.merge("RGB", (light, light, light)))
    if s.blur:
        photo = photo.filter(ImageFilter.GaussianBlur(s.blur))
    if s.grain:
        noise = Image.frombytes("L", photo.size, rnd.randbytes(pw * ph)).filter(ImageFilter.BoxBlur(1))
        photo = Image.blend(photo, Image.merge("RGB", (noise, noise, noise)), s.grain)
    return photo


def scan_bytes(s: Scan, m: Mau) -> bytes:
    """Ảnh "chụp" của văn bản: xoay nhẹ, mờ, hạt nhiễu (hạt giống cố định), nén JPEG/PNG; PDF mỗi trang một ảnh (trang
    sau trang 1 đặt lệch một góc ngẫu nhiên khác) — hoặc ảnh chụp bằng điện thoại (``photo``)."""
    rnd = random.Random(s.seed)
    pages = [paint(m, s.dpi), *(paint_annex(m, s.dpi) if m.annex else ())]
    if len(pages) > 1 and (s.fmt != "pdf" or s.photo):
        raise ValueError(f"{s.file}: văn bản nhiều trang chỉ lưu được thành PDF scan")
    if s.photo:
        shots = [_photo(page, s, rnd) for page in pages]
    else:
        shots = [_scan(page, s, rnd, s.angle if i == 0 else round(rnd.uniform(-1.2, 1.2), 2))
                 for i, page in enumerate(pages)]
    img = shots[0]
    out = io.BytesIO()
    if s.fmt == "jpg":
        img.save(out, "JPEG", quality=s.quality, dpi=(72, 72) if s.photo else (s.dpi, s.dpi), optimize=True)
    elif s.fmt == "png":
        img = img.point(lambda v: 255 if v > 235 else v)     # nền trắng phẳng: PNG nén gọn
        img.save(out, "PNG", dpi=(s.dpi, s.dpi), optimize=True)
    else:
        more = {"save_all": True, "append_images": shots[1:]} if len(shots) > 1 else {}
        img.save(out, "PDF", resolution=float(s.dpi), quality=s.quality, title=f"Văn bản mẫu {s.file[:2]}",
                 producer="Mộc van_ban_mau.py", creationDate=FIXED_TIME.timetuple(),
                 modDate=FIXED_TIME.timetuple(), **more)
    return out.getvalue()


# ---------------------------------------------------------------------------------------------------------------
# TSV của Tesseract (fixture cho test quy tắc trên chữ OCR) — xử lý ảnh như ocr.py của svc-files


def ocr_input(data: bytes) -> bytes:
    """Ảnh đưa cho Tesseract: PDF lấy ảnh lớn nhất của trang 1; xám, tự cân tương phản, cạnh dài về 2000–3500 px."""
    from PIL import Image, ImageOps

    if data.startswith(b"%PDF-"):
        from pypdf import PdfReader

        images = PdfReader(io.BytesIO(data)).pages[0].images
        data = max(images, key=lambda im: len(im.data)).data
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    img = ImageOps.autocontrast(img.convert("L"))
    edge = max(img.size)
    if edge < 2000 or edge > 3500:
        scale = (2000 if edge < 2000 else 3500) / edge
        img = img.resize((round(img.size[0] * scale), round(img.size[1] * scale)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def tesseract_tsv(data: bytes) -> str:
    binary = os.environ.get("MOC_TESSERACT_BIN", "tesseract")
    lang = os.environ.get("MOC_OCR_LANG", "vie")
    run = subprocess.run([binary, "stdin", "stdout", "-l", lang, "--oem", "1", "--psm", "3", "tsv"],
                         input=ocr_input(data), capture_output=True, timeout=120,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    if run.returncode != 0:
        raise RuntimeError(f"tesseract lỗi: {run.stderr.decode(errors='replace')[:300]}")
    return run.stdout.decode()


def render_all() -> dict:
    """Mọi tệp mẫu (base64), nhãn, TSV nếu máy có tesseract — chạy được trong container hoặc trên máy."""
    files = {m.file: render_pdf(m) for m in SAMPLES}
    by_file = {m.file: m for m in SAMPLES}
    for s in SCANS:
        files[s.file] = scan_bytes(s, s.mau(by_file))
    result = ocr_all({s.file: files[s.file] for s in SCANS})
    return {**result, "files": {k: base64.b64encode(v).decode() for k, v in files.items()}}


def ocr_all(scans: dict[str, bytes]) -> dict:
    """TSV Tesseract của các bản scan; máy không có tesseract thì bỏ qua, báo một dòng."""
    if not shutil.which(os.environ.get("MOC_TESSERACT_BIN", "tesseract")):
        return {"files": {}, "tsv": {}, "note": "bỏ qua TSV cho test OCR: máy này không có tesseract (chạy make"
                                                " van-ban-mau khi image svc-files có)"}
    return {"files": {}, "tsv": {name: tesseract_tsv(data) for name, data in scans.items()}, "note": None}


# Chạy trong container: stdin là JSON {source, argv, scans}; tệp này chạy như __main__, ảnh cần OCR nằm ở _SCANS
INSIDE = ("import json, sys; d = json.load(sys.stdin); sys.argv = ['van_ban_mau', *d['argv']]; "
          "exec(compile(d['source'], 'van_ban_mau.py', 'exec'), {'__name__': '__main__', '_SCANS': d['scans']})")


def run_in_container(scans: dict[str, bytes] | None) -> dict:
    """In mẫu (scans None) hoặc chỉ OCR các bản scan đã có, trong container svc-files đang chạy."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from moc_env import compose      # đọc .env khi nhập: chỉ cần ở chế độ container

    payload = {"source": pathlib.Path(__file__).read_text(encoding="utf-8"),
               "argv": ["--inside"] + ([] if scans is None else ["--tsv-only"]),
               "scans": {k: base64.b64encode(v).decode() for k, v in (scans or {}).items()}}
    try:
        out = compose("exec", "-T", "svc-files", "python", "-c", INSIDE, stdin=json.dumps(payload).encode())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Không in được trong container svc-files (make up chưa?): "
                         f"{exc.stderr.decode(errors='replace')[-400:]}") from exc
    return json.loads(out)


def main(argv: list[str] | None = None) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent if "__file__" in globals() else pathlib.Path.cwd()
    parser = argparse.ArgumentParser(prog="van_ban_mau", description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=("auto", "local", "container"), default="auto",
                        help="local: WeasyPrint + Pillow trên máy; container: trong svc-files đang chạy; "
                             "auto: local nếu nhập được weasyprint và PIL")
    parser.add_argument("--out", default=str(root / "seed" / "van-ban-den"), help="thư mục ghi mẫu")
    parser.add_argument("--tsv-out", default=str(root / "services" / "svc-files" / "tests" / "fixtures" / "ocr"))
    parser.add_argument("--tsv-only", action="store_true",
                        help="chỉ ghi TSV Tesseract của các bản scan đang có trong --out, không in lại mẫu")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.inside:                  # trong container: in kết quả ra stdout cho phía máy chủ
        if args.tsv_only:
            scans = {k: base64.b64decode(v) for k, v in globals().get("_SCANS", {}).items()}
            sys.stdout.write(json.dumps(ocr_all(scans)))
        else:
            sys.stdout.write(json.dumps(render_all()))
        return 0
    out = pathlib.Path(args.out)
    scans = None
    if args.tsv_only:
        missing = [s.file for s in SCANS if not (out / s.file).is_file()]
        if missing:
            print(f"✗ chưa có bản scan trong {out}: {', '.join(missing)}", file=sys.stderr)
            return 1
        scans = {s.file: (out / s.file).read_bytes() for s in SCANS}
    mode = args.mode
    if mode == "auto":
        try:
            import PIL  # noqa: F401
            if scans is None:
                import weasyprint  # noqa: F401
            elif not shutil.which(os.environ.get("MOC_TESSERACT_BIN", "tesseract")):
                raise ImportError("tesseract")
            mode = "local"
        except (ImportError, OSError):
            mode = "container"
    if mode == "local":
        result = render_all() if scans is None else ocr_all(scans)
    else:
        result = run_in_container(scans)

    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, data in result["files"].items():
        raw = base64.b64decode(data)
        (out / name).write_bytes(raw)
        total += len(raw)
        print(f"  {name:32s} {len(raw) / 1024:7.1f} KB")
    if scans is None:
        (out / "nhan.json").write_text(json.dumps(labels(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {'nhan.json':32s} nhãn của {len(SAMPLES) + len(SCANS)} mẫu")
    if result["tsv"]:
        tsv_dir = pathlib.Path(args.tsv_out)
        tsv_dir.mkdir(parents=True, exist_ok=True)
        for name, text in result["tsv"].items():
            (tsv_dir / (pathlib.Path(name).stem + ".tsv")).write_text(text, encoding="utf-8")
        print(f"  TSV Tesseract của {len(result['tsv'])} bản scan → {tsv_dir}")
    if result.get("note"):
        print(f"  – {result['note']}")
    if scans is None:
        print(f"Tổng {total / 1024 / 1024:.2f} MB ({mode}) → {out}")
    if total > MAX_TOTAL:
        print(f"✗ quá {MAX_TOTAL // 1024 // 1024} MB: giảm dpi, chất lượng JPEG hoặc hạt nhiễu", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
