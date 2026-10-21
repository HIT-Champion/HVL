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

"""Chữ tiếng Việt của trợ lý hỏi đáp (F4.2): chuẩn hóa, token, từ dừng, câu tìm, tách câu."""

from __future__ import annotations

import unicodedata

import pytest

from assist_fakes import PAGE_88, QUESTION, QUOTE
from svc_files.assist import vi


def texts(s: str) -> list[str]:
    return [s[a:b] for a, b in vi.sentences(s)]


# --- chuẩn hóa -----------------------------------------------------------------------------------------------------


def test_normalize_is_nfc_without_invisible_characters_on_one_line():
    nfd = unicodedata.normalize("NFD", "Điều kiện xét học bổng")
    assert vi.normalize(nfd) == "Điều kiện xét học bổng"
    assert vi.normalize("  học\u200b bổng\n\tkhuyến\u00a0khích\r\n ") == "học bổng khuyến khích"
    assert vi.normalize("khuy\u00adến khích") == "khuyến khích"          # gạch nối mềm: bỏ, không tách từ
    assert vi.normalize("a\u202eb\ufeffc") == "abc"


@pytest.mark.parametrize(("text", "expected"), [
    ("Điều kiện\nhọc bổng\t?", False), ("có\u200b ký tự vô hình", False), ("NUL\x00", True), ("ESC\x1b[31m", True),
    ("DEL\x7f", True), ("C1\x85", True),
])
def test_control_characters(text, expected):
    assert vi.has_control(text) is expected


# --- token, term ---------------------------------------------------------------------------------------------------


def test_tokens_keep_numbers_dates_and_symbols_whole():
    got = vi.tokens("Số 88/CTSV, 131/ĐT-ĐH ngày 15/11/2026: điểm 3,2; 200.000 đồng; Nghị định 12/2026/NĐ-CP, B1, 7:30.")
    assert got == ["số", "88/ctsv", "131/đt-đh", "ngày", "15/11/2026", "điểm", "3,2", "200.000", "đồng", "nghị",
                   "định", "12/2026/nđ-cp", "b1", "7:30"]


def test_stopwords_are_matched_before_removing_diacritics():
    # "có" là từ dừng, "cơ" (cơ quan) thì không; "thì" là từ dừng, "thi" (kỳ thi) thì không
    assert vi.terms("Cơ quan nào có kỳ thi thì báo?") == ["co", "quan", "ky", "thi", "bao"]


def test_terms_drop_single_letters_keep_single_digits_and_dedupe_on_folded_form():
    assert vi.terms("Học kỳ I, học KỲ 2 — hoc ky") == ["hoc", "ky", "2"]


def test_question_terms_and_keyword_query():
    assert vi.terms(QUESTION) == ["dieu", "kien", "xet", "hoc", "bong", "khuyen", "khich", "tap"]
    assert vi.keyword_query(QUESTION) == "Điều kiện xét học bổng khuyến khích tập"


def test_keyword_query_keeps_at_most_ten_terms_in_original_letters():
    q = "Một hai ba bốn năm sáu bảy tám chín mười trăm nghìn"
    words = vi.keyword_query(q).split()
    assert len(words) == 10 and words[0] == "hai" and words[1] == "ba"     # "một" là từ dừng
    assert vi.keyword_query("là gì vậy?") == ""


def test_unaccented_questions_keep_their_words():
    # câu hỏi không dấu: từ dừng có dấu không khớp, vẫn tìm được (Meilisearch tự bỏ dấu)
    assert vi.terms("TRANG2abc han nop la ngay nao") == ["trang2abc", "han", "nop", "la", "ngay", "nao"]


# --- tách câu ------------------------------------------------------------------------------------------------------


def test_sentences_split_on_end_marks_before_capitals_digits_brackets():
    s = "Câu một. Câu hai! 3 người dự; (ghi chú) thêm? Hết"
    assert texts(s) == ["Câu một.", "Câu hai!", "3 người dự;", "(ghi chú) thêm?", "Hết"]


def test_sentences_do_not_split_titles_decimals_dates_symbols():
    s = "TS. Nguyễn Văn A và PGS.TS. Trần B họp tại TP. Hồ Chí Minh, Tp. Huế. Điểm 3.5 ngày 15.11.2026 theo 88/CTSV."
    assert texts(s) == ["TS. Nguyễn Văn A và PGS.TS. Trần B họp tại TP. Hồ Chí Minh, Tp. Huế.",
                        "Điểm 3.5 ngày 15.11.2026 theo 88/CTSV."]
    assert texts("chọn sinh viên; có chứng chỉ B1. tiếp tục") == ["chọn sinh viên; có chứng chỉ B1. tiếp tục"]


def test_sentences_follow_line_breaks_of_the_pdf_text_layer():
    got = texts(PAGE_88)
    # dòng bị ngắt do dàn trang (dòng sau chữ thường, hoặc chữ số mà dòng trước chưa hết câu) nối lại thành một câu
    assert QUOTE in [" ".join(t.split()) for t in got]
    assert "Biên bản họp xét của Khoa và danh sách đề nghị gửi về Phòng trước ngày\n15/11/2026." in got
    assert "V/v xét cấp học bổng khuyến khích\nhọc tập học kỳ I năm học 2026–2027" in got
    # tiêu đề, quốc hiệu, kính gửi: mỗi dòng một câu (dòng sau chữ hoa)
    assert got[:3] == ["TRƯỜNG ĐẠI HỌC THỬ", "PHÒNG CÔNG TÁC SINH VIÊN", "Số: 88/CTSV"]
    assert "Kính gửi: Khoa Công nghệ thông tin" in got


def test_sentences_split_numbered_items_after_a_colon_and_on_blank_lines():
    s = "Lịch họp như sau:\n1. Thời gian: 14 giờ 00.\n2. Địa điểm: Phòng họp tầng 3, nhà A1.\n\nghi chú cuối"
    assert texts(s) == ["Lịch họp như sau:", "1. Thời gian: 14 giờ 00.", "2. Địa điểm: Phòng họp tầng 3, nhà A1.",
                        "ghi chú cuối"]


def test_sentence_spans_point_into_the_original_text():
    s = "  Một câu.\n\n  Câu hai  "
    assert vi.sentences(s) == [(2, 10), (14, 21)]
    assert vi.sentences("") == [] and vi.sentences(" \n ") == []
