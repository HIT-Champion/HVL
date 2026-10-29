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

"""Bộ định tuyến tất định của trợ lý (assist/route.py, #423): đường và mã lý do của các câu thử trong đặc tả, câu có từ
chỉ văn bản luôn về ``van_ban``, câu nối tiếp ghép với câu trước. Không cần dịch vụ nào."""

from __future__ import annotations

import pytest

from svc_files.assist import route, vi


def routed(question: str, *, scoped: bool = False) -> tuple[str, str, str]:
    r = route.route(vi.normalize(question), scoped=scoped)
    return r.name, r.reason, r.lang


@pytest.mark.parametrize(("question", "name", "reason"), [
    # câu về chính trợ lý, chào, cảm ơn
    ("Bạn làm được gì?", "gioi_thieu", "kw:lam-duoc-gi"),
    ("Em làm được những gì", "gioi_thieu", "kw:lam-duoc-gi"),
    ("Trợ lý có thể giúp tôi những việc gì?", "gioi_thieu", "kw:lam-duoc-gi"),
    ("Xin chào", "gioi_thieu", "kw:xin-chao"),
    ("Chào bạn!", "gioi_thieu", "kw:xin-chao"),
    ("Cảm ơn nhé", "gioi_thieu", "kw:cam-on"),
    ("Bạn là ai?", "gioi_thieu", "kw:la-ai"),
    ("Trợ lý này dùng mô hình nào?", "gioi_thieu", "kw:dung-mo-hinh"),
    ("Tôi nên hỏi bạn thế nào?", "gioi_thieu", "kw:hoi-the-nao"),
    ("Cho tôi hỏi, bạn làm được gì?", "gioi_thieu", "kw:lam-duoc-gi"),
    # cách dùng Signet
    ("Nộp đơn nghỉ phép ở đâu?", "huong_dan", "kw:o-dau"),
    ("Làm thế nào để ký số văn bản đi?", "huong_dan", "kw:lam-the-nao"),
    ("Đổi mật khẩu ở đâu?", "huong_dan", "kw:o-dau"),
    ("Hướng dẫn cách vào sổ văn bản đến", "huong_dan", "kw:huong-dan-cach"),
    # ngoài phạm vi
    ("Thời tiết Hà Nội hôm nay thế nào?", "ngoai_pham_vi", "kw:thoi-tiet"),
    ("Giá vàng hôm nay bao nhiêu?", "ngoai_pham_vi", "kw:gia-ca"),
    ("Viết giúp tôi một bài thơ", "ngoai_pham_vi", "kw:viet-ho"),
    # còn lại: tìm trong kho văn bản như trước (đường dữ liệu chưa có)
    ("Điều kiện xét học bổng khuyến khích học tập là gì?", "van_ban", "mac-dinh"),
    ("Em cần làm gì để được học bổng?", "van_ban", "mac-dinh"),
    ("Quyết định này giao việc cho ai?", "van_ban", "mac-dinh"),
    ("Có bao nhiêu văn bản đến trong tháng 10?", "van_ban", "mac-dinh"),
    ("Việc nào của tôi sắp quá hạn?", "van_ban", "mac-dinh"),
    ("Học phí năm 2026 là bao nhiêu?", "van_ban", "mac-dinh"),
    ("Thông báo về thời tiết hôm nay của nhà trường", "van_ban", "mac-dinh"),
    ("Bạn làm được gì với quy chế đào tạo?", "van_ban", "mac-dinh"),
])
def test_vietnamese_questions_take_the_expected_route(question, name, reason):
    assert routed(question) == (name, reason, "vi")


@pytest.mark.parametrize(("question", "name", "reason"), [
    ("Hello", "gioi_thieu", "kw:hello"),
    ("What can you do?", "gioi_thieu", "kw:what-can-you-do"),
    ("Who are you?", "gioi_thieu", "kw:who-are-you"),
    ("Which model do you use?", "gioi_thieu", "kw:which-model"),
    ("Thanks", "gioi_thieu", "kw:thanks"),
    ("What is the weather today?", "ngoai_pham_vi", "kw:weather"),
    ("Write me a poem", "ngoai_pham_vi", "kw:write-for-me"),
])
def test_english_questions_route_and_carry_their_language(question, name, reason):
    assert routed(question) == (name, reason, "en")


