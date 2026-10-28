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

"""Che thông tin cá nhân (F4.4): số CCCD/CMND, số điện thoại, email, số tài khoản viết theo định dạng Việt Nam.

Dùng ở hai chỗ: chữ gửi mô hình (``Masker`` đánh số nhãn ``[SĐT-1]`` trong một lượt hỏi, ``mask_text`` ở lối ra
Ollama) và nhật ký (``PiiFilter``). Chỉ mục tìm kiếm, câu trích nguyên văn và sổ kiểm toán giữ bản gốc: người có quyền
đọc văn bản thì thấy số thật. svc_workflow/pii.py là bản chép y hệt byte của tệp này (test so byte).

Tự viết, chỉ dùng thư viện chuẩn: Presidio kéo spaCy, numpy… mà vẫn không có định dạng Việt Nam. Nhận theo cấu trúc
chứ không theo "dãy số đủ dài": chuỗi số ứng viên → cụm nhóm liền nhau → kiểm mã tỉnh, thế kỷ, năm sinh, đầu số đã
cấp. CMND và số tài khoản không có cấu trúc riêng nên chỉ nhận khi đứng ngay sau từ khóa. Số dính chữ chỉ nhận khi là
số di động viết liền sau tiền tố điện thoại (``ĐT0912…``, ``Tel0912…``).

Sót có chủ đích: số dính chữ khác (``HS0912…``, máy bàn sau ``Tel``), số có hai ký tự trắng liền (cả dòng trống),
CCCD sau ``/``; số viết từng cặp (``09 12 34 56 78``), số nhóm nối bằng phẩy không cách; số máy bàn kiểu cũ 10 số, số
nước ngoài; họ tên, địa chỉ; CMND và số tài khoản không có từ khóa; chữ không ở dạng NFC có thể sót từ khóa.

    python -m svc_files.pii mask  < tệp     # in bản che, nhãn trơn [SĐT] (svc-workflow: svc_workflow.pii)
    python -m svc_files.pii count < tệp     # in {"chars", "total", "spans"} — không bao giờ in giá trị
"""

from __future__ import annotations

import bisect
import json
import logging
import re
import sys
import time
import unicodedata
from dataclasses import dataclass

KINDS = ("cccd", "cmnd", "phone", "email", "account")
LABELS = {"cccd": "CCCD", "cmnd": "CMND", "phone": "SĐT", "email": "EMAIL", "account": "STK"}
# Nhãn đã che (trơn hoặc đánh số): trích yếu mang nhãn thì bị loại, giao diện nhận ra câu trả lời có che.
# Nhãn không chứa < > " \ nên chèn vào JSON hay thẻ <nguon> vẫn hợp lệ, và không giống dấu trích dẫn [1].
LABEL_RE = re.compile(r"\[(?:CCCD|CMND|SĐT|EMAIL|STK)(?:-\d{1,3})?\]")

