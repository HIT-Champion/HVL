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


"""Quy tắc trích thông tin tiếp nhận (F4.1): mọi ví dụ của thiết kế, kể cả ca âm, và hiệu năng regex."""

from __future__ import annotations

import time
import unicodedata
from datetime import date

import pytest

from svc_files.docread.layout import Line
from svc_files.docread.rules import CATALOG, MAX_BODY, Field, fold, suggest, title_case

TODAY = date(2026, 10, 21)
# Vị trí cột trên trang (0..1): trái là cơ quan, số ký hiệu; phải là quốc hiệu, ngày; giữa là tên loại; thân rộng cả trang
COLS = {"L": (0.05, 0.40), "R": (0.55, 0.95), "C": (0.30, 0.70), "B": (0.0, 0.99)}


def page(*rows, dy: float = 0.03, number: int = 1) -> list[Line]:
    """Mỗi hàng: (cột, chữ), danh sách (cột, chữ) cùng hàng, hoặc None (dòng trống)."""
    lines = []
    for i, row in enumerate(rows):
        if row is None:
            continue
        for col, text in row if isinstance(row, list) else [row]:
            x0, x1 = COLS[col]
            lines.append(Line(text, x0, x1, round(0.02 + i * dy, 4), number))
    return lines


MOTTO = ("R", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
MOTTO2 = ("R", "Độc lập - Tự do - Hạnh phúc")
DATE_LINE = ("R", "Hà Nội, ngày 15 tháng 10 năm 2026")
BODY = [("C", "Kính gửi: Khoa Công nghệ thông tin"), None,
        ("B", "Thực hiện kế hoạch năm học 2026–2027, Phòng Đào tạo đề nghị Khoa rà soát danh sách sinh viên."),
        ("B", "Danh sách gửi về Phòng Đào tạo trước ngày 10/11/2026 để tổng hợp, báo cáo Ban Giám hiệu.")]


def letter(*, issuer=("TRƯỜNG ĐẠI HỌC MẪU",), symbol="Số: 123/CV-ĐHM", date_line=DATE_LINE, below=(), body=BODY,
           **kw) -> list[Line]:
    """Phần đầu theo NĐ 30: cơ quan (1–2 dòng) + quốc hiệu cùng hàng, số ký hiệu + ngày cùng hàng."""
    rows: list = [[("L", issuer[0]), MOTTO]]
    rows += [[("L", text), MOTTO2] if i == 0 else ("L", text) for i, text in enumerate(issuer[1:])]
    if len(issuer) == 1:
        rows.append(MOTTO2)
    rows.append([("L", symbol), date_line] if date_line else ("L", symbol))
    rows += list(below) + [None] + list(body)
    return page(*rows, **kw)


def fields(lines, **kw) -> dict[str, tuple[str, str]]:
    got = suggest(lines, today=kw.pop("today", TODAY), **kw)
    return {k: (f.value, f.confidence) for k, f in got.fields.items()}


def test_fold_drops_vietnamese_marks_and_keeps_the_length():
    text = unicodedata.normalize("NFC", "Số: 123/QĐ-UBND · Hà Nội, ngày 15 tháng 10 năm 2026 · ỦY BAN NHÂN DÂN đường Ưng Ỷ")
    folded = fold(text)
    assert len(folded) == len(text)
    assert folded == "So: 123/QD-UBND · Ha Noi, ngay 15 thang 10 nam 2026 · UY BAN NHAN DAN duong Ung Y"


# --- 1. Số, ký hiệu ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("printed", "value", "confidence"), [
    ("Số: 123/QĐ-UBND", "123/QĐ-UBND", "high"),
    ("Số: 45/2026/TT-BTC", "45/2026/TT-BTC", "high"),
    ("Số: 07/CV-ĐHCN", "07/CV-ĐHCN", "high"),
    ("Số: 08/TTr-KCNTT", "08/TTr-KCNTT", "high"),
    ("Số: 57/KT&ĐBCL", "57/KT&ĐBCL", "high"),
    ("Số: 05/2026/NĐ-CP", "05/2026/NĐ-CP", "high"),
    ("Số: 12 /QĐ - UBND", "12/QĐ-UBND", "high"),
    ("SỐ: 128/TB–ĐHM.", "128/TB-ĐHM", "high"),              # chữ in hoa, gạch ngang dài, dấu câu cuối
    ("S6: 1O5/TB-ĐHM", "105/TB-ĐHM", "medium"),              # OCR: "Số" thành "S6", số 0 thành chữ O
    ("Số: 1O5/TB-ĐHM", "105/TB-ĐHM", "medium"),
    ("So: 99/TB-SMOKE", "99/TB-SMOKE", "high"),               # ASCII
    ("123/QĐ-UBND", "123/QĐ-UBND", "medium"),                 # mẫu trần, không có "Số"
])
def test_symbol_examples(printed, value, confidence):
    assert fields(letter(symbol=printed))["symbol"] == (value, confidence)


