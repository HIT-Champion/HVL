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

"""Bỏ phiếu đơn vị chủ trì và hạn (F4.3, suggest.py): hàm thuần, không cần giả lập gì."""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import pytest

from svc_workflow.suggest import (
    LEGAL_HOLIDAYS,
    MAX_DAYS,
    NO_HOLIDAYS,
    TOP_K,
    Evidence,
    Hit,
    Holidays,
    Past,
    lead_unit,
    next_workday,
    parse_holidays,
    past_days,
    suggest,
    vn_date,
)

DT, KTPM, HTTT, CTSV = "dt", "ktpm", "httt", "ctsv"  # CTSV: phòng không có lãnh đạo phòng
UNITS = {DT, KTPM, HTTT}
MONDAY = date(2026, 10, 26)


def doc(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def run(pairs: list[tuple[float, str | None, int | None]], *, units: set[str] = UNITS, min_score: float = 0.3,
        registered_on: date = MONDAY, doc_due: date | None = None, today: date = MONDAY,
        holidays: Holidays = NO_HOLIDAYS):
    """pairs: (điểm, đơn vị chủ trì lúc trước, số ngày) theo thứ tự svc-files trả."""
    hits = [Hit(doc(i), score) for i, (score, _, _) in enumerate(pairs)]
    history = {doc(i): Past(doc(i), unit, days) for i, (_, unit, days) in enumerate(pairs)}
    return suggest(hits, history, units, min_score=min_score, registered_on=registered_on, doc_due=doc_due,
                   today=today, holidays=holidays)


def test_three_agreeing_letters_give_high_confidence_and_a_typical_due_date():
    s = run([(0.9, DT, 10), (0.8, DT, 7), (0.7, DT, 12), (0.35, KTPM, 3)])
    assert (s.status, s.reason, s.department_id, s.confidence) == ("suggested", None, DT, "high")
    assert s.share == round(2.4 / 2.75, 3) and s.share >= 0.7
    assert s.due_days == 10 and s.due_on == date(2026, 11, 5)     # median_low(7, 10, 12), 26/10 + 10 = thứ Năm
    assert s.ranking == (DT, KTPM) and s.candidates == 4
    # căn cứ là mọi phiếu (cả đơn vị thua), theo điểm giảm dần
    assert [e.document_id for e in s.evidence] == [doc(0), doc(1), doc(2), doc(3)]
    assert s.evidence[3] == Evidence(doc(3), 0.35, KTPM, 3)


def test_two_letters_give_medium_one_letter_gives_low():
    s = run([(0.8, DT, 10), (0.6, DT, 10), (0.5, KTPM, 14)])
    assert (s.confidence, s.department_id, s.share) == ("medium", DT, round(1.4 / 1.9, 3))  # n = 2 < 3
    s = run([(0.9, DT, 10), (0.6, KTPM, 14), (0.3, HTTT, 5)])
    assert (s.confidence, s.department_id) == ("low", DT)       # share 0.5 nhưng chỉ một căn cứ
    s = run([(0.9, DT, 10)])
    assert (s.confidence, s.share) == ("low", 1.0)


def test_scattered_votes_give_no_suggestion_but_keep_the_ranking():
    s = run([(0.6, DT, 10), (0.55, KTPM, 14), (0.5, HTTT, 5)])
    assert (s.status, s.reason) == ("none", "low_confidence")
    assert s.ranking == (DT, KTPM, HTTT)                         # vẫn tính để đo top-k
    assert (s.department_id, s.confidence, s.share, s.due_days, s.due_on, s.evidence) == (
        None, None, None, None, None, ())


@pytest.mark.parametrize(("pairs", "winner"), [
    # cùng trọng số 1.0: đơn vị có một căn cứ điểm cao hơn thắng
    ([(0.6, KTPM, None), (0.5, DT, None), (0.5, DT, None), (0.4, KTPM, None)], KTPM),
    # vẫn hòa (cùng trọng số, cùng điểm đơn lẻ): id nhỏ hơn thắng, không phụ thuộc thứ tự svc-files trả
    ([(0.5, KTPM, None), (0.5, DT, None)], DT),
    ([(0.5, DT, None), (0.5, KTPM, None)], DT),
])
def test_ties_are_broken_by_best_single_score_then_by_id(pairs, winner):
    s = run(pairs)
    assert s.ranking[0] == winner


def test_hits_below_the_threshold_do_not_vote():
    s = run([(0.9, DT, 10), (0.29, KTPM, 3), (0.2, KTPM, 3), (0.1, KTPM, 3)])
    assert (s.department_id, s.share, s.ranking, s.candidates) == (DT, 1.0, (DT,), 4)
    assert run([(0.29, DT, 10), (0.1, DT, 10)]).reason == "no_similar"
    assert run([(0.29, DT, 10)], min_score=0.25).status == "suggested"
    assert run([(0.0, DT, 10)], min_score=0.0).reason == "no_similar"   # điểm 0 không nói gì về độ giống


def test_reasons_for_no_suggestion():
    assert run([]).reason == "no_similar"
    assert run([]).candidates == 0
    # tương tự nhưng chưa giao, hoặc không đọc được lịch sử (văn bản hạn chế bị lọc ở truy vấn lịch sử)
    assert run([(0.9, None, None), (0.8, None, None)]).reason == "no_history"
    hits = [Hit(doc(1), 0.9)]
    s = suggest(hits, {}, UNITS, min_score=0.3, registered_on=MONDAY, doc_due=None, today=MONDAY)
    assert (s.reason, s.candidates) == ("no_history", 1)
    # phòng không có lãnh đạo phòng: chỉ đạo sẽ báo no_manager, nên không gợi ý
    assert run([(0.9, CTSV, 10), (0.8, CTSV, 10), (0.7, CTSV, 10)]).reason == "no_valid_unit"


def test_units_without_a_manager_are_dropped_before_voting():
    s = run([(0.9, CTSV, 3), (0.8, DT, 10), (0.7, DT, 10), (0.6, DT, 10)])
    assert (s.department_id, s.confidence, s.share) == (DT, "high", 1.0)
    assert CTSV not in s.ranking and all(e.department_id != CTSV for e in s.evidence)


def test_lead_given_to_a_person_counts_for_their_department():
    users = {"u-staff-dt": DT, "u-manager-ktpm": KTPM}
    assert lead_unit({"department_id": KTPM, "user_id": None, "due_on": None}, users) == KTPM
    assert lead_unit({"department_id": None, "user_id": "u-staff-dt", "due_on": "2026-11-01"}, users) == DT
    assert lead_unit({"department_id": None, "user_id": "u-da-nghi", "due_on": None}, users) is None
    assert lead_unit(None, users) is None


def test_due_days_is_the_lower_median_of_the_winning_unit():
    s = run([(0.9, DT, 20), (0.85, DT, 7), (0.8, DT, 14), (0.75, DT, 10), (0.7, KTPM, 1)])
    assert s.due_days == 10                                      # median_low(20, 7, 14, 10), bỏ số ngày của KTPM
    s = run([(0.9, DT, None), (0.8, DT, 12), (0.7, DT, None)])
    assert s.due_days == 12                                      # bỏ căn cứ không có số ngày
    s = run([(0.9, DT, None), (0.8, DT, None), (0.7, DT, None)])
    assert (s.status, s.due_days, s.due_on) == ("suggested", None, None)  # vẫn gợi ý đơn vị


def test_due_date_moves_off_the_weekend_and_is_never_before_tomorrow():
    friday = date(2026, 10, 23)
    s = run([(0.9, DT, 8), (0.8, DT, 8), (0.7, DT, 8)], registered_on=friday, today=friday)
    assert s.due_days == 8 and s.due_on == date(2026, 11, 2)     # thứ Bảy 31/10 → thứ Hai 2/11
    # văn bản vào sổ đã lâu (hàng đợi bị nghẽn): hạn sớm nhất là ngày mai, vẫn là ngày làm việc
    s = run([(0.9, DT, 2), (0.8, DT, 2), (0.7, DT, 2)], registered_on=date(2026, 10, 1), today=friday)
    assert s.due_on == date(2026, 10, 26)                        # mai là thứ Bảy → thứ Hai
    s = run([(0.9, DT, 2), (0.8, DT, 2), (0.7, DT, 2)], registered_on=date(2026, 10, 1), today=MONDAY)
    assert s.due_on == date(2026, 10, 27)


def test_due_written_on_the_letter_wins_over_habit():
    s = run([(0.9, DT, 10), (0.8, DT, 10), (0.7, DT, 10)], doc_due=date(2026, 11, 20))
    assert (s.status, s.department_id, s.due_days, s.due_on) == ("suggested", DT, None, None)


@pytest.mark.parametrize(("d", "expected"), [
    (date(2026, 10, 23), date(2026, 10, 23)),    # thứ Sáu
    (date(2026, 10, 24), date(2026, 10, 26)),    # thứ Bảy
    (date(2026, 10, 25), date(2026, 10, 26)),    # Chủ nhật
    (date(2026, 10, 26), date(2026, 10, 26)),
])
def test_next_workday(d, expected):
    assert next_workday(d) == expected


LEGAL = parse_holidays(LEGAL_HOLIDAYS)
# khoảng ví dụ cho Tết Đinh Mùi (mùng 1 là 06/02/2027), không phải lịch nghỉ Chính phủ công bố
TET = parse_holidays(f"{LEGAL_HOLIDAYS},2027-02-05..2027-02-12")


@pytest.mark.parametrize(("d", "holidays", "expected"), [
    (date(2026, 9, 2), LEGAL, date(2026, 9, 3)),         # Quốc khánh thứ Tư → thứ Năm
    (date(2026, 4, 30), LEGAL, date(2026, 5, 4)),        # 30/4 thứ Năm, 1/5 thứ Sáu, rồi cuối tuần → thứ Hai
    (date(2027, 1, 1), LEGAL, date(2027, 1, 4)),         # lễ thứ Sáu ngay trước cuối tuần; lặp hằng năm
    (date(2027, 2, 8), TET, date(2027, 2, 15)),          # giữa khoảng Tết, hết khoảng là thứ Bảy, Chủ nhật
    (date(2027, 2, 4), TET, date(2027, 2, 4)),           # ngày trước khoảng vẫn là ngày làm việc
    (date(2026, 9, 2), NO_HOLIDAYS, date(2026, 9, 2)),
])
def test_next_workday_skips_holidays(d, holidays, expected):
    assert next_workday(d, holidays) == expected


def test_next_workday_gives_up_after_a_year():
    every_day = Holidays(yearly=frozenset((d.month, d.day) for d in (date(2028, 1, 1) + timedelta(days=i)
                                                                       for i in range(366))))
    assert next_workday(date(2026, 10, 26), every_day) == date(2026, 10, 26) + timedelta(days=366)


def test_suggested_due_date_moves_off_a_holiday():
    # vào sổ thứ Hai 24/8/2026, thói quen 9 ngày → 2/9 là Quốc khánh → thứ Năm 3/9; số ngày vẫn là 9
    s = run([(0.9, DT, 9), (0.8, DT, 9), (0.7, DT, 9)], registered_on=date(2026, 8, 24), today=date(2026, 8, 24),
            holidays=LEGAL)
    assert (s.due_days, s.due_on) == (9, date(2026, 9, 3))
    s = run([(0.9, DT, 9), (0.8, DT, 9), (0.7, DT, 9)], registered_on=date(2026, 8, 24), today=date(2026, 8, 24))
    assert (s.due_days, s.due_on) == (9, date(2026, 9, 2))


def test_holidays_syntax():
    assert LEGAL == Holidays(yearly=frozenset({(1, 1), (4, 30), (5, 1), (9, 2)}))
    h = parse_holidays(" 02-29 ,2027-04-16  2026-12-31..2027-01-02,")
    assert h.yearly == {(2, 29)}
    assert h.dates == {date(2027, 4, 16), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 2)}
    assert date(2028, 2, 29) in h and date(2027, 4, 16) in h and date(2028, 4, 16) not in h
    assert parse_holidays("") == parse_holidays(" , ") == NO_HOLIDAYS
    assert len(parse_holidays("2027-02-05..2027-03-07").dates) == 31     # dài nhất: 31 ngày