# Mã tỉnh (3 chữ số đầu) của số định danh cá nhân 12 số: 63 tỉnh, thành phố — phụ lục danh mục mã tỉnh, Thông tư
# 59/2021/TT-BCA. Chưa xác nhận người đăng ký khai sinh sau khi sắp xếp tỉnh (07/2025) có mang mã ngoài danh sách này
# hay không; nếu có thì chỉ còn đường từ khóa ("CCCD", "số định danh"…) bắt được.
PROVINCES = frozenset("""
001 002 004 006 008 010 011 012 014 015 017 019 020 022 024 025 026 027 030 031 033 034 035 036 037 038 040 042
044 045 046 048 049 051 052 054 056 058 060 062 064 066 067 068 070 072 074 075 077 079 080 082 083 084 086 087
089 091 092 093 094 095 096
""".split())
# Đầu số di động 10 số đã cấp (10/2026; 095 về Viettel từ 07/2026) — có dải mới thì thêm ở đây
MOBILE_PREFIXES = frozenset("""
032 033 034 035 036 037 038 039 052 055 056 058 059 070 076 077 078 079 081 082 083 084 085 086 087 088 089
090 091 092 093 094 095 096 097 098 099
""".split())
OLD_MOBILE_PREFIXES = frozenset({"012", "016", "018", "019"})    # di động 11 số trước khi chuyển đầu số (2018)
MAX_GROUPS = 6           # một cụm số dài tối đa từng này nhóm — giữ bước chọn cụm tuyến tính (chuỗi "12 12 12…")
MAX_GAP = 20             # khoảng cách tối đa (ký tự) từ cuối từ khóa tới chữ số đầu
TAX_WINDOW = 25          # cổng mã số thuế: từ khóa nằm trong từng này ký tự trước số
MAX_PASSES = 3           # find() lặp tới khi bản che không còn gì để che, tối đa từng này lượt

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
# Phân cách nhóm: đúng MỘT chấm, gạch hay ký tự trắng bất kỳ — cả xuống dòng (lớp chữ PDF, OCR ngắt dòng ở dấu cách:
# "0912 345⏎678"; \r\n tính là một), tab, cách không ngắt, cách hẹp U+2009 / U+202F
SEP = r"(?:\r\n|[\s.\-])"
LINE_BREAKS = "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"      # ranh giới dòng (như str.splitlines)
# Chuỗi số ứng viên: các nhóm chữ số cách nhau một phân cách; có thể mở đầu bằng +84, (+84), 0084 (kèm "(0)") hoặc mã
# vùng trong ngoặc (024). Trước không là chữ cái / chữ số ("_" là ranh giới: tên tệp "don_0912…"), "/", "@" hay "chữ
# số + chấm/phẩy"; sau không là chữ cái / chữ số, "@", "/" hay "chấm/phẩy + chữ số" — loại số ký hiệu 131/…, đường
# dẫn, hex, phần lẻ của số thập phân. Riêng phẩy nối hai dãy ≥ 9 chữ số liền ("0912345678,0987654321") là hai số.
NUMBER_RE = re.compile(
    r"(?<![^\W_]|[/@])(?<!\d\.)(?:(?<!\d,)|(?<=\d{9},))"
    rf"(?:(?:(?P<cc>\(\+84\)|\+84|0084)(?:{SEP}?\(0\))?|(?P<area>\(0\d{{2,3}}\))){SEP}?)?"
    rf"(?P<body>\d+(?:{SEP}\d+)*)"
    r"(?![^\W_]|[@/])(?!\.\d)(?!,\d(?!\d{8}))"
)
GROUP_RE = re.compile(r"\d+")
EMAIL_RE = re.compile(
    r"(?<![\w.%+\-])[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*\.[A-Za-z]{2,24}(?![\w\-])"
)
# Từ khóa so trên bản gấp dấu (fold): "Số CMND", "CĂN CƯỚC CÔNG DÂN", "so tai khoan" đều khớp
ID_KEYWORD_RE = re.compile(
    r"\b(?:cccd|cmnd|cmt|can\s+cuoc(?:\s+cong\s+dan)?|chung\s+minh\s+(?:nhan\s+dan|thu)"
    r"|(?:so|ma)\s+dinh\s+danh(?:\s+ca\s+nhan)?)\b"
)
ACCOUNT_KEYWORD_RE = re.compile(r"\b(?:so\s+tai\s+khoan|stk|tai\s+khoan(?:\s+ngan\s+hang)?\s+so|tk\s+so|so\s+tk)\b")
GAP_RE = re.compile(r"[\s:.,#()\-–]*(?:so\s*)?(?:la\s*)?[\s:.,#()\-–]*")    # "CCCD số: ", "CMND là ", "STK số (…"
# Số sau từ khóa: lấy trọn chuỗi (không lùi bớt nhóm), dính chữ thì bỏ cả — "001 205 000 017x" không thành CMND 9 số.
# Chỉ lùi về cuối một dòng: "CMND số 123456789⏎2. Địa chỉ" (trọn chuỗi 10 số) vẫn che 9 số của dòng đầu.
KEYWORD_NUMBER_RE = re.compile(rf"\d++(?:{SEP}\d++)*+")
GLUED_RE = re.compile(r"[^\W_]|[@/]|[.,]\d")      # khớp ngay sau số thì số dính chữ
# Cổng mã số thuế: MST doanh nghiệp 10 số mở đầu bằng mã tỉnh 2 số của cơ quan thuế cấp (01 Hà Nội, 03 TP HCM…); mã
# tỉnh trải từ 01 tới hơn 60 nên có dải trùng dạng đầu số di động (07…, 08…, 09…), còn dải 03… của TP HCM đang ở
# 030–031 và sẽ chạm 032. Số 10 chữ số ngay sau từ khóa MST thì không coi là SĐT; CCCD 12 số sau MST (MST cá nhân là
# số định danh) vẫn che.
TAX_KEYWORD_RE = re.compile(r"\b(?:mst|ma\s+so\s+thue|ma\s+so\s+doanh\s+nghiep|msdn)\b")
# Tiền tố điện thoại viết liền số (#58): "ĐT0912345678", "SĐT0912 345 678", "Tel0912…" — so trên bản gấp dấu ("SDT",
# "sđt" cũng khớp). Tiền tố đứng đầu dòng hay sau khoảng trắng, dấu câu; không sau chữ, chữ số, "_", "/", "-", "@" (mã
# hồ sơ "HSĐT0912…", số ký hiệu "QĐ-ĐT…").
PHONE_PREFIX_RE = re.compile(r"(?<![\w/@\-])(?:s?dt|dd|tel|phone)(?=\d)")