def test_symbol_in_the_body_is_not_taken():
    head = letter(symbol="Kính gửi các đơn vị", body=[])
    body = [Line("Thực hiện Công văn số 47/KHCN-ĐT của Phòng Khoa học, Khoa đề nghị các bộ môn rà soát.", 0, 0.99, 0.5),
            Line("Số: 47/KHCN-ĐT", 0.05, 0.4, 0.6), Line("47/KHCN-ĐT", 0.05, 0.4, 0.7)]
    assert "symbol" not in fields(head + body)      # ngoài vùng đầu (y ≥ 0.45) không lấy, kể cả có "Số"
    # trong vùng đầu: mẫu trần giữa câu của phần thân cũng không lấy
    near = letter(symbol="Kính gửi các đơn vị", body=[("B", "Theo Công văn 47/KHCN-ĐT, hạn nộp là cuối tháng 10.")])
    assert "symbol" not in fields(near)


def test_lowercase_so_inside_a_sentence_in_the_head_is_not_the_symbol():
    lines = page([("L", "TRƯỜNG ĐẠI HỌC MẪU"), MOTTO],
                 ("B", "Theo công văn số 47/KHCN của Phòng Khoa học"))
    assert "symbol" not in fields(lines)


def test_symbol_without_number_is_not_suggested():
    got = suggest(letter(symbol="Số:   /QĐ-UBND"), today=TODAY)
    assert "symbol" not in got.fields and "symbol_no_number" in got.warnings
    got = suggest(letter(symbol="Số: ......./QĐ-UBND"), today=TODAY)
    assert "symbol" not in got.fields and "symbol_no_number" in got.warnings


def test_symbol_prefers_the_left_column_and_caps_the_length():
    lines = letter(symbol="Số: 12/QĐ-UBND", date_line=("R", "Số: 99/TB-KHAC"))
    assert fields(lines)["symbol"] == ("12/QĐ-UBND", "high")
    long = "Số: 12345/2026/ABCDEFGHIJKL-ABCDEFGHIJKL-ABCDEFGHIJKL-ABCDEFGHIJKL"
    assert "symbol" not in fields(letter(symbol=long))


# --- 2. Ngày ban hành -------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("printed", "value", "confidence"), [
    ("Hà Nội, ngày 15 tháng 10 năm 2026", "2026-10-15", "high"),
    ("TP. Hồ Chí Minh, ngày 01 tháng 02 năm 2026", "2026-02-01", "high"),
    ("Ha Noi, ngay 5 thang 10 nam 2026", "2026-10-05", "high"),         # OCR mất dấu
    ("Mẫu, ngày 30 tháng 9 năm 2026", "2026-09-30", "high"),
    ("ngày 15 tháng 10 năm 2026", "2026-10-15", "medium"),              # không có địa danh
    ("Hà Nội, ngày 15/10/2026", "2026-10-15", "medium"),
])
def test_issued_on_examples(printed, value, confidence):
    assert fields(letter(date_line=("R", printed)))["issued_on"] == (value, confidence)


def test_date_in_the_body_is_not_the_issue_date():
    lines = letter(date_line=None, body=[
        ("C", "Kính gửi: Khoa Công nghệ thông tin"),
        ("B", "Đề nghị gửi báo cáo trước ngày 10/11/2026."),
        ("B", "Hội nghị họp vào ngày 20 tháng 10 năm 2026 tại phòng họp tầng 3."),
    ])
    got = suggest(lines, today=TODAY)
    assert "issued_on" not in got.fields and not got.warnings


def test_date_prefers_the_right_column():
    lines = letter(below=[("L", "ngày 01 tháng 01 năm 2026")])
    assert fields(lines)["issued_on"] == ("2026-10-15", "high")


def test_impossible_date_is_dropped_with_a_warning():
    got = suggest(letter(date_line=("R", "Hà Nội, ngày 31 tháng 02 năm 2026")), today=TODAY)
    assert "issued_on" not in got.fields and "invalid_date" in got.warnings


