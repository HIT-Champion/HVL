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

"""Quy tắc trích thông tin tiếp nhận từ chữ của văn bản đến (F4.1) — thuần Python, không I/O, kiểm thử được.

Theo thể thức NĐ 30/2020/NĐ-CP: phần đầu trang 1 có cơ quan ban hành và "Số: …" ở cột trái, quốc hiệu và
"<địa danh>, ngày … tháng … năm …" ở cột phải; dưới là tên loại văn bản (in hoa, giữa trang) và trích yếu, hoặc
"V/v …" dưới số ký hiệu nếu là công văn. Mỗi trường kèm độ tin cậy:

- ``high``: đúng vị trí, đúng dạng, không phải sửa gì (giao diện điền sẵn, nhãn xanh);
- ``medium``: phải đoán hoặc sửa (chữ O thành số 0, ghép hai dòng, chỉ có mẫu trần…) — vẫn điền, nhãn vàng;
- ``low``: chỉ gợi ý, không điền (ngày sau hôm nay, câu đầu của thân làm trích yếu).

Regex chạy trên ``fold(text)`` (bỏ dấu, giữ nguyên độ dài) nên OCR mất dấu vẫn khớp; giá trị cắt từ chữ gốc theo
vị trí khớp. Không regex nào có lượng từ lồng nhau không chặn; đầu vào cắt ở 20 000 ký tự (test hiệu năng).
Không chữ nào của văn bản được ghi nhật ký ở đây.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .layout import Line, clean

Confidence = Literal["high", "medium", "low"]

MAX_CHARS = 20_000       # chỉ xét từng này ký tự đầu
MAX_BODY = 6_000         # phần thân gửi cho mô hình (nếu bật)
MAX_SYMBOL = 50          # như schemas/van-ban-den.json
MAX_ISSUER = 200
MIN_SUMMARY, MAX_SUMMARY = 10, 500
HEAD_Y = 0.45            # vùng đầu: dòng trang 1 có y < HEAD_Y …
HEAD_LINES = 30          # … hoặc 30 dòng đầu khi không có tọa độ
LOW_TEXT = 80            # ít hơn từng này ký tự chữ, số: cảnh báo low_text

# Danh mục loại văn bản (office.document_types, NĐ 30 Phụ lục III) + vài loại văn bản quy phạm chưa có trong danh mục:
# tên loại dùng để nhận dòng tiêu đề và viết trích yếu, mã chỉ trả khi có trong type_codes
TYPE_NAMES = {
    "CV": "Công văn", "NQ": "Nghị quyết", "QĐ": "Quyết định", "CT": "Chỉ thị", "QC": "Quy chế", "QYĐ": "Quy định",
    "TC": "Thông cáo", "TB": "Thông báo", "HD": "Hướng dẫn", "CTr": "Chương trình", "KH": "Kế hoạch",
    "PA": "Phương án", "ĐA": "Đề án", "DA": "Dự án", "BC": "Báo cáo", "BB": "Biên bản", "TTr": "Tờ trình",
    "HĐ": "Hợp đồng", "CĐ": "Công điện", "BGN": "Bản ghi nhớ", "BTT": "Bản thỏa thuận", "GUQ": "Giấy ủy quyền",
    "GM": "Giấy mời", "GGT": "Giấy giới thiệu", "GNP": "Giấy nghỉ phép", "PG": "Phiếu gửi", "PC": "Phiếu chuyển",
    "PB": "Phiếu báo",
    "TT": "Thông tư", "NĐ": "Nghị định", "TTLT": "Thông tư liên tịch",
}
CATALOG = frozenset(TYPE_NAMES) - {"TT", "NĐ", "TTLT"}   # mặc định khi không truyền type_codes

URGENCY = {"HOATOC": "hoa_toc", "THUONGKHAN": "thuong_khan", "KHAN": "khan"}

# ---------------------------------------------------------------------------------------------------------------
# Bỏ dấu giữ nguyên độ dài: mỗi ký tự Latin có dấu → chữ gốc (đ → d, Đ → D); ký tự khác giữ nguyên


def _fold_table() -> dict[int, str]:
    table = {ord("đ"): "d", ord("Đ"): "D", 0xD0: "D", 0xF0: "d", 0x189: "D", 0x111: "d", 0x110: "D"}
    for start, end in ((0xC0, 0x250), (0x1E00, 0x1F00)):
        for cp in range(start, end):
            base = unicodedata.normalize("NFD", chr(cp))[0]
            if base != chr(cp) and base.isascii():
                table.setdefault(cp, base)
    return table


_FOLD = _fold_table()


def fold(s: str) -> str:
    """Bỏ dấu tiếng Việt, GIỮ NGUYÊN ĐỘ DÀI (``len(fold(s)) == len(s)`` với chữ NFC): vị trí khớp trên chữ đã bỏ dấu
    cũng là vị trí trên chữ gốc."""
    return s.translate(_FOLD)


# ---------------------------------------------------------------------------------------------------------------
# Mẫu (các ví dụ trong tests/test_docread_rules.py đều chạy qua)

SYMBOL = re.compile(r"\b(?P<pre>[Ss][Oo06])\s*[:.;]?\s*(?P<sym>(?P<num>[0-9OoIl]{1,5})[A-Za-z]?\s*/\s*"
                    r"(?:(?:19|20)[0-9]{2}\s*/\s*)?[A-Za-z0-9&]{1,12}(?:\s*-\s*[A-Za-z0-9&]{1,12}){0,4})")
BARE = re.compile(r"(?<![\w/])(?P<sym>[0-9]{1,5}/(?:(?:19|20)[0-9]{2}/)?[A-Z][A-Za-z&]{0,11}"
                  r"(?:-[A-Z0-9][A-Za-z0-9&]{0,11}){1,4})(?![\w/])")
NO_NUMBER = re.compile(r"\b[Ss][Oo06]\s*[:;]?[\s._…]*/\s*[A-Za-z]")       # "Số:   /QĐ-UBND" chưa điền số
DATE = re.compile(r"(?i)(?:(?P<place>[A-Z][A-Za-z.' ]{1,40}?)\s*,\s*)?ng[a-z]{0,2}y\s+(?P<d>[0-9]{1,2})\s+"
                  r"th[a-z]{0,2}ng\s+(?P<m>[0-9]{1,2})\s+n[a-z]{0,2}m\s+(?P<y>(?:19|20)[0-9]{2})\b")
DATE_NUM = re.compile(r"(?i)ng[a-z]{0,2}y\s+(?P<d>[0-9]{1,2})\s*[/.-]\s*(?P<m>[0-9]{1,2})\s*[/.-]\s*"
                      r"(?P<y>(?:19|20)[0-9]{2})\b")
VV = re.compile(r"(?i)^\s*(?:V\s*/\s*v\b|ve\s+viec\b)[\s.:]*")
MOTTO = re.compile(r"CONG\s*HOA\s*XA\s*HOI\s*CHU\s*NGHIA\s*VIET\s*NAM|DOC\s*LAP\s*-?\s*TU\s*DO\s*-?\s*HANH\s*PHUC")
RULE_LINE = re.compile(r"^[-_=.*~ ]+$")
DASHES = re.compile("[‐-―−]")
_SYM_SPACES = re.compile(r"\s*([/-])\s*")
_SENTENCE_END = re.compile(r"(?<![A-ZĐ])[.!?;](?=\s|$)")
# Hết trích yếu: "Kính gửi", "Căn cứ …", "Theo đề nghị …", "Điều 1." (không phải "điều kiện")
STOP_WORDS = re.compile(r"^[\s\-+•*:]*(?:KINH\s+GUI|CAN\s+CU|THEO\s+DE\s+NGHI|DIEU\s+[0-9]+)\b")

# Cơ quan ban hành --------------------------------------------------------------------------------------------
# Cấp hành chính (sau nó là tên riêng): "ỦY BAN NHÂN DÂN" + "TỈNH MẪU" là một tên, ghép lại
LEVELS = (("THANH", "PHO"), ("THI", "XA"), ("THI", "TRAN"), ("TINH",), ("HUYEN",), ("QUAN",), ("XA",), ("PHUONG",),
          ("TP",), ("TP.",))
# Đầu tên một tổ chức: dòng dưới bắt đầu bằng chúng là đơn vị (dòng trên là cơ quan chủ quản); không thì là phần tiếp
# của tên ở dòng trên bị xuống dòng ("CÔNG TY CỔ PHẦN" / "CÔNG NGHỆ MẪU")
ORG_HEADS = tuple(tuple(h.split()) for h in (
    "BO", "SO", "BAN", "CUC", "TONG CUC", "CHI CUC", "VU", "VIEN", "TRUONG", "PHONG", "KHOA", "BO MON", "TRUNG TAM",
    "CONG TY", "TONG CONG TY", "TAP DOAN", "NGAN HANG", "CHI NHANH", "UY BAN", "UBND", "HOI DONG", "HDND", "DAI HOC",
    "HOC VIEN", "BENH VIEN", "VAN PHONG", "THANH TRA", "TOA AN", "KHO BAC", "DANG UY", "DANG BO", "TINH UY",
    "THANH UY", "HUYEN UY", "CONG DOAN", "DOAN", "HOI", "LIEN DOAN", "LIEN HIEP", "MAT TRAN", "MTTQ", "UBMTTQ",
    "PHAN HIEU", "CO SO", "TRAM", "DAI", "BAO", "NHA XUAT BAN", "THU VIEN", "QUY", "HOP TAC XA", "BQL",
))
CONNECTORS = {"VA", "CUA", "-", "&", ",", "VE", "TAI"}
# Từ viết tắt giữ nguyên chữ in hoa (ngoài ra: từ có "&", từ không có nguyên âm)
ABBREVIATIONS = {"UBND", "HĐND", "ĐHQG", "ĐHQGHN", "ĐHQGHCM", "GD&ĐT", "KH&CN", "LĐTB&XH", "TP", "TNHH", "CP",
                 "MTTQ", "UBMTTQ", "CNTT", "THPT", "THCS", "BQL", "KCN", "TW", "VN", "ĐH", "CĐ", "QĐ", "SKHCN",
                 "USD", "IT", "AI"}
SMALL_WORDS = {"VÀ", "CỦA", "VỀ", "TẠI", "CHO", "THEO", "VỚI", "TRÊN", "THUỘC", "TRỰC"}
# Cụm từ hay gặp trong tên cơ quan, viết đúng hoa thường; khớp theo chữ đã bỏ dấu, chỉ lấy kiểu hoa thường
PHRASES = (
    "Ủy ban nhân dân", "Hội đồng nhân dân", "Mặt trận Tổ quốc", "Đại học", "Học viện", "Cao đẳng",
    "Trung học phổ thông", "Trung học cơ sở", "Tiểu học", "Mầm non", "Giáo dục và Đào tạo", "Khoa học và Công nghệ",
    "Công nghệ thông tin", "Thông tin và Truyền thông", "Tài nguyên và Môi trường", "Tài nguyên",
    "Lao động - Thương binh và Xã hội", "Kế hoạch và Đầu tư", "Nông nghiệp và Phát triển nông thôn",
    "Văn hóa, Thể thao và Du lịch", "Giao thông vận tải", "Tài chính", "Nội vụ", "Tư pháp", "Y tế", "Xây dựng",
    "Công thương", "Đào tạo", "Khảo thí và Đảm bảo chất lượng", "Tổ chức - Hành chính", "Tổ chức cán bộ",
    "Hành chính", "Công tác sinh viên", "Kế hoạch - Tài chính", "Hợp tác quốc tế", "Khoa học", "Quốc gia",
    "Công ty", "Cổ phần", "Trách nhiệm hữu hạn", "Tập đoàn", "Tổng công ty", "Trung tâm", "Văn phòng", "Quản lý",
    "Nghiên cứu", "Phần mềm", "Công nghệ", "Dịch vụ", "Kinh tế", "Phân hiệu", "Bệnh viện", "Ngân hàng", "Dự án",
)


def _phrase_key(text: str) -> tuple[str, ...]:
    return tuple(fold(text).upper().split())


_PHRASES = sorted(((_phrase_key(p), tuple(w[0].isupper() for w in p.split())) for p in PHRASES),
                  key=lambda item: -len(item[0]))
_TITLES = {re.sub("[^A-Z]", "", fold(name).upper()): code for code, name in TYPE_NAMES.items()}


@dataclass(frozen=True)
class Field:
    value: str
    confidence: Confidence
    source: Literal["rule", "model"] = "rule"


@dataclass(frozen=True)
class Suggestion:
    fields: dict[str, Field]
    warnings: tuple[str, ...]
    body: str             # phần thân ≤ 6000 ký tự, cho mô hình viết trích yếu


# ---------------------------------------------------------------------------------------------------------------
# Dòng đã chuẩn hóa


@dataclass
class _Ln:
    text: str             # NFC, gộp khoảng trắng — giá trị cắt từ đây
    key: str              # fold + gạch nối, gạch chéo chuẩn: cùng độ dài với text, regex chạy trên đây
    x0: float
    x1: float
    y: float
    page: int
    i: int = 0            # thứ tự trong tài liệu

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def left(self) -> bool:
        return self.cx < 0.5

    @property
    def right(self) -> bool:
        return self.cx >= 0.5 and self.x0 >= 0.35

    @property
    def letters(self) -> str:
        return "".join(ch for ch in self.text if ch.isalpha())

    @property
    def upper(self) -> bool:
        """In hoa: ≥ 80% chữ cái là chữ hoa."""
        letters = self.letters
        return len(letters) >= 2 and sum(ch.isupper() for ch in letters) >= 0.8 * len(letters)

    def starts(self, *words: str) -> bool:
        head = self.key.lstrip(" -+•*:").upper()
        return any(head.startswith(w) for w in words)


def _num(value: object, default: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return min(max(number, 0.0), 1.0) if number == number else default


def _norm(text: object) -> str:
    return clean(str(text)[:2 * MAX_CHARS])


def _key(text: str) -> str:
    return fold(DASHES.sub("-", text).replace("／", "/"))


def _sentence_case(part: str) -> str:
    """"Lịch đăng ký…" → "lịch đăng ký…" để nối sau tên loại; giữ từ viết tắt ("ĐHCN…")."""
    if len(part) >= 2 and part[0].isupper() and part[1].islower():
        return part[0].lower() + part[1:]
    return part


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,;:-")


class _Doc:
    def __init__(self, lines: Sequence[Line]) -> None:
        self.truncated = False
        items: list[_Ln] = []
        total = 0
        for line in lines:
            text = _norm(getattr(line, "text", ""))
            if not text:
                continue
            if total >= MAX_CHARS:                     # còn chữ mà đã đủ: bỏ phần còn lại
                self.truncated = True
                break
            if total + len(text) > MAX_CHARS:
                text = text[:MAX_CHARS - total].rstrip()
                self.truncated = True
            page = getattr(line, "page", 1)
            items.append(_Ln(text, _key(text), _num(getattr(line, "x0", 0.0), 0.0), _num(getattr(line, "x1", 1.0), 1.0),
                             _num(getattr(line, "y", 0.0), 0.0), page if isinstance(page, int) else 1))
            total += len(text)
        self.positioned = any(ln.x0 > 0.001 or ln.x1 < 0.999 for ln in items)
        if self.positioned:
            items.sort(key=lambda ln: (ln.page, ln.y, ln.x0))
        for i, ln in enumerate(items):
            ln.i = i
        self.lines = items
        first = min((ln.page for ln in items), default=1)
        self.page1 = [ln for ln in items if ln.page == first]
        self.head = ([ln for ln in self.page1 if ln.y < HEAD_Y] if self.positioned else self.page1[:HEAD_LINES])
        self._steps: dict[int, float] = {}

    def step(self, page: int) -> float:
        """Khoảng cách dòng điển hình của trang: tứ phân vị dưới của khoảng cách tới dòng kế dưới cùng cột (dòng chung
        hàng ở cột bên kia không tính) — phần lớn các dòng liền nhau, chỗ cách đoạn không kéo giá trị lên."""
        if page not in self._steps:
            lines = [ln for ln in self.lines if ln.page == page]
            gaps = []
            for i, a in enumerate(lines):
                for b in lines[i + 1:i + 50]:
                    if b.y - a.y > 0.002 and min(a.x1, b.x1) > max(a.x0, b.x0):
                        gaps.append(b.y - a.y)
                        break
            self._steps[page] = sorted(gaps)[len(gaps) // 4] if gaps else 0.02
        return self._steps[page]

    def adjacent(self, a: _Ln, b: _Ln) -> bool:
        """b ngay dưới a, không cách dòng trống."""
        return not self.positioned or (a.page == b.page and b.y - a.y <= 1.6 * self.step(a.page) + 1e-9)

    def after(self, line: _Ln) -> list[_Ln]:
        """Các dòng sau ``line`` trên cùng trang, bỏ dòng chung hàng."""
        return [ln for ln in self.lines[line.i + 1:] if ln.page == line.page
                and (not self.positioned or ln.y > line.y + 1e-9)]


# ---------------------------------------------------------------------------------------------------------------
# 1. Số, ký hiệu


@dataclass
class _Symbol:
    line: _Ln
    value: str
    confidence: Confidence


def _fix_symbol(raw: str, num: str) -> tuple[str, bool]:
    """Bỏ khoảng trắng quanh "/", "-", dấu câu cuối; trong phần số O, o → 0, I, l → 1. Trả (giá trị, đã phải sửa)."""
    value = _SYM_SPACES.sub(r"\1", DASHES.sub("-", raw).replace("／", "/")).strip().rstrip(".,;:-")
    fixed = num.translate(str.maketrans("OoIl", "0011"))
    return fixed + value[len(num):], fixed != num


def _symbol(doc: _Doc, warnings: list[str]) -> _Symbol | None:
    head = doc.head
    order = sorted(head, key=lambda ln: (not ln.left, ln.i)) if doc.positioned else head
    for ln in order:
        for m in SYMBOL.finditer(ln.key):
            before = ln.key[:m.start()]
            at_start = not any(ch.isalnum() for ch in before)
            # "Số" viết hoa hoặc đứng đầu dòng: "theo công văn số 47/KHCN…" giữa câu không phải số của văn bản này
            if not at_start and m.group("pre")[0] != "S":
                continue
            if not any(ch.isdigit() for ch in m.group("num")):
                continue
            value, fixed = _fix_symbol(ln.text[m.start("sym"):m.end("sym")], m.group("num"))
            if len(value) > MAX_SYMBOL:
                continue
            clean_prefix = m.group("pre").lower() == "so"
            confident = at_start and clean_prefix and not fixed
            return _Symbol(ln, value, "high" if confident else "medium")
    for ln in head:
        if NO_NUMBER.search(ln.key):
            warnings.append("symbol_no_number")
            return None
    for ln in order:
        m = BARE.search(ln.key)
        # mẫu trần chỉ khi đứng đầu dòng hoặc dòng ngắn: "Theo Công văn 47/KHCN-ĐT, …" là câu của phần thân
        if m and (not any(ch.isalnum() for ch in ln.key[:m.start()]) or len(ln.text.split()) <= 4):
            value = ln.text[m.start("sym"):m.end("sym")]
            if len(value) <= MAX_SYMBOL:
                return _Symbol(ln, value, "medium")
    return None


def _symbol_type(value: str, codes: Collection[str]) -> str | None:
    """Mã loại ngay sau số (và năm) trong ký hiệu: "123/QĐ-UBND" → QĐ, "45/2026/TT-BTN" → TT."""
    parts = value.split("/")
    k = 2 if len(parts) > 2 and re.fullmatch(r"(?:19|20)[0-9]{2}", parts[1]) else 1
    if len(parts) <= k:
        return None
    return _code(parts[k].split("-")[0], codes)


def _code(text: str, codes: Collection[str]) -> str | None:
    exact = [c for c in codes if c.casefold() == text.casefold()]
    if exact:
        return exact[0]
    loose = [c for c in codes if fold(c).casefold() == fold(text).casefold()]
    return loose[0] if len(loose) == 1 else None


# ---------------------------------------------------------------------------------------------------------------
# 2. Ngày ban hành


def _issued_on(doc: _Doc, today: date, warnings: list[str]) -> tuple[_Ln, Field] | None:
    order = sorted(doc.head, key=lambda ln: (not ln.right, ln.i)) if doc.positioned else doc.head
    for ln in order:
        found = None
        m = DATE.search(ln.key)
        if m:
            at_start = not any(ch.isalpha() for ch in ln.key[:m.start()])
            if m.group("place"):
                found = (m, "high")
            elif at_start:            # "ngày … tháng … năm …" đứng riêng một dòng; giữa câu là ngày trong thân
                found = (m, "medium")
        if found is None:
            m = DATE_NUM.search(ln.key)
            if m and ln.key[:m.start()].rstrip().endswith(","):
                found = (m, "medium")
        if found is None:
            continue
        m, confidence = found
        try:
            issued = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        except ValueError:
            warnings.append("invalid_date")
            return None
        if issued > today:
            warnings.append("future_date")
            confidence = "low"
        return ln, Field(issued.isoformat(), confidence)
    return None


# ---------------------------------------------------------------------------------------------------------------
# 3. Cơ quan ban hành


def _words(text: str) -> list[str]:
    return fold(text).upper().split()


def _starts_with(words: list[str], heads: Sequence[tuple[str, ...]]) -> bool:
    return any(tuple(words[:len(h)]) == h for h in heads)


def _level_at(words: list[str], originals: list[str], i: int) -> int:
    """Độ dài cụm cấp hành chính bắt đầu ở từ i (0: không phải)."""
    for level in LEVELS:
        if tuple(words[i:i + len(level)]) == level:
            if level == ("QUAN",) and originals[i].upper() not in ("QUẬN", "QUAN"):
                continue                # "QUẢN LÝ" không phải cấp hành chính
            if level == ("XA",) and words[i + 1:i + 2] == ["HOI"]:
                continue                # "XÃ HỘI"
            return len(level)
    return 0


def _locality(text: str) -> str | None:
    """"UBND TỈNH MẪU" → "TỈNH MẪU": để "Sở Khoa học và Công nghệ" dưới dòng chủ quản thành "… tỉnh Mẫu"."""
    originals = text.split()
    words = [fold(w).upper() for w in originals]
    for i in range(len(words)):
        if _level_at(words, originals, i) and i + _level_at(words, originals, i) < len(words):
            return " ".join(originals[i:])
    return None


def _is_abbreviation(word: str) -> bool:
    core = word.strip(".,;:()")
    letters = [ch for ch in fold(core).upper() if ch.isalpha()]
    return (core.upper() in ABBREVIATIONS or "&" in core or any(ch.isdigit() for ch in core)
            or (bool(letters) and not any(ch in "AEIOUY" for ch in letters)))


def _cap(word: str) -> str:
    lower = word.lower()
    for i, ch in enumerate(lower):
        if ch.isalpha():
            return lower[:i] + ch.upper() + lower[i + 1:]
    return lower


def title_case(name: str) -> str:
    """Tên in hoa → viết thường có hoa đầu: "ỦY BAN NHÂN DÂN TỈNH MẪU" → "Ủy ban nhân dân tỉnh Mẫu". Giữ từ viết
    tắt; cụm từ quen dùng theo bảng; sau cấp hành chính là tên riêng, viết hoa từng từ; từ còn lại hoa chữ đầu."""
    originals = name.split()
    words = [fold(w).upper() for w in originals]
    out: list[str] = []
    proper = False
    i = 0
    while i < len(originals):
        level = _level_at(words, originals, i)
        if level:
            for j in range(i, i + level):
                w = originals[j]
                out.append(w if _is_abbreviation(w) else (_cap(w) if j == 0 else w.lower()))
            proper = True
            i += level
            continue
        if proper:
            out.append(originals[i] if _is_abbreviation(originals[i]) else _cap(originals[i]))
            i += 1
            continue
        for key, pattern in _PHRASES:
            if tuple(words[i:i + len(key)]) == key:
                for j, cap in enumerate(pattern):
                    w = originals[i + j]
                    out.append(_cap(w) if cap or i + j == 0 else w.lower())
                i += len(key)
                break
        else:
            w = originals[i]
            if _is_abbreviation(w):
                out.append(w)
            elif i > 0 and w.upper() in SMALL_WORDS:
                out.append(w.lower())
            else:
                out.append(_cap(w))
            i += 1
    return " ".join(out)


def _issuer_lines(doc: _Doc, symbol: _Symbol | None) -> tuple[list[str], bool]:
    """Các dòng in hoa của cơ quan ban hành (trên xuống) và cờ đã phải cắt quốc hiệu dính cùng dòng."""
    if doc.positioned:      # cột trái; dòng dính quốc hiệu (không tách được cột) thì bắt đầu ở nửa trái
        pool = [ln for ln in doc.head if ln.left or (ln.x0 < 0.3 and MOTTO.search(ln.key.upper()))]
    else:
        pool = list(doc.head)
    if symbol is not None and symbol.line in pool:
        pool = [ln for ln in pool if (ln.y < symbol.line.y if doc.positioned else ln.i < symbol.line.i)]
    out: list[str] = []
    cut = False
    for ln in pool:
        if symbol is None and out and not ln.upper and not MOTTO.search(ln.key.upper()):
            break                                       # không có dòng "Số": khối in hoa đầu trang là hết
        text, key = ln.text, ln.key.upper()
        motto = MOTTO.search(key)
        if motto:                                       # quốc hiệu cùng dòng: lấy phần trước nó
            text, key = text[:motto.start()].strip(), key[:motto.start()].strip()
            cut = cut or bool(text)
        letters = [ch for ch in text if ch.isalpha()]
        if (len(letters) < 3 or RULE_LINE.match(text) or sum(ch.isupper() for ch in letters) < 0.8 * len(letters)
                or re.sub("[^A-Z]", "", key) in URGENCY or re.sub("[^A-Z]", "", key) in _TITLES
                or SYMBOL.search(ln.key) or DATE.search(ln.key)):
            continue
        out.append(text)
    return out, cut


def _issuer(doc: _Doc, symbol: _Symbol | None) -> Field | None:
    lines, cut = _issuer_lines(doc, symbol)
    if not lines:
        return None
    blocks = [lines[0]]
    for text in lines[1:]:
        words, prev = _words(text), _words(blocks[-1])
        if (_level_at(words, text.split(), 0) or not _starts_with(words, ORG_HEADS)
                or (prev and prev[-1] in CONNECTORS)):
            blocks[-1] += " " + text                   # phần tiếp của tên ở dòng trên
        else:
            blocks.append(text)                        # dòng trên là cơ quan chủ quản
    name = blocks[-1]
    if len(blocks) >= 2 and not _locality(name):
        locality = _locality(blocks[-2])
        if locality:
            name += " " + locality
    confidence: Confidence = "high" if len(lines) == 1 and doc.positioned and not cut else "medium"
    value = _clip(title_case(name), MAX_ISSUER)
    return Field(value, confidence) if value else None


# ---------------------------------------------------------------------------------------------------------------
# 4. Loại văn bản (dòng tiêu đề)


def _title(doc: _Doc, anchor: _Ln | None) -> tuple[_Ln, str] | None:
    """Dòng tên loại sau vùng "Số"/ngày, giữa trang, in hoa; chữ giãn ("T H Ô N G  B Á O") bỏ khoảng trắng."""
    pool = [ln for ln in doc.page1 if anchor is None or (ln.y > anchor.y if doc.positioned else ln.i > anchor.i)]
    rows: list[list[_Ln]] = []
    for ln in pool:
        if rows and doc.positioned and abs(rows[-1][0].y - ln.y) < 1e-9:
            rows[-1].append(ln)
        else:
            rows.append([ln])
        if len(rows) > 15:
            break
    for row in rows:
        if row[0].starts("KINH GUI"):
            return None
        joined = _Ln(" ".join(ln.text for ln in row), " ".join(ln.key for ln in row), row[0].x0, row[-1].x1,
                     row[0].y, row[0].page, row[0].i)
        for ln in (*row, joined) if len(row) > 1 else row:
            if not ln.upper or len(ln.letters) < 4:
                continue
            if doc.positioned and abs(ln.cx - 0.5) > 0.2:
                continue
            code = _TITLES.get(re.sub("[^A-Z]", "", ln.key.upper()))
            if code:
                return row[0], code
    return None


# ---------------------------------------------------------------------------------------------------------------
# 5. Trích yếu


def _stop(ln: _Ln) -> bool:
    return (bool(STOP_WORDS.match(ln.key.upper())) or ln.upper
            or bool(SYMBOL.search(ln.key)) or bool(DATE.search(ln.key)) or bool(MOTTO.search(ln.key.upper())))


def _vv(doc: _Doc, symbol: _Symbol | None, title: _Ln | None) -> tuple[_Ln, Field] | None:
    """(a) "V/v …" dưới số ký hiệu, cùng cột trái, tới dòng trống / "Kính gửi" / dòng không thuộc cột trái. Dòng
    "Về việc …" dưới tên loại là trích yếu kiểu (b), không xét ở đây."""
    for ln in doc.head:
        if doc.positioned and (not ln.left or (symbol is not None and ln.y <= symbol.line.y)):
            continue
        if not doc.positioned and symbol is not None and ln.i <= symbol.line.i:
            continue
        if title is not None and ln.i > title.i:
            break
        m = VV.match(ln.key)
        if not m:
            continue
        parts, last = [ln.text[m.end():]], ln
        for nxt in doc.after(ln):
            if doc.positioned and nxt.x0 >= 0.5:
                continue                                # cột phải (địa danh, ngày) cùng tầm: bỏ qua
            if (doc.positioned and not nxt.left) or not doc.adjacent(last, nxt) or _stop(nxt) or VV.match(nxt.key):
                break
            parts.append(nxt.text)
            last = nxt
            if len(parts) > 4:
                break
        rest = _norm(" ".join(parts)).lstrip(" :.-")
        value = _clip("Về việc " + _sentence_case(rest), MAX_SUMMARY)
        if len(rest) >= 3 and len(value) >= MIN_SUMMARY:
            return ln, Field(value, "high")
        return ln, Field("", "low")
    return None


def _after_title(doc: _Doc, title: _Ln, code: str) -> tuple[Field, _Ln] | None:
    """(b) dòng ngay sau tên loại, giữa trang, tới "Căn cứ" / "Kính gửi" / dòng trống / dòng in hoa."""
    parts: list[str] = []
    last = title
    for nxt in doc.after(title):
        if parts and doc.positioned and nxt.y - last.y < 1e-9:
            continue
        near = doc.adjacent(last, nxt)
        if not near and not parts and doc.positioned:
            # cách tên loại một khoảng nhỏ (lề của tiêu đề): chỉ nhận dòng căn giữa rõ ràng, không chạm hai lề như
            # dòng đầu đoạn văn của phần thân
            near = (nxt.x0 >= 0.1 and nxt.x1 <= 0.9 and nxt.page == last.page
                    and nxt.y - last.y <= 3.2 * doc.step(last.page))
        if (not near or _stop(nxt) or (doc.positioned and abs(nxt.cx - 0.5) > 0.2)
                or not any(ch.isalnum() for ch in nxt.text)):       # dòng cuối có thể chỉ là "2026–2027"
            break
        parts.append(nxt.text)
        last = nxt
        if len(parts) >= 3:
            break
    if not parts:
        return None
    value = _clip(TYPE_NAMES[code] + " " + _sentence_case(_norm(" ".join(parts))), MAX_SUMMARY)
    return (Field(value, "high"), last) if len(value) >= MIN_SUMMARY else None


def _first_sentence(doc: _Doc, start: _Ln) -> Field | None:
    """(c) câu đầu của thân sau "Kính gửi" (bỏ danh sách nơi nhận "- …"), cắt ở ranh giới từ ≤ 200 ký tự."""
    taken: list[str] = []
    started = False
    for nxt in doc.lines[start.i + 1:]:
        if not started and (nxt.starts("-", "+", "•") or nxt.text[:1] in "-+•" or nxt.upper
                            or (doc.positioned and nxt.y - start.y < 1e-9)):
            continue
        started = True
        taken.append(nxt.text)
        if sum(map(len, taken)) > 400:
            break
    text = _norm(" ".join(taken))
    m = _SENTENCE_END.search(text)
    sentence = _clip(text[:m.start()] if m else text, 200).rstrip(" .;,:")
    return Field(sentence, "low") if len(sentence) >= MIN_SUMMARY else None


# ---------------------------------------------------------------------------------------------------------------


def _rows_text(lines: Sequence[_Ln]) -> str:
    """Chữ theo hàng: các đoạn cùng hàng nối bằng khoảng trắng, các hàng xuống dòng."""
    rows: list[list[str]] = []
    prev: _Ln | None = None
    for ln in lines:
        if prev is not None and (ln.page, ln.y) == (prev.page, prev.y) and ln.y > 0:
            rows[-1].append(ln.text)
        else:
            rows.append([ln.text])
        prev = ln
    return "\n".join(" ".join(row) for row in rows)


def _urgency(doc: _Doc) -> Field | None:
    for ln in doc.head:
        value = URGENCY.get(re.sub("[^A-Z]", "", ln.key.upper()))
        if value:
            return Field(value, "high")
    return None


def suggest(lines: Sequence[Line], *, today: date, type_codes: Collection[str] | None = None) -> Suggestion:
    """Gợi ý thông tin tiếp nhận từ các dòng chữ (``layout.text_lines`` / ``tsv_lines``).

    ``fields`` chỉ có khóa đã tìm thấy, trong {type_code, symbol, issued_on, issuer_name, summary, urgency};
    ``warnings`` là mã cố định (future_date, invalid_date, symbol_no_number, type_conflict, low_text, truncated)."""
    codes = list(CATALOG if type_codes is None else type_codes)
    doc = _Doc(lines)
    warnings: list[str] = []
    fields: dict[str, Field] = {}

    symbol = _symbol(doc, warnings)
    issued = _issued_on(doc, today, warnings)
    issuer = _issuer(doc, symbol)

    anchors = [a for a in (symbol.line if symbol else None, issued[0] if issued else None) if a is not None
               and a.page == (doc.page1[0].page if doc.page1 else 1)]
    anchor = max(anchors, key=lambda a: (a.y, a.i) if doc.positioned else (a.i,), default=None)
    title = _title(doc, anchor)
    vv = _vv(doc, symbol, title[0] if title else None)

    # Loại: (a) dòng tiêu đề, (b) có "V/v" thì là công văn, (c) mã ngay sau số trong ký hiệu
    by_title = _code(title[1], codes) if title else None
    by_symbol = _symbol_type(symbol.value, codes) if symbol else None
    by_vv = _code("CV", codes) if vv and not title else None
    chosen = by_title or by_vv
    if chosen:
        if by_symbol and by_symbol != chosen:
            fields["type_code"] = Field(chosen, "medium")
            warnings.append("type_conflict")
        else:
            fields["type_code"] = Field(chosen, "high")
    elif by_symbol:
        fields["type_code"] = Field(by_symbol, "medium")

    if symbol:
        fields["symbol"] = Field(symbol.value, symbol.confidence)
    if issued:
        fields["issued_on"] = issued[1]
    if issuer:
        fields["issuer_name"] = issuer

    # Trích yếu: (a) V/v, (b) dòng sau tên loại, (c) câu đầu của thân
    summary = vv[1] if vv and vv[1].value else None
    body_from: _Ln | None = None
    if summary is None and title:
        after = _after_title(doc, *title)
        if after:
            summary, body_from = after[0], title[0]
    greeting = next((ln for ln in doc.page1 if ln.starts("KINH GUI")), None)
    if summary is None and (greeting or title):
        summary = _first_sentence(doc, greeting or title[0])  # type: ignore[index]
    if summary:
        fields["summary"] = summary

    urgency = _urgency(doc)
    if urgency:
        fields["urgency"] = urgency

    if sum(ch.isalnum() for ln in doc.lines for ch in ln.text) < LOW_TEXT:
        warnings.append("low_text")
    if doc.truncated:
        warnings.append("truncated")

    # Thân cho mô hình: sau dòng tiêu đề / "Kính gửi" (cái nào trước); không có thì cả văn bản
    starts = [ln for ln in (title[0] if title else None, greeting, body_from) if ln is not None]
    start = min(starts, key=lambda ln: ln.i) if starts else None
    rest = doc.lines[start.i + 1:] if start is not None else doc.lines
    body = _rows_text(rest or doc.lines)[:MAX_BODY]

    order = ("type_code", "symbol", "issued_on", "issuer_name", "summary", "urgency")
    return Suggestion({k: fields[k] for k in order if k in fields}, tuple(dict.fromkeys(warnings)), body)