def test_in_a_document_scope_where_questions_are_about_that_document():
    assert routed("Nộp đơn nghỉ phép ở đâu?", scoped=True) == ("van_ban", "mac-dinh", "vi")
    assert routed("Bạn làm được gì?", scoped=True)[0] == "gioi_thieu"


def test_every_reason_is_a_fixed_code_never_words_of_the_question():
    # mã lý do vào sổ kiểm toán: chỉ được là mã của mẫu, không mang chữ người hỏi gõ
    codes = {f"kw:{code}" for code, _, _ in route._INTRO + route._OUT_OF_SCOPE} | {route.DEFAULT_REASON}
    for question in ("Nộp đơn nghỉ phép ở đâu?", "Hướng dẫn cách vào sổ văn bản đến", "Bấm vào đâu để đổi mật khẩu",
                     "Các bước giao việc trên phần mềm"):
        name, reason, _ = routed(question)
        assert name == "huong_dan" and route._HOW_RE.fullmatch(reason.removeprefix("kw:").replace("-", " "))
    for question in ("Xin chào", "Thời tiết Hà Nội hôm nay thế nào?", "Học phí là bao nhiêu?"):
        assert routed(question)[1] in codes


@pytest.mark.parametrize(("previous", "question", "rewritten"), [
    ("Điều kiện xét học bổng khoa CNTT là gì?", "Còn khoa Kinh tế thì sao?",
     "Điều kiện xét học bổng khoa Kinh tế là gì"),
    ("Học phí năm 2025 là bao nhiêu?", "Thế còn năm 2026?", "Học phí năm 2026 là bao nhiêu"),
    ("Quy chế đào tạo trình độ đại học ban hành năm nào?", "Nó có hiệu lực từ khi nào?",
     "Quy chế đào tạo trình độ đại học ban hành có hiệu lực từ khi nào"),
    ("Mức học bổng loại Xuất sắc là bao nhiêu?", "Thế còn loại Giỏi?", "Mức học bổng loại Giỏi là bao nhiêu"),
    # term đầu không có trong câu trước: nối vào cuối, không neo ở "thi" giữa cụm, không nhầm "tự" với "từ"
    ("Kỳ thi kết thúc học phần học kỳ I diễn ra khi nào?", "Còn hạn nộp đề thi thì sao?",
     "Kỳ thi kết thúc học phần học kỳ I diễn ra khi nào, hạn nộp đề thi"),
    ("Phòng máy mở cửa từ mấy giờ?", "Thế còn tự ý cài đặt phần mềm?",
     "Phòng máy mở cửa từ mấy giờ, tự ý cài đặt phần mềm"),
])
def test_follow_ups_are_spliced_into_a_standalone_question(previous, question, rewritten):
    assert route.follow_up(vi.normalize(question), vi.normalize(previous)) == rewritten


@pytest.mark.parametrize(("previous", "question"), [
    (None, "Còn khoa Kinh tế thì sao?"),
    ("", "Còn khoa Kinh tế thì sao?"),
    ("Điều kiện xét học bổng là gì?", "Điều kiện tốt nghiệp là gì?"),                  # câu độc lập
    ("Điều kiện xét học bổng là gì?", "Còn bao nhiêu ngày nữa thì hết hạn nộp hồ sơ?"),  # "còn" không phải nối tiếp
    ("Điều kiện xét học bổng là gì?",
     "Còn điều kiện xét học bổng của sinh viên năm nhất khoa Kinh tế hệ chất lượng cao thì sao?"),   # > 6 term
    ("Điều kiện xét học bổng là gì?", "Còn thì sao?"),                                   # không có gì để thay
])
def test_questions_that_are_not_follow_ups_stay_as_they_are(previous, question):
    assert route.follow_up(vi.normalize(question), vi.normalize(previous) if previous else None) is None


def test_a_spliced_question_longer_than_the_limit_is_dropped():
    previous = "Điều kiện " + "rất " * 130 + "khoa CNTT là gì?"
    assert route.follow_up("Còn khoa Kinh tế thì sao?", vi.normalize(previous)) is None


def test_a_follow_up_is_routed_again_after_splicing():
    rewritten = route.follow_up("Còn khoa Kinh tế thì sao?", "Điều kiện xét học bổng khoa CNTT là gì?")
    assert rewritten and routed(rewritten) == ("van_ban", "mac-dinh", "vi")