def test_future_date_is_only_a_low_suggestion():
    got = suggest(letter(date_line=("R", "Hà Nội, ngày 25 tháng 10 năm 2026")), today=TODAY)
    assert got.fields["issued_on"] == Field("2026-10-25", "low") and "future_date" in got.warnings
    assert suggest(letter(), today=date(2026, 10, 15)).fields["issued_on"].confidence == "high"


# --- 3. Cơ quan ban hành ----------------------------------------------------------------------------------------

@pytest.mark.parametrize(("issuer", "value", "confidence"), [
    (("TRƯỜNG ĐẠI HỌC MẪU",), "Trường Đại học Mẫu", "high"),
    (("ỦY BAN NHÂN DÂN", "TỈNH MẪU"), "Ủy ban nhân dân tỉnh Mẫu", "medium"),
    (("UBND TỈNH MẪU", "SỞ KHOA HỌC VÀ CÔNG NGHỆ"), "Sở Khoa học và Công nghệ tỉnh Mẫu", "medium"),
    (("TRƯỜNG ĐẠI HỌC MẪU", "PHÒNG ĐÀO TẠO"), "Phòng Đào tạo", "medium"),
    (("BỘ GIÁO DỤC VÀ ĐÀO TẠO", "TRƯỜNG ĐẠI HỌC MẪU"), "Trường Đại học Mẫu", "medium"),
    (("CÔNG TY CỔ PHẦN", "CÔNG NGHỆ MẪU"), "Công ty Cổ phần Công nghệ Mẫu", "medium"),     # tên dài xuống dòng
    (("SỞ GIÁO DỤC VÀ", "ĐÀO TẠO TỈNH MẪU"), "Sở Giáo dục và Đào tạo tỉnh Mẫu", "medium"),
    (("UBND TỈNH MẪU", "------", "SỞ GIÁO DỤC VÀ ĐÀO TẠO"), "Sở Giáo dục và Đào tạo tỉnh Mẫu", "medium"),
])
def test_issuer_examples(issuer, value, confidence):
    assert fields(letter(issuer=issuer))["issuer_name"] == (value, confidence)


