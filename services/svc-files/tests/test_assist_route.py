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
chỉ văn bản luôn về ``van_ban``, câu nối tiếp ghép với câu trước; hai đường dữ liệu (#441) và tham số của câu đếm
(assist/data.py). Không cần dịch vụ nào."""

from __future__ import annotations

from datetime import date

import pytest

from svc_files.assist import data, route, vi


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
    ("Bạn có thể giúp gì cho tôi?", "gioi_thieu", "kw:lam-duoc-gi"),              # "gì" trước người được giúp
    ("Em làm được gì cho mình không?", "gioi_thieu", "kw:lam-duoc-gi"),
    ("hello em", "gioi_thieu", "kw:xin-chao"),                                    # chào tiếng Anh, gọi tiếng Việt
    ("Hi bạn ơi", "gioi_thieu", "kw:xin-chao"),
    ("Em ơi", "gioi_thieu", "kw:xin-chao"),
    ("Chào em nhé", "gioi_thieu", "kw:xin-chao"),
    ("Tôi cần giúp đỡ", "gioi_thieu", "kw:can-giup"),
    ("Giúp tôi với", "gioi_thieu", "kw:can-giup"),
    # cách dùng Signet
    ("Nộp đơn nghỉ phép ở đâu?", "huong_dan", "kw:o-dau"),
    ("Làm thế nào để ký số văn bản đi?", "huong_dan", "kw:lam-the-nao"),
    ("Đổi mật khẩu ở đâu?", "huong_dan", "kw:o-dau"),
    ("Hướng dẫn cách vào sổ văn bản đến", "huong_dan", "kw:huong-dan-cach"),
    ("Văn bản đến ở đâu?", "huong_dan", "kw:o-dau"),
    # "Hướng dẫn" là loại văn bản (HD); câu nhắc số ký hiệu, "số N" là câu về văn bản dù có "ở đâu"
    ("Hướng dẫn số 12/HD-ĐHM về nghỉ phép quy định gì?", "van_ban", "mac-dinh"),
    ("Hướng dẫn nghỉ phép năm 2026 của trường", "van_ban", "mac-dinh"),
    ("Quyết định giao việc số 45/QĐ-ĐHM ở đâu?", "van_ban", "mac-dinh"),
    ("Công văn số 88 nộp đơn nghỉ phép ở đâu?", "van_ban", "mac-dinh"),
    # ngoài phạm vi
    ("Thời tiết Hà Nội hôm nay thế nào?", "ngoai_pham_vi", "kw:thoi-tiet"),
    ("Giá vàng hôm nay bao nhiêu?", "ngoai_pham_vi", "kw:gia-ca"),
    ("Viết giúp tôi một bài thơ", "ngoai_pham_vi", "kw:viet-ho"),
    # việc của chính người hỏi, đếm văn bản (#441)
    ("Việc nào của tôi sắp quá hạn?", "viec_cua_toi", "kw:viec-cua-toi"),
    ("Có việc nào của mình đến hạn hôm nay không?", "viec_cua_toi", "kw:viec-cua-toi"),
    ("Tôi có bao nhiêu việc quá hạn?", "viec_cua_toi", "kw:toi-co-viec"),
    ("Tôi được giao những việc gì?", "viec_cua_toi", "kw:duoc-giao"),
    ("Hộp việc còn bao nhiêu việc quá hạn?", "viec_cua_toi", "kw:hop-viec"),
    ("Có bao nhiêu văn bản đến trong tháng 10?", "dem_van_ban", "kw:dem-van-ban"),
    ("Thống kê số văn bản đi năm 2026", "dem_van_ban", "kw:dem-van-ban"),
    ("Tháng trước có mấy công văn đến?", "dem_van_ban", "kw:dem-van-ban"),
    ("Số văn bản đi tháng 9/2026", "dem_van_ban", "kw:dem-van-ban"),          # ngày tháng không phải số ký hiệu
    ("Có bao nhiêu quy chế ban hành năm 2026?", "dem_van_ban", "kw:dem-van-ban"),
    ("Đếm số văn bản đến tháng 10", "dem_van_ban", "kw:dem-van-ban"),
    # không phải việc của người hỏi, không phải câu đếm, hay mốc thời gian chưa đọc được: tìm như trước
    ("Tôi phải làm những việc gì khi nghỉ phép?", "van_ban", "mac-dinh"),
    ("Hạn nộp hồ sơ học bổng của tôi là khi nào?", "van_ban", "mac-dinh"),
    ("Tối nay có việc gì không?", "van_ban", "mac-dinh"),                      # "tối" không phải "tôi"
    ("Có bao nhiêu sinh viên được học bổng?", "van_ban", "mac-dinh"),
    ("Quyết định 15/QĐ-ĐHM có bao nhiêu văn bản kèm theo?", "van_ban", "mac-dinh"),
    ("Bao nhiêu năm theo thông tư thì được xét tốt nghiệp?", "van_ban", "mac-dinh"),  # giới từ, đơn vị ở giữa
    ("Được nghỉ bao nhiêu ngày theo thông báo nghỉ Tết?", "van_ban", "mac-dinh"),
    ("Sinh viên được miễn bao nhiêu theo quy chế?", "van_ban", "mac-dinh"),
    ("Mấy giờ thì văn bản được phát hành?", "van_ban", "mac-dinh"),
    ("Đêm qua có văn bản nào hỏa tốc không?", "van_ban", "mac-dinh"),      # "đêm" không phải "đếm"
    ("Máy chủ lưu văn bản ở đâu?", "van_ban", "mac-dinh"),                 # "máy" không phải "mấy"
    ("Có bao nhiêu văn bản đến từ ngày 1/10/2026?", "van_ban", "mac-dinh"),
    ("Có bao nhiêu văn bản đến từ tháng 9 đến tháng 10?", "van_ban", "mac-dinh"),
    ("Có bao nhiêu văn bản đến trong quý 3?", "van_ban", "mac-dinh"),
    ("Hộp việc ở đâu?", "huong_dan", "kw:o-dau"),
    # còn lại: tìm trong kho văn bản như trước
    ("Điều kiện xét học bổng khuyến khích học tập là gì?", "van_ban", "mac-dinh"),
    ("Em cần làm gì để được học bổng?", "van_ban", "mac-dinh"),
    ("Quyết định này giao việc cho ai?", "van_ban", "mac-dinh"),
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
    ("Which of my tasks are almost overdue?", "viec_cua_toi", "kw:my-tasks"),
    ("How many incoming documents arrived this month?", "dem_van_ban", "kw:how-many"),
])
def test_english_questions_route_and_carry_their_language(question, name, reason):
    assert routed(question) == (name, reason, "en")


def test_in_a_document_scope_where_questions_are_about_that_document():
    assert routed("Nộp đơn nghỉ phép ở đâu?", scoped=True) == ("van_ban", "mac-dinh", "vi")
    assert routed("Có bao nhiêu văn bản đến trong tháng 10?", scoped=True) == ("van_ban", "mac-dinh", "vi")
    assert routed("Bạn làm được gì?", scoped=True)[0] == "gioi_thieu"


def test_every_reason_is_a_fixed_code_never_words_of_the_question():
    # mã lý do vào sổ kiểm toán: chỉ được là mã của mẫu, không mang chữ người hỏi gõ
    patterns = route._INTRO + route._OUT_OF_SCOPE + route._MY_TASKS + route._COUNT + route._COUNT_MARKED
    codes = {f"kw:{code}" for code, _, _ in patterns} | {route.DEFAULT_REASON, route.NO_GUIDE_REASON}
    for question in ("Nộp đơn nghỉ phép ở đâu?", "Hướng dẫn cách vào sổ văn bản đến", "Bấm vào đâu để đổi mật khẩu",
                     "Các bước giao việc trên phần mềm"):
        name, reason, _ = routed(question)
        assert name == "huong_dan" and route._HOW_RE.fullmatch(reason.removeprefix("kw:").replace("-", " "))
    for question in ("Xin chào", "Thời tiết Hà Nội hôm nay thế nào?", "Học phí là bao nhiêu?",
                     "Việc nào của tôi sắp quá hạn?", "Có bao nhiêu văn bản đến trong tháng 10?"):
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
    # cụm bị thay dừng trước động từ "quy định", không nuốt nó
    ("Quy chế đào tạo trình độ đại học quy định gì về học phần?", "Còn trình độ thạc sĩ thì sao?",
     "Quy chế đào tạo trình độ thạc sĩ quy định gì về học phần"),
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


def test_a_follow_up_on_a_count_is_counted_again():
    rewritten = route.follow_up("Còn tháng 9 thì sao?", "Có bao nhiêu văn bản đến trong tháng 10?")
    assert rewritten == "Có bao nhiêu văn bản đến trong tháng 9"
    assert routed(rewritten) == ("dem_van_ban", "kw:dem-van-ban", "vi")


TODAY = date(2026, 10, 30)


@pytest.mark.parametrize(("question", "directions", "start", "end", "type_code"), [
    ("Có bao nhiêu văn bản đến trong tháng 10?", ("in",), "2026-10-01", "2026-11-01", None),
    ("Có bao nhiêu văn bản đến trong tháng này?", ("in",), "2026-10-01", "2026-11-01", None),
    ("Tháng trước có mấy công văn đến?", ("in",), "2026-09-01", "2026-10-01", "CV"),
    ("Số văn bản đi tháng 12/2025", ("out",), "2025-12-01", "2026-01-01", None),
    ("Có bao nhiêu văn bản đi tháng 2 năm 2026?", ("out",), "2026-02-01", "2026-03-01", None),
    ("Thống kê số văn bản đi năm 2026", ("out",), "2026-01-01", "2027-01-01", None),
    ("Có bao nhiêu quyết định ban hành năm nay?", ("out",), "2026-01-01", "2027-01-01", "QĐ"),
    ("Năm ngoái nhận được bao nhiêu văn bản?", ("in",), "2025-01-01", "2026-01-01", None),
    ("Hôm nay có bao nhiêu văn bản đến?", ("in",), "2026-10-30", "2026-10-31", None),
    ("Có bao nhiêu văn bản?", ("in", "out"), None, None, None),
    ("Có bao nhiêu thông báo trong tháng 13?", ("in", "out"), None, None, "TB"),       # tháng sai: không lọc ngày
    ("How many incoming documents arrived this month?", ("in",), "2026-10-01", "2026-11-01", None),
    ("How many decisions were issued in May 2026?", ("out",), "2026-05-01", "2026-06-01", "QĐ"),
])
def test_count_questions_read_direction_period_and_type(question, directions, start, end, type_code):
    q = data.count_query(route.folded(question), TODAY)
    assert (q.directions, q.type_code) == (directions, type_code)
    assert (q.period.start.isoformat() if q.period else None, q.period.end.isoformat() if q.period else None) == \
        (start, end)


def test_incoming_is_counted_by_registration_time_outgoing_by_issue_date():
    q = data.count_query(route.folded("Có bao nhiêu văn bản trong tháng 10?"), TODAY)
    assert data.where("in", q) == {"_and": [
        {"direction": {"_eq": "in"}},
        {"registered_at": {"_gte": "2026-10-01T00:00:00+07:00", "_lt": "2026-11-01T00:00:00+07:00"}}]}
    assert data.where("out", q) == {"_and": [
        {"direction": {"_eq": "out"}}, {"issued_on": {"_gte": "2026-10-01", "_lt": "2026-11-01"}}]}
    typed = data.count_query(route.folded("Có bao nhiêu công văn đến?"), TODAY)
    assert data.where("in", typed) == {"_and": [{"direction": {"_eq": "in"}}, {"type_code": {"_eq": "CV"}}]}


@pytest.mark.parametrize("question", [
    "bạn có thể giups gì cho tôi?",         # gõ sai: không mẫu nào khớp
    "alo alo",
    "ok",
    "tôi không biết hỏi gì",
])
def test_short_unmatched_questions_without_evidence_fall_back_to_the_intro(question):
    q = vi.normalize(question)
    chosen = route.route(q)
    assert (chosen.name, chosen.reason) == ("van_ban", "mac-dinh")
    caught = route.fallback(q, chosen)
    assert caught is not None and (caught.name, caught.reason) == ("gioi_thieu", "luoi-an-toan")


@pytest.mark.parametrize(("question", "kwargs"), [
    ("Điều kiện xét học bổng là gì?", {}),                      # có từ chỉ văn bản
    ("Lịch thi học kỳ 1 năm 2026", {}),                         # có số
    ("Tôi phải chuẩn bị những gì cho buổi bảo vệ đồ án cuối khóa?", {}),   # dài hơn 8 term
    ("lịch thi", {"scoped": True}),                             # hỏi trong một văn bản
    ("lịch thi", {"filtered": True}),                           # đang lọc loại, năm, chiều
])
def test_the_fallback_leaves_real_document_questions_as_no_evidence(question, kwargs):
    q = vi.normalize(question)
    assert route.fallback(q, route.route(q), **kwargs) is None


def test_the_fallback_only_catches_the_default_route():
    for chosen in (route.Route("van_ban", route.NO_GUIDE_REASON), route.Route("huong_dan", "kw:o-dau"),
                   route.Route("gioi_thieu", "kw:xin-chao")):
        assert route.fallback("lịch thi", chosen) is None