class _Fold(dict):
    """Bảng cho ``str.translate``: mỗi ký tự → đúng MỘT ký tự (đ → d, ố → o, khoảng trắng → " ", chữ ASCII viết
    thường), nên bản gấp cùng độ dài và vị trí khớp trên bản gấp dùng thẳng cho chuỗi gốc. Chỉ nhớ các ký tự dưới
    U+2100 (Latin, tiếng Việt, khoảng trắng) để chữ lạ không làm bảng phình mãi."""

    def __missing__(self, code: int) -> str:
        ch = chr(code)
        if ch in "đĐ":
            out = "d"
        elif ch.isspace():
            out = " "
        else:
            base = unicodedata.normalize("NFD", ch)[0]
            out = base.lower() if base.isascii() else ch
        if code < 0x2100:
            self[code] = out
        return out


_FOLD = _Fold()


def fold(text: str) -> str:
    """Bản gấp dấu cùng độ dài: "Số CĂN CƯỚC" → "so can cuoc"."""
    return text.translate(_FOLD)


@dataclass(frozen=True)
class Span:
    start: int           # [start, end) trên chuỗi GỐC
    end: int
    kind: str            # một trong KINDS


@dataclass(frozen=True)
class Masked:
    text: str                       # bản đã che
    spans: tuple[Span, ...]         # các khoảng bị che trên chuỗi gốc, theo vị trí
    labels: tuple[str, ...]         # labels[i] thay cho spans[i]

    def counts(self) -> dict[str, int]:
        """Số chỗ đã che theo loại (chỉ các loại có mặt)."""
        return {kind: n for kind in KINDS if (n := sum(s.kind == kind for s in self.spans))}

    def window(self, span: tuple[int, int]) -> tuple[int, int]:
        """Đổi khoảng ``(lo, hi)`` trên chuỗi gốc sang bản che: ``lo`` rơi giữa một số bị che thì về đầu nhãn, ``hi``
        rơi giữa thì về cuối nhãn — cắt cửa sổ theo kết quả này không bao giờ cắt đôi một con số."""
        lo, hi = span
        return self._at(lo, start=True), self._at(hi, start=False)

    def _at(self, pos: int, *, start: bool) -> int:
        shift = 0                    # tổng chênh độ dài của các khoảng che đứng trước pos
        for s, label in zip(self.spans, self.labels):
            if s.end <= pos:
                shift += len(label) - (s.end - s.start)
            elif s.start < pos:      # rơi giữa khoảng che
                return s.start + shift + (0 if start else len(label))
            else:
                break
        return pos + shift


