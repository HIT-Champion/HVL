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

"""Hai đường dữ liệu của trợ lý hỏi đáp (#441): ``viec_cua_toi`` đếm việc trong Hộp việc, ``dem_van_ban`` đếm văn bản.

Số lấy thẳng từ CSDL qua Hasura bằng **token người hỏi** (answer.py): quyền do Hasura quyết như ở mọi trang, không có
SQL hay GraphQL do mô hình viết, không gọi mô hình. Câu trả lời là mẫu câu có số và "Căn cứ: …"; ``data`` mang đúng
các số và bộ lọc đã dùng (``make do-hoi-dap`` đếm lại trực tiếp qua GraphQL để so), ``link`` là trang xem danh sách đó.

- Việc: Action ``myTasks`` (cùng nguồn với Hộp việc, Lịch hạn). Quá hạn, đến hạn hôm nay, sắp đến hạn (còn 1–2 ngày)
  tính như ``dueState`` của Lịch hạn (apps/office ``utils/format.ts``), theo ngày giờ Việt Nam. Kể tối đa ba việc gần
  hạn nhất, kèm số ký hiệu văn bản khi người hỏi đọc được văn bản đó.
- Văn bản: ``office_documents_aggregate``. Tham số đọc bằng mẫu chữ trên câu đã bỏ dấu (``route.folded``):

  - hướng: "văn bản đến", "nhận" → văn bản đến, theo ngày vào sổ (``registered_at``); "văn bản đi", "ban hành", "phát
    hành" → văn bản đi, theo ngày ban hành (``issued_on``); không nói thì đếm cả hai;
  - thời gian: "tháng 10", "tháng 10/2026", "tháng 10 năm 2025", "tháng này", "tháng trước", "năm 2026", "năm nay",
    "năm ngoái", "hôm nay" (tiếng Anh: "this month", "last month", "this year", "last year", "today", "in 2026");
    không nói thì không lọc theo ngày;
  - loại: "quyết định", "công văn", "thông báo"… → ``type_code``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SOON_DAYS = 2               # như dueState của Lịch hạn: còn 1–2 ngày là sắp đến hạn
LISTED = 3                  # số việc gần hạn nhất kể tên trong câu trả lời
INBOX = "/"                 # Hộp việc, có Lịch hạn
LISTS = {"in": "/van-ban-den", "out": "/van-ban-di"}

# (chữ đã bỏ dấu, mã loại, tên tiếng Việt, tên tiếng Anh số nhiều) — mã như bảng office.document_types
TYPES: tuple[tuple[str, str, str, str], ...] = (
    ("cong van", "CV", "công văn", "official letters"),
    ("quyet dinh", "QĐ", "quyết định", "decisions"),
    ("thong bao", "TB", "thông báo", "notices"),
    ("ke hoach", "KH", "kế hoạch", "plans"),
    ("bao cao", "BC", "báo cáo", "reports"),
    ("to trinh", "TTr", "tờ trình", "submissions"),
    ("giay moi", "GM", "giấy mời", "invitations"),
    ("chi thi", "CT", "chỉ thị", "directives"),
    ("quy che", "QC", "quy chế", "regulations"),
    ("huong dan", "HD", "hướng dẫn", "guidelines"),
    ("thong tu", "TT", "thông tư", "circulars"),
)
NOUNS = "van ban|" + "|".join(t[0] for t in TYPES)
_TYPE_RE = re.compile(rf"\b(?:{'|'.join(t[0] for t in TYPES)})\b")
_EN_TYPES = {"letters": "CV", "decisions": "QĐ", "notices": "TB", "plans": "KH", "reports": "BC", "circulars": "TT"}
_EN_TYPE_RE = re.compile(rf"\b(?:{'|'.join(_EN_TYPES)})\b")

_IN_RE = re.compile(rf"\b(?:{NOUNS})(?: moi)? den\b|\b(?:nhan duoc|da nhan|tiep nhan|vao so)\b"
                    r"|\b(?:incoming|received)\b")
_OUT_RE = re.compile(rf"\b(?:{NOUNS})(?: moi)? di\b|\b(?:ban hanh|phat hanh|gui di)\b|\b(?:outgoing|issued|sent)\b")

# Mốc thời gian chưa đọc được (ngày cụ thể, khoảng "từ … đến", quý, tuần): câu đó không thành câu đếm, về ``van_ban``
# (route.py) thay vì đếm sai khoảng. So trên chữ bỏ dấu còn "/"
UNSUPPORTED_RE = re.compile(
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\bngay \d|\btu (?:ngay|thang|nam|dau)\b|\bquy (?:\d|i|ii|iii|iv)\b|"
    r"\b(?:tuan|week|quarter|since|between|from)\b")
_MONTH_RE = re.compile(r"\bthang (\d{1,2})(?: nam)?(?: (\d{4}))?\b")
_YEAR_RE = re.compile(r"\bnam (\d{4})\b|\bin (\d{4})\b")
_EN_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
              "november", "december")
_EN_MONTH_RE = re.compile(rf"\b({'|'.join(_EN_MONTHS)})(?: (\d{{4}}))?\b")


@dataclass(frozen=True)
class Period:
    start: date
    end: date               # ngày sau ngày cuối (nửa mở)
    vi: str                 # "tháng 10/2026", "năm 2026", "hôm nay (30/10/2026)"
    en: str                 # kèm giới từ: "in October 2026", "this month (October 2026)"


@dataclass(frozen=True)
class Count:
    directions: tuple[str, ...]     # ("in",), ("out",) hoặc ("in", "out")
    period: Period | None
    type_code: str | None
    noun_vi: str                    # "văn bản", "quyết định"…
    noun_en: str


@dataclass
class Answer:
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    link: str | None = None


def _month(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    return start, date(year + month // 12, month % 12 + 1, 1)


def _en_month(day: date) -> str:
    return f"{_EN_MONTHS[day.month - 1].title()} {day.year}"


def period(text: str, today: date) -> Period | None:
    """Khoảng ngày nhắc trong câu (chữ đã bỏ dấu, viết thường); không nhắc, hay tháng không hợp lệ thì None."""
    m = _MONTH_RE.search(text)
    if m and 1 <= int(m.group(1)) <= 12:
        year, month = int(m.group(2) or today.year), int(m.group(1))
        if 2000 <= year <= 2100:
            start, end = _month(year, month)
            return Period(start, end, f"tháng {month}/{year}", f"in {_en_month(start)}")
    m = _EN_MONTH_RE.search(text)
    if m and (m.group(2) or not m.group(1) == "may"):          # "may" một mình là động từ
        year, month = int(m.group(2) or today.year), _EN_MONTHS.index(m.group(1)) + 1
        if 2000 <= year <= 2100:
            start, end = _month(year, month)
            return Period(start, end, f"tháng {month}/{year}", f"in {_en_month(start)}")
    if re.search(r"\b(?:thang nay|this month)\b", text):
        start, end = _month(today.year, today.month)
        return Period(start, end, f"tháng này ({today.month}/{today.year})", f"this month ({_en_month(start)})")
    if re.search(r"\b(?:thang truoc|last month)\b", text):
        prev = today.replace(day=1) - timedelta(days=1)
        start, end = _month(prev.year, prev.month)
        return Period(start, end, f"tháng trước ({prev.month}/{prev.year})", f"last month ({_en_month(start)})")
    m = _YEAR_RE.search(text)
    if m and 2000 <= int(m.group(1) or m.group(2)) <= 2100:
        year = int(m.group(1) or m.group(2))
        return Period(date(year, 1, 1), date(year + 1, 1, 1), f"năm {year}", f"in {year}")
    if re.search(r"\b(?:nam nay|this year)\b", text):
        return Period(date(today.year, 1, 1), date(today.year + 1, 1, 1), f"năm nay ({today.year})",
                      f"this year ({today.year})")
    if re.search(r"\b(?:nam ngoai|nam truoc|last year)\b", text):
        year = today.year - 1
        return Period(date(year, 1, 1), date(year + 1, 1, 1), f"năm ngoái ({year})", f"last year ({year})")
    if re.search(r"\b(?:hom nay|today)\b", text):
        return Period(today, today + timedelta(days=1), f"hôm nay ({today:%d/%m/%Y})", f"today ({today:%d/%m/%Y})")
    return None


def count_query(text: str, today: date) -> Count:
    """Bộ lọc của câu ``dem_van_ban`` (chữ đã bỏ dấu, viết thường, như ``route.folded``)."""
    incoming, outgoing = bool(_IN_RE.search(text)), bool(_OUT_RE.search(text))
    directions = ("in",) if incoming and not outgoing else ("out",) if outgoing and not incoming else ("in", "out")
    noun_vi, noun_en, type_code = "văn bản", "documents", None
    m = _TYPE_RE.search(text)
    if m:
        _, type_code, noun_vi, noun_en = next(t for t in TYPES if t[0] == m.group(0))
    elif (e := _EN_TYPE_RE.search(text)) is not None:
        type_code = _EN_TYPES[e.group(0)]
        _, _, noun_vi, noun_en = next(t for t in TYPES if t[1] == type_code)
    return Count(directions, period(text, today), type_code, noun_vi, noun_en)


def where(direction: str, query: Count) -> dict[str, Any]:
    """Điều kiện ``office_documents_bool_exp``: văn bản đến tính theo ngày vào sổ (giờ Việt Nam), văn bản đi theo ngày
    ban hành. Quyền (thuê ước, văn bản được xem) Hasura tự thêm theo token."""
    parts: list[dict[str, Any]] = [{"direction": {"_eq": direction}}]
    if query.type_code:
        parts.append({"type_code": {"_eq": query.type_code}})
    p = query.period
    if p is not None and direction == "in":
        parts.append({"registered_at": {"_gte": f"{p.start.isoformat()}T00:00:00+07:00",
                                        "_lt": f"{p.end.isoformat()}T00:00:00+07:00"}})
    elif p is not None:
        parts.append({"issued_on": {"_gte": p.start.isoformat(), "_lt": p.end.isoformat()}})
    return {"_and": parts}


def count_answer(query: Count, counts: dict[str, int], lang: str) -> Answer:
    p = query.period
    data = {"kind": "documents", "counts": dict(counts), "type_code": query.type_code,
            "from": p.start.isoformat() if p else None, "to": p.end.isoformat() if p else None}
    link = LISTS[query.directions[0]] if len(query.directions) == 1 else None
    if lang == "en":
        words = {"in": "incoming", "out": "outgoing"}
        noun = {d: query.noun_en if counts[d] != 1 else query.noun_en[:-1] for d in query.directions}
        parts = " and ".join(f"{counts[d]} {words[d]} {noun[d]}" for d in query.directions)
        verb = "is" if counts[query.directions[0]] == 1 else "are"
        when = f" {p.en}" if p else ""
        basis = ("Basis: the documents you are allowed to see in Signet; incoming documents by registration date, "
                 "outgoing documents by issue date (Vietnam time).") if p else \
            "Basis: the documents you are allowed to see in Signet, all dates."
        return Answer(f"There {verb} {parts}{when}. {basis}", data, link)
    words = {"in": "đến", "out": "đi"}
    parts = " và ".join(f"{counts[d]} {query.noun_vi} {words[d]}" for d in query.directions)
    when = f" trong {p.vi}" if p else ""
    basis = ("Căn cứ: các văn bản bạn được xem trên Signet; văn bản đến tính theo ngày vào sổ, văn bản đi theo ngày "
             "ban hành (giờ Việt Nam).") if p else "Căn cứ: các văn bản bạn được xem trên Signet, mọi thời gian."
    return Answer(f"Có {parts}{when}. {basis}", data, link)


# --- việc của tôi ----------------------------------------------------------------------------------------------


def _due(task: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(task.get("due_on"))[:10]) if task.get("due_on") else None
    except ValueError:
        return None


def urgent(tasks: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Việc quá hạn, đến hạn hôm nay, sắp đến hạn; hạn sớm nhất trước (cùng hạn thì giữ thứ tự Hộp việc)."""
    near = [t for t in tasks if (d := _due(t)) is not None and (d - today).days <= SOON_DAYS]
    return sorted(near, key=lambda t: _due(t))   # type: ignore[arg-type,return-value]