@pytest.mark.parametrize("text", [
    "30/04", "4-30", "04-30-", "13-01", "02-30", "٠٤-٣٠",            # ngày lặp hằng năm
    "2027-2-8", "20270208", "2027-W06-1", "2027-02-30", "2027-02-08T00:00",
    "2027-02-13..2027-02-05",                                          # khoảng ngược
    "2027-02-05..2027-03-08",                                          # 32 ngày: gần như chắc gõ nhầm
    "2027-02-05..", "..2027-02-05", "2027-02-05...2027-02-08", "04-30..05-01",
])
def test_bad_holidays_are_rejected(text):
    with pytest.raises(ValueError):
        parse_holidays(text)


def test_dates_are_counted_in_vietnam_time():
    assert vn_date("2026-10-20T17:30:00Z") == date(2026, 10, 21)
    assert vn_date("2026-10-20T16:59:59+00:00") == date(2026, 10, 20)
    assert vn_date("2026-10-21T00:30:00.123456+07:00") == date(2026, 10, 21)
    # vào sổ 00:30 sáng 21/10 giờ VN, hạn 31/10 → 10 ngày (không phải 11 theo ngày UTC)
    assert past_days("2026-10-20T17:30:00Z", "2026-10-31") == 10


@pytest.mark.parametrize(("due", "expected"), [
    ("2026-10-22", 1), ("2027-10-21", MAX_DAYS), ("2026-10-21", None), ("2026-10-01", None),
    ("2027-10-22", None), (None, None), ("", None), ("không-phải-ngày", None),
])
def test_past_days_outside_one_to_a_year_are_ignored(due, expected):
    assert past_days("2026-10-21T02:00:00Z", due) == expected