def _digits(text: str) -> str:
    """Chữ số ASCII của ``text`` (chữ số Unicode khác, như chữ số toàn khổ, đổi về ASCII)."""
    found = "".join(GROUP_RE.findall(text))
    return found if found.isascii() else "".join(str(unicodedata.decimal(c)) for c in found)


def _is_mobile(prefix: str) -> bool:
    return prefix in MOBILE_PREFIXES


def _is_cccd(d: str, year: int) -> bool:
    """3 số mã tỉnh, 1 số giới tính + thế kỷ (0/1 thế kỷ 20, 2/3 thế kỷ 21; 4–9 là các thế kỷ sau), 2 số năm sinh."""
    if d[:3] not in PROVINCES or d[3] not in "0123":
        return False
    return d[3] in "01" or int(d[4:6]) <= year % 100      # sinh ở thế kỷ 21 thì không sinh sau năm nay


def _number_kind(d: str, cc: bool, year: int) -> str | None:
    """Loại của dãy chữ số ``d`` (đã ghép, ASCII) theo cấu trúc; ``cc``: có +84 / (+84) / 0084 đứng trước."""
    if cc:
        d = d[1:] if d.startswith("0") else d     # "+84 0912…": người viết giữ cả số 0 đầu
        if len(d) == 9 and _is_mobile("0" + d[:2]):
            return "phone"
        return "phone" if len(d) == 10 and d[0] == "2" else None
    if len(d) == 12:
        return "cccd" if _is_cccd(d, year) else None
    if len(d) == 10:
        return "phone" if _is_mobile(d[:3]) else None
    if len(d) == 11 and (d.startswith("02") or d[:3] in OLD_MOBILE_PREFIXES):
        return "phone"                            # máy bàn 02x (11 số từ 2017), di động 11 số cũ
    if len(d) == 11 and d.startswith("84") and _is_mobile("0" + d[2:4]):
        return "phone"                            # di động viết liền 84… (bỏ dấu cộng)
    return None


def _after_tax_code(folded: str, at: int) -> bool:
    """Ngay trước vị trí ``at`` (≤ TAX_WINDOW ký tự) có từ khóa mã số thuế mà giữa hai bên không có chữ số nào khác
    ("MST: 0100109106 - ĐT: 0912…" thì số điện thoại vẫn bị che)."""
    last = None
    for last in TAX_KEYWORD_RE.finditer(folded, max(0, at - TAX_WINDOW), at):
        pass
    return last is not None and not any(c.isdigit() for c in folded[last.end():at])


def _counting(text: str, groups: list[tuple[int, int]]) -> bool:
    """Dãy đếm: ≥ 3 nhóm cùng độ dài, nhóm sau hơn nhóm trước đúng 1 — cột số thứ tự tách mỗi ô một dòng
    ("001⏎002⏎003⏎004"), dãy mã ("0101 0102 0103"). Số thật hầu như không bao giờ có dạng này."""
    if len(groups) < 3 or len({b - a for a, b in groups}) != 1:
        return False
    values = [int(_digits(text[a:b])) for a, b in groups]
    return all(y - x == 1 for x, y in zip(values, values[1:]))