def test_issuer_skips_the_national_motto_on_the_same_row():
    assert fields(letter())["issuer_name"] == ("Trường Đại học Mẫu", "high")
    # hai cột không tách được (cách nhau ít khoảng trắng): cắt quốc hiệu khỏi dòng, còn cơ quan — chỉ medium
    merged = page(("B", "TRƯỜNG ĐẠI HỌC MẪU CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
                  ("B", "Độc lập - Tự do - Hạnh phúc"),
                  [("L", "Số: 12/TB-ĐHM"), DATE_LINE])
    assert fields(merged)["issuer_name"] == ("Trường Đại học Mẫu", "medium")


def test_without_coordinates_the_motto_is_cut_from_the_same_line():
    lines = [Line(t) for t in ("TRƯỜNG ĐẠI HỌC MẪU CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
                               "PHÒNG ĐÀO TẠO Độc lập - Tự do - Hạnh phúc", "Số: 131/ĐT-ĐHM",
                               "Hà Nội, ngày 15 tháng 10 năm 2026")]
    got = fields(lines)
    assert got["issuer_name"] == ("Phòng Đào tạo", "medium")
    assert got["symbol"] == ("131/ĐT-ĐHM", "high") and got["issued_on"] == ("2026-10-15", "high")


@pytest.mark.parametrize(("upper", "proper"), [
    ("ỦY BAN NHÂN DÂN TỈNH MẪU", "Ủy ban nhân dân tỉnh Mẫu"),
    ("UBND THÀNH PHỐ HỒ CHÍ MINH", "UBND thành phố Hồ Chí Minh"),
    ("HĐND HUYỆN MẪU SƠN", "HĐND huyện Mẫu Sơn"),
    ("SỞ GD&ĐT TỈNH MẪU", "Sở GD&ĐT tỉnh Mẫu"),
    ("ĐẠI HỌC QUỐC GIA HÀ NỘI", "Đại học Quốc gia Hà Nội"),
    ("KHOA CÔNG NGHỆ THÔNG TIN", "Khoa Công nghệ thông tin"),
    ("SỞ LAO ĐỘNG - THƯƠNG BINH VÀ XÃ HỘI", "Sở Lao động - Thương binh và Xã hội"),
    ("CÔNG TY TNHH PHẦN MỀM MẪU", "Công ty TNHH Phần mềm Mẫu"),
    ("BAN QUẢN LÝ DỰ ÁN MẪU", "Ban Quản lý Dự án Mẫu"),
    ("PHÂN HIỆU TẠI TP. HỒ CHÍ MINH", "Phân hiệu tại TP. Hồ Chí Minh"),
])
def test_title_case(upper, proper):
    assert title_case(upper) == proper


# --- 4. Loại văn bản --------------------------------------------------------------------------------------------

def test_type_from_the_title_line():
    lines = letter(symbol="Số: 123/QĐ-UBND", below=[None, ("C", "QUYẾT ĐỊNH"),
                                                    ("C", "Về việc ban hành Quy chế văn thư")])
    assert fields(lines)["type_code"] == ("QĐ", "high")


def test_spaced_title_is_read_without_spaces():
    lines = letter(symbol="Số: 12/TB-ĐHM", below=[None, [("C", "T H Ô N G"), ("C", "B Á O")]])
    assert fields(lines)["type_code"] == ("TB", "high")


def test_title_and_symbol_disagree():
    got = suggest(letter(symbol="Số: 12/QĐ-ĐHM", below=[None, ("C", "THÔNG BÁO")]), today=TODAY)
    assert got.fields["type_code"] == Field("TB", "medium") and "type_conflict" in got.warnings


def test_vv_without_title_is_a_cong_van():
    lines = letter(symbol="Số: 131/ĐT-ĐHM", below=[("L", "V/v rà soát danh sách sinh viên")])
    assert fields(lines)["type_code"] == ("CV", "high")


def test_type_from_the_symbol_only():
    assert fields(letter(symbol="Số: 123/QĐ-UBND", body=[]))["type_code"] == ("QĐ", "medium")
    assert fields(letter(symbol="Số: 45/2026/KH-UBND", body=[]))["type_code"] == ("KH", "medium")
    assert "type_code" not in fields(letter(symbol="Số: 57/KT&ĐBCL", body=[]))


def test_only_codes_in_the_catalog_are_returned():
    lines = letter(symbol="Số: 123/QĐ-UBND", below=[None, ("C", "QUYẾT ĐỊNH")])
    assert "type_code" not in fields(lines, type_codes=["CV", "TB"])
    thong_tu = letter(symbol="Số: 45/2026/TT-BTN", below=[None, ("C", "THÔNG TƯ"),
                                                          ("C", "Quy định kỹ thuật về số hóa tài liệu lưu trữ")])
    got = fields(thong_tu, type_codes=CATALOG)
    assert "type_code" not in got        # Thông tư chưa có trong danh mục office.document_types
    assert got["summary"] == ("Thông tư quy định kỹ thuật về số hóa tài liệu lưu trữ", "high")


# --- 5. Trích yếu -----------------------------------------------------------------------------------------------

def test_summary_from_vv_on_two_lines_ignores_the_right_column():
    lines = page([("L", "TRƯỜNG ĐẠI HỌC MẪU"), MOTTO],
                 [("L", "PHÒNG ĐÀO TẠO"), MOTTO2],
                 [("L", "Số: 131/ĐT-ĐHM"), DATE_LINE],
                 [("L", "V/v rà soát danh sách sinh viên đủ"), ("R", "(dòng phụ ở cột phải)")],
                 ("L", "điều kiện xét tốt nghiệp đợt tháng 12"),
                 None,
                 ("C", "Kính gửi: Khoa Công nghệ thông tin"))
    assert fields(lines)["summary"] == ("Về việc rà soát danh sách sinh viên đủ điều kiện xét tốt nghiệp đợt tháng 12",
                                        "high")


def test_vv_stops_at_a_blank_line_and_at_the_urgency_stamp():
    lines = letter(below=[("L", "V/v triển khai hệ thống văn bản"), ("L", "điện tử năm 2026"), None,
                          ("L", "Không phải trích yếu")])
    assert fields(lines)["summary"][0] == "Về việc triển khai hệ thống văn bản điện tử năm 2026"
    lines = letter(below=[("L", "V/v: triển khai hệ thống văn bản"), ("L", "KHẨN")])
    got = fields(lines)
    assert got["summary"][0] == "Về việc triển khai hệ thống văn bản" and got["urgency"] == ("khan", "high")


def test_summary_after_the_title():
    lines = letter(symbol="Số: 123/QĐ-UBND", below=[
        None, ("C", "QUYẾT ĐỊNH"), ("C", "Về việc ban hành Quy chế quản lý, sử dụng"),
        ("C", "hệ thống văn phòng điện tử"), ("C", "CHỦ TỊCH ỦY BAN NHÂN DÂN TỈNH MẪU"),
        ("B", "Căn cứ Luật Tổ chức chính quyền địa phương;")], body=[])
    assert fields(lines)["summary"] == ("Quyết định về việc ban hành Quy chế quản lý, sử dụng hệ thống văn phòng điện tử",
                                        "high")
    lines = letter(symbol="Số: 12/TB-ĐHM", below=[None, ("C", "THÔNG BÁO"),
                                                  ("C", "Lịch đăng ký học phần học kỳ II năm học 2026–2027")])
    assert fields(lines)["summary"] == ("Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027", "high")
    lines = letter(symbol="Số: 12/TB-ĐHM", below=[None, ("C", "THÔNG BÁO"),
                                                  ("C", "Lịch đăng ký học phần học kỳ II năm học"), ("C", "2026–2027")])
    assert fields(lines)["summary"][0] == "Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027"
    lines = letter(symbol="Số: 12/TB-ĐHM", below=[None, ("C", "THÔNG BÁO"), ("C", "ĐHCN tuyển sinh năm 2027")])
    assert fields(lines)["summary"][0] == "Thông báo ĐHCN tuyển sinh năm 2027"


def test_body_paragraph_after_the_title_is_not_its_summary():
    lines = letter(symbol="Số: 12/TB-ĐHM", below=[None, ("C", "THÔNG BÁO")], body=[
        ("B", "Thực hiện kế hoạch năm học 2026–2027, Phòng Đào tạo thông báo lịch họp giao ban. Đề nghị các đơn vị"),
        ("B", "cử đại diện tham dự đầy đủ, đúng giờ.")])
    got = fields(lines)
    assert got["type_code"] == ("TB", "high")
    assert got["summary"] == ("Thực hiện kế hoạch năm học 2026–2027, Phòng Đào tạo thông báo lịch họp giao ban", "low")


def test_summary_from_the_first_sentence_is_low():
    long = "Công ty Cổ phần Công nghệ Mẫu trân trọng kính mời đại diện lãnh đạo Khoa " + "tham dự hội thảo " * 20
    lines = letter(symbol="Số: 209/GM-CNM", below=[None, ("C", "GIẤY MỜI")], body=[
        ("C", "Kính gửi:"), ("C", "- Khoa Công nghệ thông tin;"), ("C", "- Phòng Đào tạo."),
        ("B", "Công ty Cổ phần Công nghệ Mẫu trân trọng kính mời đại diện lãnh đạo Khoa tham dự hội thảo."
              " Thời gian: 8 giờ.")])
    value, confidence = fields(lines)["summary"]
    assert (value, confidence) == ("Công ty Cổ phần Công nghệ Mẫu trân trọng kính mời đại diện lãnh đạo Khoa tham dự"
                                   " hội thảo", "low")
    value, _ = fields(letter(body=[("C", "Kính gửi: Khoa"), ("B", long)]))["summary"]
    assert len(value) <= 200 and long.startswith(value) and not value.endswith(" ")


def test_too_short_summaries_are_dropped():
    assert "summary" not in fields(letter(below=[("L", "V/v")], body=[]))
    assert "summary" not in fields(letter(body=[("C", "Kính gửi: Khoa"), ("B", "Đề nghị.")]))


# --- 6. Độ khẩn -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("stamp", "value"), [("KHẨN", "khan"), ("THƯỢNG KHẨN", "thuong_khan"),
                                              ("HỎA TỐC", "hoa_toc"), ("HOẢ TỐC", "hoa_toc"), ("| KHAN |", "khan")])