def _item(task: dict[str, Any], symbols: dict[str, str], today: date, en: bool) -> str:
    """Một việc gần hạn: tên bước, số ký hiệu văn bản (nếu đọc được), hạn so với hôm nay."""
    due = _due(task) or today
    symbol = symbols.get(str(task.get("document_id")))
    name = f"{task.get('name') or ''} {symbol or ''}".strip()
    late = (today - due).days
    if en:
        when = f"{late} day(s) overdue" if late > 0 else "due today" if late == 0 else f"due {due:%d/%m}"
    else:
        when = f"quá {late} ngày" if late > 0 else "hạn hôm nay" if late == 0 else f"hạn {due:%d/%m}"
    return f"{name} ({when})"


def tasks_answer(tasks: list[dict[str, Any]], symbols: dict[str, str], today: date, lang: str) -> Answer:
    """``symbols``: số ký hiệu văn bản của việc, chỉ văn bản người hỏi đọc được (hậu kiểm bằng token)."""
    days = [(d - today).days if (d := _due(t)) is not None else None for t in tasks]
    n = {"tasks": len(tasks), "overdue": sum(1 for x in days if x is not None and x < 0),
         "today": sum(1 for x in days if x == 0), "soon": sum(1 for x in days if x is not None and 0 < x <= SOON_DAYS),
         "no_due": sum(1 for x in days if x is None)}
    data = {"kind": "tasks", "on": today.isoformat(), **n}
    en = lang == "en"
    if not tasks:
        text = "Your inbox has no open tasks." if en else "Hộp việc của bạn không có việc nào đang chờ."
    else:
        bits = [(n["overdue"], "overdue", "quá hạn"), (n["today"], "due today", "đến hạn hôm nay"),
                (n["soon"], f"due in the next {SOON_DAYS} days", f"đến hạn trong {SOON_DAYS} ngày tới")]
        said = ", ".join(f"{k} {en_w if en else vi_w}" for k, en_w, vi_w in bits if k)
        if en:
            text = f"Your inbox has {n['tasks']} open task(s): {said or 'none is overdue or due soon'}."
        else:
            text = f"Hộp việc của bạn có {n['tasks']} việc đang chờ: {said or 'chưa việc nào quá hạn hay sắp đến hạn'}."
        items = [_item(t, symbols, today, en) for t in urgent(tasks, today)[:LISTED]]
        if items:
            text += (" Nearest: " if en else " Gần hạn nhất: ") + "; ".join(items) + "."
    basis = (f" Basis: your inbox in Signet on {today:%d/%m/%Y}; overdue and due dates as in the deadline calendar."
             if en else f" Căn cứ: Hộp việc của bạn trên Signet ngày {today:%d/%m/%Y}; quá hạn, đến hạn tính như "
                        "Lịch hạn.")
    return Answer(text + basis, data, INBOX)