def _number_spans(text: str, folded: str, year: int) -> list[Span]:
    """Đường cấu trúc: mỗi chuỗi số ứng viên → các cụm ≤ MAX_GROUPS nhóm liền nhau hợp lệ, ưu tiên cụm dài nhất rồi
    trái nhất; nhận xong một cụm thì tìm tiếp trong các nhóm còn lại ("0912 345 678 0987 654 321" ra hai số).

    Cụm nhiều nhóm mở đầu bằng nhóm ≥ 3 chữ số (CCCD 3-3-3-3, 4-4-4; điện thoại 4-3-3, 3-3-4, 4-2-2-2), trừ khi có
    +84 / mã vùng đứng trước: dãy số nhỏ của bảng, lịch ("Tuần 01 02 03 04 05 06") không ghép thành số."""
    out: list[Span] = []
    for m in NUMBER_RE.finditer(text):
        base = m.start("body")
        groups = [(base + g.start(), base + g.end()) for g in GROUP_RE.finditer(m.group("body"))]
        head = None                                   # tiền tố chỉ tính cho cụm bắt đầu ở nhóm đầu
        if m.group("area"):
            groups.insert(0, (m.start("area") + 1, m.end("area") - 1))     # (024) ghép vào trước như số cố định
            head = m.start("area")
        elif m.group("cc"):
            head = m.start("cc")
        cc = m.group("cc") is not None
        n = len(groups)
        found: list[tuple[int, int, str]] = []       # (số nhóm, nhóm đầu, loại)
        for i in range(n):
            first = groups[i][0]
            if i and text[first - 1] == ".":         # sau "chữ số + chấm" là phần lẻ, không phải đầu một số
                continue
            digits = ""
            lead = 2 if (i == 0 and head is not None) else 3      # số chữ số tối thiểu của nhóm đầu
            for j in range(i, min(n, i + MAX_GROUPS)):
                a, b = groups[j]
                # cụm từ 2 nhóm trở lên: nhóm đầu lead–6 chữ số, các nhóm sau 2–6 (sai thì mọi cụm dài hơn cũng sai)
                if j > i and not (2 <= b - a <= 6 and lead <= groups[i][1] - groups[i][0] <= 6):
                    break
                digits += text[a:b]
                if len(digits) > 12:
                    break
                if len(digits) < 9 or (j + 1 < n and text[b] == "."):     # cụm không dừng trước ".chữ số"
                    continue
                kind = _number_kind(_digits(digits), cc and i == 0, year)
                if kind == "phone" and len(digits) == 10 and not (cc and i == 0) and _after_tax_code(folded, first):
                    kind = None
                if kind and _counting(text, groups[i:j + 1]):
                    kind = None
                if kind:
                    found.append((j - i + 1, i, kind))
        used = [False] * n
        for size, i, kind in sorted(found, key=lambda f: (-f[0], f[1])):
            if any(used[i:i + size]):
                continue
            used[i:i + size] = [True] * size
            start = head if (i == 0 and head is not None) else groups[i][0]
            out.append(Span(start, groups[i + size - 1][1], kind))
    return out


def _keyword_spans(text: str, folded: str) -> list[Span]:
    """Đường từ khóa: CCCD/CMND 9 hoặc 12 số, số tài khoản 6–19 số, đứng sau từ khóa (khoảng đệm ≤ MAX_GAP ký tự).
    Không kiểm mã tỉnh, thế kỷ: có từ khóa thì đủ tin."""
    out: list[Span] = []
    for regex, account in ((ID_KEYWORD_RE, False), (ACCOUNT_KEYWORD_RE, True)):
        for k in regex.finditer(folded):
            at = GAP_RE.match(folded, k.end()).end()
            if at - k.end() > MAX_GAP:
                continue
            m = KEYWORD_NUMBER_RE.match(text, at)
            if not m:
                continue
            groups: list[tuple[int, int]] = []        # tối đa MAX_GROUPS + 1 nhóm đầu: chuỗi dài không tốn thêm
            for g in GROUP_RE.finditer(text, m.start(), m.end()):
                groups.append(g.span())
                if len(groups) > MAX_GROUPS:
                    break
            # trọn chuỗi (nếu không dính chữ), rồi lùi về cuối từng dòng, dài trước
            ends = [n for n in range(min(len(groups), MAX_GROUPS), 0, -1)
                    if (n == len(groups) and not GLUED_RE.match(text, m.end()))
                    or (n < len(groups) and text[groups[n - 1][1]] in LINE_BREAKS)]
            for n in ends:
                size = sum(b - a for a, b in groups[:n])
                kind = None
                if account:
                    kind = "account" if 6 <= size <= 19 else None
                elif size in (9, 12):
                    cmnd = size == 9 or k.group().startswith(("cmnd", "cmt", "chung"))
                    kind = "cmnd" if cmnd else "cccd"
                if kind:
                    out.append(Span(m.start(), groups[n - 1][1], kind))
                    break
    return out