def test_urgency_stamp(stamp, value):
    assert fields(letter(below=[("L", stamp)]))["urgency"] == (value, "high")


def test_khan_truong_in_the_text_is_not_urgency():
    lines = letter(below=[("B", "Đề nghị các đơn vị khẩn trương triển khai.")],
                   body=[("B", "Việc này cần làm khẩn."), ("C", "Khẩn trương")])
    assert "urgency" not in fields(lines)


# --- 7. Cảnh báo, phần thân, đầu vào bất thường -----------------------------------------------------------------

def test_low_text_and_empty_input():
    got = suggest([Line("Số: 1/QĐ-X")], today=TODAY)
    assert "low_text" in got.warnings
    empty = suggest([], today=TODAY)
    assert (empty.fields, empty.warnings, empty.body) == ({}, ("low_text",), "")


def test_body_starts_after_the_greeting_and_is_capped():
    got = suggest(letter(body=[("C", "Kính gửi: Khoa Công nghệ thông tin")] + [("B", "Nội dung " * 20)] * 60),
                  today=TODAY)
    assert got.body.startswith("Nội dung") and len(got.body) == MAX_BODY and "Kính gửi" not in got.body


def test_long_input_is_truncated():
    got = suggest(letter() + [Line("x" * 30_000, 0.0, 0.99, 0.9)], today=TODAY)
    assert "truncated" in got.warnings and got.fields["symbol"].value == "123/CV-ĐHM"