def test_past_days_needs_a_registration_time():
    assert past_days("", "2026-11-01") is None


def test_evidence_is_capped_and_carries_no_text():
    pairs = [(0.9 - i * 0.05, DT if i % 3 else KTPM, 10) for i in range(9)]
    s = run(pairs)
    assert len(s.evidence) == TOP_K == 5 and s.candidates == 9
    assert [e.score for e in s.evidence] == sorted((e.score for e in s.evidence), reverse=True)
    assert {f.name for f in dataclasses.fields(Evidence)} == {"document_id", "score", "department_id", "days"}
    # chỉ 5 căn cứ đầu bỏ phiếu: đơn vị chỉ có phiếu ở hạng 6 trở đi không vào xếp hạng
    s = run([(0.9 - i * 0.01, DT, 10) for i in range(5)] + [(0.5, KTPM, 3)])
    assert s.ranking == (DT,) and s.share == 1.0


def test_duplicate_hits_vote_once_with_their_best_score():
    hits = [Hit(doc(1), 0.5), Hit(doc(1), 0.9), Hit(doc(2), 0.6)]
    history = {doc(1): Past(doc(1), DT, 10), doc(2): Past(doc(2), KTPM, 3)}
    s = suggest(hits, history, UNITS, min_score=0.3, registered_on=MONDAY, doc_due=None, today=MONDAY)
    assert [(e.document_id, e.score) for e in s.evidence] == [(doc(1), 0.9), (doc(2), 0.6)]
    assert s.share == round(0.9 / 1.5, 3)
