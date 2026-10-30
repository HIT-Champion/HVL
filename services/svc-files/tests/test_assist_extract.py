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

"""Câu trích nguyên văn (F4.2): câu hỏi mẫu → đúng câu, đúng [n]; tất định; giới hạn độ dài; dấu [n] có sẵn trong
văn bản không thành trích dẫn."""

from __future__ import annotations

import re

import pytest

from assist_fakes import PAGE_88, QUESTION, QUOTE, passage
from svc_files.assist import extract

# như CITE trong apps/office/app/utils/answer.ts: giao diện dựng mọi chỗ khớp có nguồn tương ứng thành liên kết
UI_CITE = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")

PAGE_131 = (
    "Để chuẩn bị xét công nhận tốt nghiệp đợt tháng 12 năm 2026, Phòng Đào tạo đề\nnghị Khoa rà soát danh sách sinh "
    "viên dự kiến tốt nghiệp, đối chiếu đủ các điều kiện:\nhoàn thành chương trình đào tạo; đạt chuẩn đầu ra ngoại ngữ "
    "(chứng chỉ B1 theo\nKhung năng lực ngoại ngữ 6 bậc dùng cho Việt Nam); có chứng chỉ giáo dục quốc\nphòng – an "
    "ninh và chứng chỉ giáo dục thể chất.\nDanh sách gửi về Phòng Đào tạo trước ngày 10/11/2026, kèm bản chụp chứng "
    "chỉ\ncủa các trường hợp còn thiếu minh chứng."
)


def test_demo_question_quotes_the_right_sentence_with_its_source_number():
    p = passage(PAGE_88, document_id="d-88")
    got = extract.answer(QUESTION, [p])
    assert got.text == f"“{QUOTE}” [1]" and got.cited == [1]
    # dòng V/v cùng điểm nhưng chỉ nhắc lại trích yếu (đã hiện ở nguồn): xếp sau câu nội dung
    a, b = got.best[p.chunk_id]
    assert " ".join(PAGE_88[a:b].split()) == QUOTE


def test_deterministic():
    ps = [passage(PAGE_131, document_id="d-131", symbol="131/ĐT-ĐH", summary="Về việc rà soát danh sách sinh viên"),
          passage(PAGE_88, document_id="d-88")]
    first = extract.answer(QUESTION, ps)
    assert all(extract.answer(QUESTION, ps) == first for _ in range(5))


def test_number_follows_the_order_of_sources():
    ps = [passage("Biên bản hội nghị viên chức năm 2026 gửi về Phòng Tổ chức.", document_id="d-1"),
          passage(PAGE_131, document_id="d-131"), passage(PAGE_88, document_id="d-88")]
    got = extract.answer("Chuẩn đầu ra ngoại ngữ để xét tốt nghiệp là chứng chỉ gì?", ps)
    assert got.cited[0] == 2 and got.text.startswith("“hoàn thành chương trình đào tạo; đạt chuẩn đầu ra ngoại ngữ")
    assert got.text.split("\n")[0].endswith("[2]") and "chứng chỉ B1" in got.text


def test_question_about_a_deadline():
    got = extract.answer("Hạn nộp biên bản họp xét học bổng là ngày nào?", [passage(PAGE_88)])
    assert got.text == "“Biên bản họp xét của Khoa và danh sách đề nghị gửi về Phòng trước ngày 15/11/2026.” [1]"


def test_unaccented_smoke_question_finds_page_two():
    page2 = passage("TRANG2abc han nop 12/12/2026", page=2)
    got = extract.answer("TRANG2abc han nop la ngay nao", [page2])
    assert got.text == "“TRANG2abc han nop 12/12/2026” [1]"


def test_nothing_good_enough_is_none():
    p = passage(PAGE_88)
    got = extract.answer("Thủ tục cấp hộ chiếu công vụ?", [p])
    assert got.text is None and got.cited == [] and p.chunk_id in got.best
    # một term chung trên hai không đủ dù đạt tỷ lệ
    assert extract.answer("Học bổng hộ chiếu", [passage("Danh sách học sinh tiêu biểu.")]).text is None
    assert extract.answer(QUESTION, []).text is None


def test_scattered_syllables_are_not_quoted():
    # #448: term là âm tiết — câu đạt 5/7 term qua "thủ tục", "cung cấp", "công nghệ", "dịch vụ" nhưng chỉ chung
    # một cặp term liền nhau ("thủ tục") trên sáu
    p = passage("Ứng dụng công nghệ trong cung cấp dịch vụ số, gồm thủ tục hành chính trên môi trường số.")
    got = extract.answer("Thủ tục cấp hộ chiếu công vụ?", [p])
    assert got.text is None and p.chunk_id in got.best
    risk = passage("Phương án xử lý rủi ro khi triển khai công tác tuyển sinh.")
    assert extract.answer("Phương án XANH LAM là gì?", [risk]).text is None