def test_odd_input_never_raises():
    odd = [Line("Số: 12/QĐ-UBND", float("nan"), float("inf"), -3.0, 0), Line("", 0.2, 0.3, 0.1, 1),
           Line("\x00​ Hà Nội,\tngày 15 tháng 10 năm 2026", 2.0, -1.0, 0.1, 1)]
    got = suggest(odd, today=TODAY)
    assert got.fields["symbol"].value == "12/QĐ-UBND"


def test_without_coordinates_a_whole_cong_van():
    plain = ("TRƯỜNG ĐẠI HỌC MẪU", "PHÒNG ĐÀO TẠO", "Số: 131/ĐT-ĐHM", "V/v rà soát danh sách sinh viên đủ",
             "điều kiện xét tốt nghiệp", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc",
             "Hà Nội, ngày 15 tháng 10 năm 2026", "KHẨN", "Kính gửi: Khoa Công nghệ thông tin",
             "Để chuẩn bị xét tốt nghiệp, Phòng Đào tạo đề nghị Khoa rà soát danh sách.")
    got = fields([Line(t) for t in plain])
    assert got == {
        "type_code": ("CV", "high"), "symbol": ("131/ĐT-ĐHM", "high"), "issued_on": ("2026-10-15", "high"),
        "issuer_name": ("Phòng Đào tạo", "medium"),
        "summary": ("Về việc rà soát danh sách sinh viên đủ điều kiện xét tốt nghiệp", "high"),
        "urgency": ("khan", "high"),
    }


# --- Hiệu năng: regex tuyến tính trên chữ đối kháng -------------------------------------------------------------

ADVERSARIAL = {
    "digits": "Số: " + "1" * 50_000,
    "slashes": "Số: 1/" * 10_000,
    "dashes": "Số: 12/QĐ" + "-A" * 25_000,
    "dates": "ngày 1 tháng 1 năm " * 2_700,
    "places": "Hà Nội, " * 7_000,
    "place-run": "A" * 50_000 + ", ngày 1",
    "spaces": "Số" + " " * 50_000 + ":",
    "vv": "V/v " * 12_500,
    "mixed": "So: 1O/2026/" + "A&-" * 16_000,
    "upper-lines": "\n".join(["ỦY BAN NHÂN DÂN TỈNH MẪU"] * 2_000),
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL))
def test_adversarial_text_is_fast(name):
    text = ADVERSARIAL[name]
    assert len(text) >= 45_000
    chunks = text.split("\n") if "\n" in text else [text[j:j + 50] for j in range(0, len(text), 50)]
    shapes = [
        [Line(text)],                                                                  # một dòng dài
        [Line(chunk, 0.05, 0.4, 0.01 + (i % 40) * 0.01) for i, chunk in enumerate(chunks)],     # nhiều dòng ngắn
    ]
    # Bắt regex bùng nổ (bậc hai trở lên: hàng giây tới hàng phút trên 50 000 ký tự), không đo hiệu năng: lấy lần nhanh
    # nhất trong 3 lần, ngưỡng 1 giây. Ngưỡng cũ 0,3 giây cho một lần đo đỏ ngẫu nhiên trên máy CI (0,34 giây, #155)
    for lines in shapes:
        best = float("inf")
        for _ in range(3):
            started = time.perf_counter()
            suggest(lines, today=TODAY)
            best = min(best, time.perf_counter() - started)
        assert best < 1.0, f"{name}: {len(lines)} dòng chậm quá ({best:.2f} giây)"