def _prefixed_phone_spans(text: str, folded: str, year: int) -> list[Span]:
    """Đường tiền tố: số di động 10 số viết liền sau "ĐT", "SĐT", "DĐ", "Tel", "Phone" — đường cấu trúc bỏ qua vì số
    dính chữ. Thay tiền tố bằng dấu cách cùng độ dài rồi cho đường cấu trúc xét lại, giữ số bắt đầu ngay sau tiền tố:
    cùng quy tắc nhóm, biên, phần lẻ như số đứng riêng. Tiền tố không đứng sau chữ, chữ số, nên thay nó không đổi biên
    của số đứng trước. Máy bàn, CCCD sau tiền tố không nhận: mã có chữ dính số vẫn giữ nguyên."""
    parts: list[str] = []
    ends: set[int] = set()
    at = 0
    for k in PHONE_PREFIX_RE.finditer(folded):
        parts += (text[at:k.start()], " " * (k.end() - k.start()))
        at = k.end()
        ends.add(at)
    if not ends:
        return []
    parts.append(text[at:])
    unglued = "".join(parts)
    out: list[Span] = []
    for s in _number_spans(unglued, fold(unglued), year):
        d = _digits(unglued[s.start:s.end])
        if s.start in ends and len(d) == 10 and _is_mobile(d[:3]):
            out.append(s)
    return out


def _find_once(text: str, year: int) -> list[Span]:
    folded = fold(text)
    protected = [m.span() for m in UUID_RE.finditer(text)]
    starts = [a for a, _ in protected]
    candidates = [(0, s) for s in _keyword_spans(text, folded)]
    candidates += [(1, Span(m.start(), m.end(), "email")) for m in EMAIL_RE.finditer(text)]
    candidates += [(2, s) for s in _number_spans(text, folded, year)]
    candidates += [(2, s) for s in _prefixed_phone_spans(text, folded, year)]
    candidates.sort(key=lambda c: (c[1].start, c[0], c[1].start - c[1].end))
    out: list[Span] = []
    for _, s in candidates:
        if out and s.start < out[-1].end:
            continue
        i = bisect.bisect_left(starts, s.end) - 1       # vùng bảo vệ cuối cùng bắt đầu trước s.end
        if i >= 0 and protected[i][1] > s.start:
            continue
        out.append(s)
    return out


