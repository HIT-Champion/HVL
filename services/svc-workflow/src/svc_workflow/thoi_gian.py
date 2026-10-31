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

"""Thời gian dùng chung của svc-workflow: thời hạn ISO 8601 và ngày nghỉ lễ. Phần lõi, không biết nghiệp vụ nào:
cấu hình (config.py) đọc bằng các hàm ở đây; nhắc hạn (sla.py) và gợi ý hạn (suggest.py) của Văn phòng dùng lại, đúng
chiều Văn phòng → lõi (#489, docs/architecture.md §4.7). Thuần Python, không I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


def parse_duration(text: str) -> timedelta:
    """Thời hạn ISO 8601 dạng ngày, giờ, phút, giây (P1D, PT24H, PT1M, PT20S) — đúng phần Flowable hiểu như nhau."""
    m = _DURATION.match(text or "")
    if not m or text.endswith("T"):
        raise ValueError(f"thời hạn không hợp lệ: {text!r} (dạng ISO 8601, ví dụ PT24H, PT1M)")
    days, hours, minutes, seconds = m.groups()
    value = timedelta(days=int(days or 0), hours=int(hours or 0), minutes=int(minutes or 0),
                      seconds=float(seconds or 0))
    if value <= timedelta(0):
        raise ValueError(f"thời hạn phải lớn hơn 0: {text!r}")
    return value


@dataclass(frozen=True)
class Holidays:
    """Ngày nghỉ ngoài thứ Bảy, Chủ nhật: (tháng, ngày) lặp hằng năm, các ngày của một năm; và thứ Bảy, Chủ nhật làm
    bù khi lịch nghỉ hoán đổi ngày làm việc (#427) — ngày làm việc dù rơi vào cuối tuần."""

    yearly: frozenset[tuple[int, int]] = frozenset()
    dates: frozenset[date] = frozenset()
    workdays: frozenset[date] = frozenset()

    def __contains__(self, d: object) -> bool:
        return isinstance(d, date) and ((d.month, d.day) in self.yearly or d in self.dates)

    def __or__(self, other: Holidays) -> Holidays:
        return Holidays(self.yearly | other.yearly, self.dates | other.dates, self.workdays | other.workdays)

    def is_workday(self, d: date) -> bool:
        return (d.weekday() < 5 or d in self.workdays) and d not in self


NO_HOLIDAYS = Holidays()
# Ngày lễ dương lịch cố định của Điều 112 Bộ luật Lao động 2019. Tết Âm lịch, Giỗ Tổ Hùng Vương, ngày liền kề Quốc
# khánh, ngày nghỉ bù, làm bù đổi theo năm: lấy từ lịch nghỉ chính thức (MOC_HOLIDAYS_FILE, #427); năm tệp chưa có thì
# người vận hành thêm vào MOC_HOLIDAYS theo lịch nghỉ Chính phủ công bố
LEGAL_HOLIDAYS = "01-01,04-30,05-01,09-02"
MAX_RANGE_DAYS = 31  # một khoảng dài hơn gần như chắc là gõ nhầm năm, tháng


def parse_holidays(text: str) -> Holidays:
    """``04-30`` lặp hằng năm; ``2027-02-08`` một ngày; ``2027-02-05..2027-02-13`` cả khoảng, tính cả hai đầu.

    Các mục cách nhau bằng dấu phẩy hay khoảng trắng; chuỗi rỗng là không có ngày lễ. Sai dạng thì ``ValueError``.
    """
    yearly: set[tuple[int, int]] = set()
    dates: set[date] = set()
    for item in text.replace(",", " ").split():
        start, sep, end = item.partition("..")
        if sep:
            first, last = _day(start, item), _day(end, item)
            if not 0 <= (last - first).days < MAX_RANGE_DAYS:
                raise ValueError(f"{item!r}: khoảng phải từ ngày sớm tới ngày muộn, dài tối đa {MAX_RANGE_DAYS} ngày")
            dates.update(first + timedelta(days=i) for i in range((last - first).days + 1))
        elif item.count("-") == 1:
            month, day = _numbers(item, (2, 2), item)
            _date(2000, month, day, item)  # năm nhuận: 02-29 hợp lệ
            yearly.add((month, day))
        else:
            dates.add(_day(item, item))
    return Holidays(frozenset(yearly), frozenset(dates))


def holidays_from_data(data: object) -> Holidays:
    """Lịch nghỉ của nguồn công khai B (``ngay-nghi.json``, scripts/nguon_ngay_nghi_le.py): ``fixed`` các ngày
    ``MM-DD`` hằng năm, ``days_off`` các khoảng ``from``..``to`` (≤ ``MAX_RANGE_DAYS`` ngày), ``workdays`` các ngày
    cuối tuần làm bù. Sai dạng thì ``ValueError``."""
    if not isinstance(data, dict):
        raise ValueError("cần một đối tượng JSON")
    yearly: set[tuple[int, int]] = set()
    dates: set[date] = set()
    workdays: set[date] = set()
    for entry in _entries(data, "fixed", ("date",)):
        month, day = _numbers(entry["date"], (2, 2), entry["date"])
        _date(2000, month, day, entry["date"])
        yearly.add((month, day))
    for entry in _entries(data, "days_off", ("from", "to")):
        item = f"{entry['from']}..{entry['to']}"
        dates.update(parse_holidays(item).dates)
    for entry in _entries(data, "workdays", ("date",)):
        d = _day(entry["date"], entry["date"])
        if d.weekday() < 5:
            raise ValueError(f"{entry['date']!r}: ngày làm bù phải là thứ Bảy hay Chủ nhật")
        workdays.add(d)
    return Holidays(frozenset(yearly), frozenset(dates), frozenset(workdays))


def _entries(data: dict[str, object], key: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    items = data.get(key, [])
    if not isinstance(items, list) or not all(
            isinstance(e, dict) and all(isinstance(e.get(f), str) for f in fields) for e in items):
        raise ValueError(f"{key!r}: cần danh sách mục có {', '.join(fields)} là chuỗi")
    return items


def _numbers(text: str, sizes: tuple[int, ...], item: str) -> list[int]:
    # chỉ nhận đúng số chữ số từng phần: date.fromisoformat còn nhận 20270208, 2027-W06-1…
    chunks = text.split("-")
    if tuple(map(len, chunks)) != sizes or not all(c.isascii() and c.isdigit() for c in chunks):
        raise ValueError(f"{item!r}: cần MM-DD, YYYY-MM-DD hoặc YYYY-MM-DD..YYYY-MM-DD")
    return [int(c) for c in chunks]


def _date(year: int, month: int, day: int, item: str) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"{item!r}: không có ngày này") from None


def _day(text: str, item: str) -> date:
    year, month, day = _numbers(text, (4, 2, 2), item)
    return _date(year, month, day, item)


def next_workday(d: date, holidays: Holidays = NO_HOLIDAYS) -> date:
    """Ngày làm việc đầu tiên từ ``d``: bỏ qua thứ Bảy, Chủ nhật (trừ ngày làm bù) và ngày lễ trong ``holidays``."""
    for _ in range(366):  # cấu hình cho nghỉ cả năm cũng không làm vòng lặp treo
        if holidays.is_workday(d):
            break
        d += timedelta(days=1)
    return d
