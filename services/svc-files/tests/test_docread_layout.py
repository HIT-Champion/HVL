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


"""Dòng có vị trí (F4.1): chữ pypdf theo bố cục tách hai cột; TSV của Tesseract gom từ thành dòng."""

from __future__ import annotations

import io
import unicodedata
from datetime import date

import pytest

from conftest import text_pdf
from svc_files.docread.layout import Line, text_lines, tsv_lines
from svc_files.docread.rules import suggest

TODAY = date(2026, 10, 21)


def cx(line: Line) -> float:
    return (line.x0 + line.x1) / 2


def layout_text(pdf: bytes) -> list[str]:
    """Như pdflayout.py của svc-files: pypdf theo bố cục, tối đa 3 trang (tệp tin cậy, chạy ngay trong tiến trình)."""
    from pypdf import PdfReader

    return [page.extract_text(extraction_mode="layout") for page in PdfReader(io.BytesIO(pdf)).pages[:3]]


def test_text_lines_splits_two_columns_at_three_spaces():
    row0 = "TRƯỜNG ĐẠI HỌC MẪU" + " " * 6 + "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
    rows = [row0, "  Số: 12/TB-ĐHM", "", "Kính gửi:  Khoa Công nghệ thông tin"]
    lines = text_lines(["\n".join(rows)])
    width = len(row0)
    assert [(ln.text, ln.page) for ln in lines] == [
        ("TRƯỜNG ĐẠI HỌC MẪU", 1), ("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 1), ("Số: 12/TB-ĐHM", 1),
        ("Kính gửi: Khoa Công nghệ thông tin", 1),          # hai khoảng trắng vẫn là một đoạn, gộp lại
    ]
    left, right, symbol, greeting = lines
    assert (left.x0, left.x1) == (0.0, round(18 / width, 4)) and cx(left) < 0.5 < cx(right)
    assert (right.x0, right.x1) == (round(24 / width, 4), 1.0)
    assert symbol.x0 == round(2 / width, 4)
    assert (left.y, right.y, symbol.y, greeting.y) == (0.0, 0.0, 0.25, 0.75)       # dòng trống vẫn chiếm một hàng


def test_justified_row_stays_one_line():
    rows = ["      Thực   hiện   Chương   trình   hỗ   trợ   khởi   nghiệp",
            "TRƯỜNG ĐẠI HỌC MẪU      CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
            "Một   hai      ba         bốn"]
    assert [ln.text for ln in text_lines(["\n".join(rows)])] == [
        "Thực hiện Chương trình hỗ trợ khởi nghiệp", "TRƯỜNG ĐẠI HỌC MẪU", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
        "Một", "hai", "ba", "bốn"]      # khoảng hở không đều: vẫn là các cột


def test_text_lines_cleans_and_normalizes():
    nfd = unicodedata.normalize("NFD", "Quyết định")
    pages = ["\n\n" + "      " + nfd + "\x00​   B\n" + "    Dòng hai\t\tcó tab\n\n", "", "   \n", "Trang bốn"]
    lines = text_lines(pages)
    assert [(ln.text, ln.page) for ln in lines] == [("Quyết định", 1), ("B", 1), ("Dòng hai có tab", 1),
                                                    ("Trang bốn", 4)]
    assert lines[0].text == unicodedata.normalize("NFC", "Quyết định")
    assert lines[2].x0 == 0.0            # lề trái chung (4 khoảng trắng) đã bỏ
    assert lines[3].y == 0.0 and lines[3].x1 == 1.0


def test_text_lines_on_a_real_two_column_letter():
    try:
        from weasyprint import HTML
    except OSError:
        pytest.skip("máy này thiếu thư viện Pango của WeasyPrint (image svc-files có sẵn)")
    pdf = HTML(string="""<html lang="vi"><body style="font-family: 'Liberation Serif', serif; font-size: 12pt">
        <table style="width: 100%"><tr>
        <td style="width: 40%; text-align: center"><div>ỦY BAN NHÂN DÂN</div><div><b>TỈNH MẪU</b></div>
            <div>Số: 123/QĐ-UBND</div></td>
        <td style="text-align: center"><div><b>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</b></div>
            <div><b>Độc lập - Tự do - Hạnh phúc</b></div><div><i>Mẫu, ngày 05 tháng 10 năm 2026</i></div></td>
        </tr></table>
        <h3 style="text-align: center">QUYẾT ĐỊNH</h3><p style="text-align: center">Về việc ban hành Quy chế văn thư</p>
        <p>Căn cứ Luật Tổ chức chính quyền địa phương ngày 19 tháng 6 năm 2015;</p></body></html>""").write_pdf()
    lines = text_lines(layout_text(pdf))
    by_text = {ln.text: ln for ln in lines}
    assert cx(by_text["ỦY BAN NHÂN DÂN"]) < 0.5 < cx(by_text["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"])
    assert by_text["ỦY BAN NHÂN DÂN"].y == by_text["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"].y
    assert abs(cx(by_text["QUYẾT ĐỊNH"]) - 0.5) < 0.1
    got = {k: (f.value, f.confidence) for k, f in suggest(lines, today=TODAY).fields.items()}
    assert got == {"type_code": ("QĐ", "high"), "symbol": ("123/QĐ-UBND", "high"), "issued_on": ("2026-10-05", "high"),
                   "issuer_name": ("Ủy ban nhân dân tỉnh Mẫu", "medium"),
                   "summary": ("Quyết định về việc ban hành Quy chế văn thư", "high")}


def test_smoke_pdf_is_read_like_scripts_smoke():
    """Đúng tệp make smoke tải lên (Helvetica, chỉ ASCII, dòng sát lề trái): đọc ra số, ngày, loại."""
    tag = "A1B2C3"
    pdf = text_pdf("CONG HOA XA HOI CHU NGHIA VIET NAM", f"So: 99/TB-SMK{tag}", "Ha Noi, ngay 15 thang 10 nam 2026",
                   "THONG BAO", f"Lich hop giao ban thang 11 {tag}")
    got = suggest(text_lines(layout_text(pdf)), today=TODAY).fields
    assert got["symbol"].value == f"99/TB-SMK{tag}"
    assert got["issued_on"].value == "2026-10-15"
    assert got["type_code"].value == "TB"


def tsv(*words: tuple, size: tuple[int, int] = (2000, 2800)) -> str:
    """TSV như ``tesseract … tsv``: words = (block, par, line, left, top, width, height, conf, text)."""
    head = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [head, f"1\t1\t0\t0\t0\t0\t0\t0\t{size[0]}\t{size[1]}\t-1\t"]
    seen = set()
    for n, (block, par, line, left, top, width, height, conf, text) in enumerate(words, 1):
        if (block, par, line) not in seen:      # dòng cấu trúc level 4 (conf -1): bỏ qua khi gom
            seen.add((block, par, line))
            rows.append(f"4\t1\t{block}\t{par}\t{line}\t0\t{left}\t{top}\t500\t{height}\t-1\t")
        rows.append(f"5\t1\t{block}\t{par}\t{line}\t{n}\t{left}\t{top}\t{width}\t{height}\t{conf}\t{text}")
    return "\n".join(rows) + "\n"


def test_tsv_lines_groups_words_into_lines():
    data = tsv((1, 1, 1, 200, 100, 150, 40, 96.1, "TRƯỜNG"), (1, 1, 1, 370, 102, 100, 40, 95.0, "ĐẠI"),
               (1, 1, 1, 490, 101, 80, 40, 93.0, "HỌC"),
               (1, 1, 2, 300, 160, 80, 40, 91.0, "Số:"), (1, 1, 2, 400, 160, 200, 40, 88.5, "12/TB-ĐHM"),
               (1, 1, 2, 620, 160, 30, 40, -1, ""), (1, 1, 2, 660, 160, 30, 40, 50.0, "   "),
               (2, 1, 1, 1100, 100, 120, 40, 90.0, "CỘNG"), (2, 1, 1, 1240, 100, 100, 40, 90.0, "HÒA"))
    lines = tsv_lines([data])
    assert [ln.text for ln in lines] == ["TRƯỜNG ĐẠI HỌC", "CỘNG HÒA", "Số: 12/TB-ĐHM"]
    first, right, symbol = lines
    assert (first.x0, first.x1, first.y, first.page) == (0.1, 0.285, round(100 / 2800, 4), 1)
    assert cx(right) > 0.5 > cx(first) and symbol.y == round(160 / 2800, 4)


def test_tsv_lines_splits_two_columns_merged_into_one_line():
    data = tsv((1, 1, 1, 100, 300, 120, 40, 90, "Số:"), (1, 1, 1, 230, 300, 250, 40, 90, "131/ĐT-ĐHM"),
               (1, 1, 1, 1150, 302, 160, 40, 90, "Hà"), (1, 1, 1, 1320, 302, 120, 40, 90, "Nội,"))
    assert [(ln.text, ln.x0 < 0.5) for ln in tsv_lines([data])] == [("Số: 131/ĐT-ĐHM", True), ("Hà Nội,", False)]


def test_tsv_lines_survives_garbage_and_missing_page_size():
    assert tsv_lines(["", "rác\tkhông\tphải tsv", "5\t1\t1\t1\t1\t1\tx\t1\t1\t1\t90\tchữ",
                      "5\t1\t1\t1\t1\t1\t1\t1\t1\t1\tnan\tchữ", "5\t1\t1\t1\t1\t1\t1\t1\t1\t1\tinf\tchữ"]) == []
    no_size = "\n".join(tsv((1, 1, 1, 100, 50, 100, 40, 90, "Một"), (1, 1, 2, 100, 150, 300, 40, 90, "Hai"))
                        .splitlines()[:1] + [r for r in tsv((1, 1, 1, 100, 50, 100, 40, 90, "Một"),
                                                            (1, 1, 2, 100, 150, 300, 40, 90, "Hai")).splitlines()
                                             if r.startswith("5")])
    lines = tsv_lines(["", no_size])
    assert [(ln.text, ln.page, ln.x1, ln.y) for ln in lines] == [("Một", 2, 0.5, round(50 / 190, 4)),
                                                                ("Hai", 2, 1.0, round(150 / 190, 4))]


def test_ocr_header_through_the_rules():
    """Chữ OCR mất dấu, nhầm số: vẫn ra số ký hiệu (medium vì phải sửa O → 0), ngày, cơ quan."""
    words = [(1, 1, 1, 260, 120, 420, 45, 91, "UY BAN NHAN DAN"), (1, 1, 2, 330, 180, 260, 45, 90, "TINH MAU"),
             (1, 1, 3, 280, 260, 380, 45, 85, "S6: 1O5/TB-UBND"),
             (2, 1, 1, 1050, 120, 800, 45, 92, "CONG HOA XA HOI CHU NGHIA VIET NAM"),
             (2, 1, 2, 1150, 180, 600, 45, 90, "Doc lap - Tu do - Hanh phuc"),
             (2, 1, 3, 1080, 262, 720, 45, 88, "Mau, ngay 5 thang 10 nam 2026"),
             (3, 1, 1, 860, 420, 290, 50, 93, "THONG BAO"),
             (3, 1, 2, 560, 480, 880, 45, 90, "Lich tiep cong dan thang 11 nam 2026")]
    # mỗi "từ" ở đây là cả cụm chữ — tách ra từng từ như Tesseract
    split = []
    for block, par, line, left, top, width, height, conf, text in words:
        x = left
        for word in text.split():
            w = max(int(width * len(word) / len(text)), 10)
            split.append((block, par, line, x, top, w, height, conf, word))
            x += w + 18
    lines = tsv_lines([tsv(*split)])
    got = {k: (f.value, f.confidence) for k, f in suggest(lines, today=TODAY).fields.items()}
    assert got["symbol"] == ("105/TB-UBND", "medium")
    assert got["issued_on"] == ("2026-10-05", "high")
    assert got["issuer_name"] == ("Uy ban nhan dan tinh Mau", "medium")
    assert got["type_code"] == ("TB", "high")
    assert got["summary"] == ("Thông báo lich tiep cong dan thang 11 nam 2026", "high")


def test_line_defaults_mean_no_position():
    assert Line("Số: 1/QĐ-X") == Line("Số: 1/QĐ-X", 0.0, 1.0, 0.0, 1)