def find(text: str, *, year: int | None = None) -> list[Span]:
    """Các khoảng cần che, không chồng nhau, theo vị trí. ``year`` (mặc định năm nay) để loại CCCD sinh ở tương lai.

    Chồng nhau thì: khớp có từ khóa > email > số theo cấu trúc; khớp chạm UUID (vùng bảo vệ) thì bỏ. Lặp tới điểm bất
    động (≤ MAX_PASSES lượt): che xong một khớp có thể gỡ điều kiện chặn của khớp bên cạnh — "001205000017,0084a@…"
    lượt đầu chỉ che email (nuốt cả 0084), CCCD đứng trước ",0" bị chặn; lượt sau trên bản che mới thấy CCCD. Khớp
    mới không bao giờ chứa nhãn (khớp không có "[" "]", nhãn trơn không có chữ số) nên đổi thẳng về vị trí chữ gốc."""
    if year is None:
        year = time.localtime().tm_year
    spans = _find_once(text, year)
    for _ in range(MAX_PASSES - 1):
        if not spans:
            break
        masked = _masked(text, spans, [f"[{LABELS[s.kind]}]" for s in spans])
        more = _find_once(masked.text, year)
        if not more:
            break
        shifts = []                  # (vị trí trên bản che ngay sau nhãn, tổng chênh độ dài tới hết nhãn đó)
        shift = 0
        for s, label in zip(masked.spans, masked.labels):
            shift += len(label) - (s.end - s.start)
            shifts.append((s.start + shift + (s.end - s.start), shift))
        ends = [at for at, _ in shifts]
        for s in more:
            k = bisect.bisect_right(ends, s.start) - 1
            back = shifts[k][1] if k >= 0 else 0
            spans.append(Span(s.start - back, s.end - back, s.kind))
        spans.sort(key=lambda s: s.start)
    return spans


def _masked(text: str, spans: list[Span], labels: list[str]) -> Masked:
    parts: list[str] = []
    at = 0
    for s, label in zip(spans, labels):
        parts += (text[at:s.start], label)
        at = s.end
    parts.append(text[at:])
    return Masked("".join(parts), tuple(spans), tuple(labels))


def mask(text: str, *, year: int | None = None) -> Masked:
    """Che bằng nhãn trơn ``[SĐT]``, ``[CCCD]``… (nhật ký, lối ra mô hình)."""
    spans = find(text, year=year)
    return _masked(text, spans, [f"[{LABELS[s.kind]}]" for s in spans])


def mask_text(text: str) -> str:
    """``mask(text).text``. Idempotent: ``find`` lặp tới điểm bất động, bản đã che không còn gì để che."""
    return mask(text).text


def _canonical(value: str, kind: str) -> str:
    """Giá trị chuẩn hóa để đánh số nhãn: email viết thường; số chỉ giữ chữ số, +84 / 0084 / 84 liền đổi thành 0."""
    if kind == "email":
        return value.lower()
    if kind == "phone":
        for cc in ("(+84)", "+84", "0084"):
            if value.startswith(cc):
                rest = _digits(value[len(cc):])
                return rest if rest.startswith("0") else "0" + rest
        digits = _digits(value)
        return "0" + digits[2:] if len(digits) == 11 and digits.startswith("84") else digits
    return _digits(value)


class Masker:
    """Một lượt (một câu hỏi + các đoạn của nó): nhãn đánh số ``[SĐT-1]``, ``[SĐT-2]``…, đếm riêng từng loại. Cùng
    giá trị chuẩn hóa thì cùng số, giữ qua các lần gọi — số trong câu hỏi và trong đoạn mang cùng nhãn, nên mô hình
    vẫn biết "số này của ai" mà không thấy số."""

    def __init__(self, *, year: int | None = None) -> None:
        self.year = year
        self._numbers: dict[tuple[str, str], int] = {}
        self._last: dict[str, int] = {}
        self._total = 0

    def mask(self, text: str) -> Masked:
        spans = find(text, year=self.year)
        labels = []
        for s in spans:
            key = (s.kind, _canonical(text[s.start:s.end], s.kind))
            if key not in self._numbers:
                self._numbers[key] = self._last[s.kind] = self._last.get(s.kind, 0) + 1
            n = self._numbers[key]
            # quá 999 giá trị khác nhau trong một lượt thì dùng nhãn trơn (LABEL_RE chỉ nhận tới 3 chữ số)
            labels.append(f"[{LABELS[s.kind]}-{n}]" if n < 1000 else f"[{LABELS[s.kind]}]")
        self._total += len(spans)
        return _masked(text, spans, labels)

    @property
    def total(self) -> int:
        """Tổng số chỗ đã che qua mọi lần gọi (đếm số lần xuất hiện, không phải số giá trị khác nhau)."""
        return self._total