def test_sentence_with_the_words_together_beats_a_higher_scattered_score():
    p = passage("Tiền nghỉ, tiền thuê bao, phòng tối và đa năng. "
                "Tiền thuê phòng nghỉ được thanh toán tối đa 1.200.000 đồng.")
    got = extract.answer("Tiền thuê phòng nghỉ tối đa bao nhiêu?", [p])
    assert got.text == "“Tiền thuê phòng nghỉ được thanh toán tối đa 1.200.000 đồng.” [1]"


def test_at_most_three_sentences_preferring_different_documents_and_no_duplicates():
    same = "Sinh viên xét học bổng khuyến khích học tập cần điểm từ 3,2 trở lên."
    ps = [passage(same, document_id="a", seq=1), passage(same, document_id="a", seq=2),     # đoạn chồng nhau
          passage("Học bổng khuyến khích học tập xét theo học kỳ.", document_id="a", seq=3),
          passage("Hồ sơ xét học bổng khuyến khích nộp trước 15/11.", document_id="b"),
          passage("Điều kiện xét học bổng khuyến khích gồm điểm học tập.", document_id="c"),
          passage("Mức học bổng khuyến khích học tập bằng học phí.", document_id="d")]
    got = extract.answer(QUESTION, ps)
    lines = got.text.split("\n")
    assert len(lines) == 3 and len(set(lines)) == 3
    assert sorted(got.cited) == sorted(set(got.cited))
    docs = [ps[n - 1].document_id for n in got.cited]
    assert len(set(docs)) == 3               # ba văn bản khác nhau trước khi lấy thêm câu của cùng văn bản
    assert got.cited[0] == 5                 # điểm cao nhất (6/8 term) đứng đầu


def test_long_sentence_is_clipped_around_the_match():
    filler = " ".join(["nội dung chung của văn bản"] * 30)
    sentence = f"{filler} điều kiện xét học bổng khuyến khích học tập là điểm từ 3,2 trở lên {filler}."
    got = extract.answer(QUESTION, [passage(sentence)])
    quote = got.text.removeprefix("“").removesuffix("” [1]")
    assert len(quote) <= extract.SENTENCE_CHARS and quote.startswith("…") and quote.endswith("…")
    assert "điều kiện xét học bổng khuyến khích học tập" in quote


def test_excerpt_is_one_line_around_the_best_sentence():
    p = passage(PAGE_88 + "\n" + PAGE_131 * 2)
    got = extract.answer(QUESTION, [p])
    text = extract.excerpt(p.text, got.best[p.chunk_id])
    assert len(text) <= 600 and "\n" not in text and "3,2" in text and text.endswith("…")
    assert extract.excerpt("Ngắn\ngọn.", None) == "Ngắn gọn."


def test_meta_passage_is_quoted():
    meta = passage("Công văn số 12/UBND ngày 01/10/2026 của UBND tỉnh: Về việc xét học bổng khuyến khích học tập "
                   "cho sinh viên dân tộc thiểu số", kind="meta")
    got = extract.answer(QUESTION, [meta])
    assert got.cited == [1] and got.text.startswith("“Công văn số 12/UBND")


def test_bracket_numbers_already_in_the_document_never_look_like_citations():
    text = ("Sinh viên được xét học bổng khi đăng ký tối thiểu 15 tín chỉ theo quy định [2] và Điều 5 [1, 3] của "
            "Quy chế.")
    p = passage(text, document_id="d-1")
    got = extract.answer("Đăng ký tối thiểu bao nhiêu tín chỉ để xét học bổng?",
                         [p, passage("Danh mục tài liệu kèm theo gồm năm phụ lục.", document_id="d-2")])
    assert got.text == ("“Sinh viên được xét học bổng khi đăng ký tối thiểu 15 tín chỉ theo quy định (2) và Điều 5 "
                        "(1, 3) của Quy chế.” [1]")
    # chỉ dấu do máy chủ thêm mới thành liên kết — trước đây [2] trỏ nhầm sang nguồn 2, [1, 3] thành hai liên kết
    assert UI_CITE.findall(got.text) == ["1"] and got.cited == [1]
    # đoạn trích ở danh sách nguồn (giao diện hiện như chữ, không dựng liên kết) giữ nguyên văn
    assert "[2]" in extract.excerpt(p.text, got.best[p.chunk_id])


@pytest.mark.parametrize(("raw", "want"), [
    ("theo quy định [2].", "theo quy định (2)."), ("Điều 5 [1, 3]", "Điều 5 (1, 3)"), ("[ 1;2 ]", "( 1;2 )"),
    ("[12][3]", "(12)(3)"), ("[a] [1000] [2026-1] [] (4)", "[a] [1000] [2026-1] [] (4)"),
])
def test_unmark(raw, want):
    assert extract.unmark(raw) == want and len(extract.unmark(raw)) == len(raw)