def _access_path(path: str) -> str:
    """Đường dẫn của dòng truy cập: bỏ chuỗi truy vấn (đã mã hóa phần trăm, regex không thấy: ``0912%20345…``,
    ``ten%40example.com``; họ tên thì không nhận dạng được), che phần còn lại."""
    head, sep, _ = path.partition("?")
    return mask_text(head) + ("?…" if sep else "")


class PiiFilter(logging.Filter):
    """Che chuỗi cuối cùng của bản ghi: message đã ghép tham số, traceback, stack. Luôn trả True, idempotent.

    ``access=True`` cho uvicorn.access: ``args`` là bộ 5 (client, method, full_path, http_version, status) — chỉ đổi
    full_path (bỏ truy vấn), giữ dạng bộ 5 để ``AccessFormatter`` của uvicorn vẫn định dạng được. Che hỏng thì thay cả
    bản ghi bằng sự kiện ``core.log.redaction_failed``: thà mất một dòng còn hơn lọt dữ liệu."""

    def __init__(self, *, access: bool = False) -> None:
        super().__init__()
        self.access = access

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if self.access and isinstance(record.args, tuple) and len(record.args) == 5:
                client, method, path, version, status = record.args
                record.args = (client, method, _access_path(str(path)), version, status)
            else:
                record.msg, record.args = mask_text(record.getMessage()), None
                # uvicorn in màu thì dùng color_message (mẫu riêng của nó) thay cho msg: bỏ để chỉ còn bản đã che
                record.__dict__.pop("color_message", None)
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            # Formatter dùng exc_text đã che; bỏ exc_info để không formatter nào dựng lại traceback chưa che
            record.exc_info = None
            if record.exc_text:
                record.exc_text = mask_text(record.exc_text)
            if record.stack_info:
                record.stack_info = mask_text(record.stack_info)
        except Exception:  # noqa: BLE001 — lỗi gì cũng không được để lọt bản gốc
            record.msg = json.dumps({"event": "core.log.redaction_failed", "logger": record.name}, ensure_ascii=False)
            record.args = record.exc_info = record.exc_text = record.stack_info = None
        return True


def install_log_redaction(service_logger: logging.Logger) -> None:
    """Gắn ``PiiFilter`` vào logger của dịch vụ, uvicorn.error, uvicorn (handler mặc định nhận bản ghi uvicorn.*
    truyền lên) và mọi handler hiện có của chúng; ``PiiFilter(access=True)`` vào uvicorn.access và handler của nó.
    Gọi sau khi uvicorn đã dựng logger (uvicorn cấu hình logging trước khi gọi factory). Gọi nhiều lần vẫn chỉ một bộ
    lọc ở mỗi chỗ. Bộ lọc của logger không chạy cho bản ghi truyền lên từ logger con, nên gắn cả vào handler."""
    for logger, access in ((service_logger, False), (logging.getLogger("uvicorn.error"), False),
                           (logging.getLogger("uvicorn"), False), (logging.getLogger("uvicorn.access"), True)):
        for where in (logger, *logger.handlers):
            if not any(isinstance(f, PiiFilter) for f in where.filters):
                where.addFilter(PiiFilter(access=access))


def main(argv: list[str] | None = None) -> int:
    """``mask``: stdin → bản che (nhãn trơn). ``count``: stdin → {"chars", "total", "spans"}, không in giá trị."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in ("mask", "count"):
        print(f"cách dùng: python -m {__package__ or 'svc_files'}.pii mask|count < tệp", file=sys.stderr)
        return 2
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
    text = raw.decode("utf-8", errors="replace")
    if args[0] == "mask":
        out = mask_text(text)
    else:
        masked = mask(text)
        out = json.dumps({"chars": len(text), "total": len(masked.spans), "spans": masked.counts()},
                         ensure_ascii=False) + "\n"
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.flush()
        sys.stdout.buffer.write(out.encode("utf-8"))
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
