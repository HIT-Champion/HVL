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

"""Bộ nhận dạng thông tin cá nhân (F4.4, svc_files/pii.py): dương tính, âm tính khó, đột biến dữ liệu vào, vị trí,
Masker, bộ lọc nhật ký; CLI và hiệu năng.

Mọi số, email trong tệp là GIẢ LẬP, hợp lệ về định dạng (số ví dụ phổ biến 0912 345 678, CCCD đuôi 0000xx, email
@example.com theo RFC 2606): có thể trùng số thật nhưng không thuộc người nào trong hệ thống.

Phần kiểm viết thành hàm thuần ``check_*(pii) -> list[str]``: nhận module cần kiểm, trả các ca hỏng. ``failures(pii)``
gom tất cả; test_pii_mutation.py chạy nó trên từng bản đột biến của pii.py — mọi đột biến phải bị bắt.

Đột biến dữ liệu vào (test metamorphic): mỗi toán tử nhận một ca dương tính một giá trị và trả (chuỗi mới, kỳ vọng);
kỳ vọng do chính toán tử định nghĩa, không lấy từ mã đang test.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import random
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator

import pytest

from svc_files import pii

YEAR = 2026
CCCD = ("001205000017", "079305000123", "036099000045")
PHONES = ("0912 345 678", "0812.345.678", "+84 912 345 678", "(024) 3000 0000", "0203 1234 567")
EMAILS = ("nguyenvanb@example.com", "phong.dao-tao+cv@dhm.example.edu.vn")
ACCOUNT = "0011 0041 23456"
CC = ("(+84)", "+84", "0084")
SEPARATORS = " .-\u00a0"

Want = list[tuple[int, int, str]]


def pos(text: str, *items: tuple[str, str], kw: bool = False, mutate: bool = True) -> tuple:
    """Một ca dương tính: (chuỗi, [(giá trị, loại)…] theo thứ tự xuất hiện, có từ khóa?, dùng làm ca gốc đột biến?)."""
    return text, items, kw, mutate


def spans_of(text: str, items: tuple[tuple[str, str], ...]) -> Want:
    """Biên mong đợi: tìm lần lượt từng giá trị, mỗi giá trị sau giá trị trước."""
    out, at = [], 0
    for value, kind in items:
        start = text.index(value, at)
        out.append((start, start + len(value), kind))
        at = start + len(value)
    return out


POSITIVE = [
    # CCCD: liền, 3-3-3-3, 4-4-4, chấm, gạch, trong ngoặc, sau từ khóa (cả mã tỉnh lạ: đi đường từ khóa)
    pos("001205000017", ("001205000017", "cccd")),
    pos("079305000123", ("079305000123", "cccd")),
    pos("Mã 036099000045 ghi ở trang 1", ("036099000045", "cccd")),
    pos("001 205 000 017", ("001 205 000 017", "cccd")),
    pos("0793 0500 0123", ("0793 0500 0123", "cccd")),
    pos("036.099.000.045", ("036.099.000.045", "cccd")),
    pos("001-205-000-017", ("001-205-000-017", "cccd")),
    pos("(CCCD 001205000017)", ("001205000017", "cccd"), kw=True),
    pos("Số CCCD: 079305000123", ("079305000123", "cccd"), kw=True),
    pos("số định danh cá nhân: 036099000045.", ("036099000045", "cccd"), kw=True),
    pos("Căn cước công dân số 098 205 000 017", ("098 205 000 017", "cccd"), kw=True),
    pos("SO DINH DANH 099205000017", ("099205000017", "cccd"), kw=True),
    pos("sinh năm 2026: 001326000017", ("001326000017", "cccd")),          # thế kỷ 21, năm sinh = năm nay
    pos("MST cá nhân: 001205000017", ("001205000017", "cccd")),            # MST cá nhân là số định danh
    # CMND: chỉ khi có từ khóa — có dấu, không dấu, viết hoa; 12 số sau "CMND" vẫn là CMND
    pos("CMND số 123456789", ("123456789", "cmnd"), kw=True),
    pos("Số CMND: 212 345 678", ("212 345 678", "cmnd"), kw=True),
    pos("chứng minh nhân dân số 025123456", ("025123456", "cmnd"), kw=True),
    pos("CHỨNG MINH THƯ: 145 678 901", ("145 678 901", "cmnd"), kw=True),
    pos("cmt so 123456789", ("123456789", "cmnd"), kw=True),
    pos("Số CCCD/CMND: 123456789", ("123456789", "cmnd"), kw=True),
    pos("CMND: 001205000017", ("001205000017", "cmnd"), kw=True, mutate=False),
    # SĐT: liền, 4-3-3, 3-3-4, chấm, gạch, +84, (+84), 0084, (024), máy bàn 11 số, di động 11 số cũ, NBSP
    pos("0912345678", ("0912345678", "phone")),
    pos("0912 345 678", ("0912 345 678", "phone")),
    pos("091 234 5678", ("091 234 5678", "phone")),
    pos("0912.345.678", ("0912.345.678", "phone")),
    pos("0912-345-678", ("0912-345-678", "phone")),
    pos("0812.345.678", ("0812.345.678", "phone")),
    pos("+84 912 345 678", ("+84 912 345 678", "phone")),
    pos("+84912345678", ("+84912345678", "phone")),
    pos("(+84) 912 345 678", ("(+84) 912 345 678", "phone")),
    pos("0084 912 345 678", ("0084 912 345 678", "phone")),
    pos("+84 0912 345 678", ("+84 0912 345 678", "phone")),
    pos("(024) 3000 0000", ("(024) 3000 0000", "phone")),
    pos("024 3000 0000", ("024 3000 0000", "phone")),
    pos("0203 1234 567", ("0203 1234 567", "phone")),
    pos("+84 24 3000 0000", ("+84 24 3000 0000", "phone")),
    pos("0168 123 4567", ("0168 123 4567", "phone")),
    pos("0912\u00a0345\u00a0678", ("0912\u00a0345\u00a0678", "phone")),
    pos("ĐT: \uff10\uff19\uff11\uff12 \uff13\uff14\uff15 \uff16\uff17\uff18",          # chữ số toàn khổ
        ("\uff10\uff19\uff11\uff12 \uff13\uff14\uff15 \uff16\uff17\uff18", "phone"), mutate=False),
    pos("Liên hệ: 0987 654 321.", ("0987 654 321", "phone")),
    pos("Gọi (0912 345 678) nhé", ("0912 345 678", "phone")),
    pos("tel:0912345678", ("0912345678", "phone")),
    pos("Điện thoại:0523456789", ("0523456789", "phone")),
    pos("di động 0703 456 789, cơ quan", ("0703 456 789", "phone")),
    pos("đầu số mới 0951 234 567", ("0951 234 567", "phone")),
    pos("ĐT 0355 123 456, email nguyenvanb@example.com",
        ("0355 123 456", "phone"), ("nguyenvanb@example.com", "email")),
    pos("0912 345 678 0987 654 321", ("0912 345 678", "phone"), ("0987 654 321", "phone")),
    pos("0912 345 678, 0987.654.321", ("0912 345 678", "phone"), ("0987.654.321", "phone")),
    pos("MST: 0100109106 - ĐT: 0912345678", ("0912345678", "phone")),
    pos("0912 34 56 78", ("0912 34 56 78", "phone")),                       # 4-2-2-2: nhóm đầu ≥ 3 chữ số
    pos("84912345678", ("84912345678", "phone")),                           # 84… liền, bỏ dấu cộng
    pos("+84 (0) 912 345 678", ("+84 (0) 912 345 678", "phone")),
    pos("0912345678,0987654321,0903123456,0812345678", ("0912345678", "phone"), ("0987654321", "phone"),
        ("0903123456", "phone"), ("0812345678", "phone")),                  # phẩy không cách, một lượt
    # Ngắt dòng, tab, cách hẹp là phân cách nhóm (lớp chữ PDF, OCR giữ xuống dòng: chunks.py, trích yếu F4.1)
    pos("điện thoại 0912 345\n678, cảm ơn", ("0912 345\n678", "phone")),
    pos("0912\r\n345 678", ("0912\r\n345 678", "phone")),
    pos("0912\t345\t678", ("0912\t345\t678", "phone")),
    pos("0912\N{THIN SPACE}345\N{THIN SPACE}678", ("0912\N{THIN SPACE}345\N{THIN SPACE}678", "phone")),
    pos("ĐT: 0912\N{NARROW NO-BREAK SPACE}345\N{NARROW NO-BREAK SPACE}678",
        ("0912\N{NARROW NO-BREAK SPACE}345\N{NARROW NO-BREAK SPACE}678", "phone")),
    pos("Số CCCD của tôi là 001205\n000017.", ("001205\n000017", "cccd")),
    pos("+84 912\n345 678", ("+84 912\n345 678", "phone")),
    pos("Căn cước công dân số 098 205\n000 017", ("098 205\n000 017", "cccd"), kw=True),
    pos("Số CMND: 212 345\n678", ("212 345\n678", "cmnd"), kw=True),
    # dán chữ vào dòng cuối thì lùi về dòng đầu (STK 6–19 số: dòng đầu vẫn đủ) — không dùng làm ca gốc op_glue
    pos("STK 0011 0041\n23456", ("0011 0041\n23456", "account"), kw=True, mutate=False),
    # sau từ khóa, trọn chuỗi vắt dòng sai độ dài thì lùi về cuối dòng: số thứ tự "2." của dòng sau không bị che
    pos("CMND số 123456789\n2. Địa chỉ thường trú", ("123456789", "cmnd"), kw=True, mutate=False),
    # "_" là ranh giới (tên tệp bị chặn vào nhật ký core.file.rejected)
    pos("don_0912345678.txt", ("0912345678", "phone"), mutate=False),      # op_tax: "don_MST" không là từ khóa
    pos("CCCD_001205000017.jpg", ("001205000017", "cccd")),
    pos("scan_001205000017_mat_truoc.jpg", ("001205000017", "cccd")),
    # số di động viết liền sau tiền tố điện thoại (#58): có dấu, không dấu, hoa thường, theo nhóm, sau dấu câu, đầu dòng
    pos("ĐT0912345678", ("0912345678", "phone")),
    pos("SĐT0912345678", ("0912345678", "phone")),
    pos("SDT0912345678", ("0912345678", "phone")),
    pos("sđt0912 345 678", ("0912 345 678", "phone")),
    pos("DĐ0987.654.321", ("0987.654.321", "phone")),
    pos("Tel0912345678", ("0912345678", "phone")),
    pos("PHONE0951234567", ("0951234567", "phone")),
    pos("SĐT:0912345678", ("0912345678", "phone")),
    pos("(ĐT0912345678)", ("0912345678", "phone")),
    pos("Nguyễn Văn B\nSĐT0912345678.", ("0912345678", "phone")),
    pos("Liên hệ ĐT0912345678, email nguyenvanb@example.com",
        ("0912345678", "phone"), ("nguyenvanb@example.com", "email")),
    pos("ĐT0912345678 0987 654 321", ("0912345678", "phone"), ("0987 654 321", "phone")),
    # che lượt đầu gỡ điều kiện chặn của khớp bên cạnh: find lặp tới điểm bất động (fuzz tìm ra)
    pos("001205000017,0084nguyenvanb@example.com", ("001205000017", "cccd"), ("0084nguyenvanb@example.com", "email")),
    pos("091209120011+840912345678", ("091209120011", "cccd"), ("+840912345678", "phone")),
    # Email
    pos("nguyenvanb@example.com", ("nguyenvanb@example.com", "email")),
    pos("phong.dao-tao+cv@dhm.example.edu.vn", ("phong.dao-tao+cv@dhm.example.edu.vn", "email")),
    pos("Email: NguyenVanB@Example.COM.", ("NguyenVanB@Example.COM", "email")),
    pos("<nguyenvanb@example.com>", ("nguyenvanb@example.com", "email")),
    pos("mailto:nguyenvanb@example.com", ("nguyenvanb@example.com", "email")),
    pos("0912345678@example.com", ("0912345678@example.com", "email")),
    # Số tài khoản: chỉ khi có từ khóa
    pos("Số tài khoản: 0011 0041 23456", ("0011 0041 23456", "account"), kw=True),
    pos("STK 19034567890123", ("19034567890123", "account"), kw=True),
    pos("tài khoản ngân hàng số 1234 5678 9012", ("1234 5678 9012", "account"), kw=True),
    pos("SỐ TÀI KHOẢN 0011004123456", ("0011004123456", "account"), kw=True),
    pos("so tai khoan: 0011 0041 23456", ("0011 0041 23456", "account"), kw=True),
    pos("TK số: 123456789", ("123456789", "account"), kw=True),
    pos("số TK 0123456789012", ("0123456789012", "account"), kw=True),
    pos("Stk: 0912345678", ("0912345678", "account"), kw=True, mutate=False),     # từ khóa thắng cấu trúc
    # Đủ năm loại trong một câu
    pos(f"Ông A, CCCD {CCCD[0]}, ĐT {PHONES[0]}, email {EMAILS[0]}, STK {ACCOUNT}.",
        (CCCD[0], "cccd"), (PHONES[0], "phone"), (EMAILS[0], "email"), (ACCOUNT, "account")),
]

_rng = random.Random(44)
NEGATIVE = [
    # giấy tờ, ngày, tiền
    "Số: 131/ĐT-ĐHM", "Nghị định số 30/2020/NĐ-CP ngày 05 tháng 3 năm 2020", "05/3/2026", "05.03.2026", "2026-10-15",
    "200.000 đồng", "1.500.000.000 đồng", "3,2", "Điều 12 Khoản 3", "trang 12", "năm học 2026–2027",
    "02 bản sao, cấp ngày 05/3/2021",
    # định danh máy
    hashlib.sha256(b"moc-f44").hexdigest(),
    *(uuid.UUID(int=_rng.getrandbits(128), version=4).hex for _ in range(5)),
    "c300d5bb-1234-4abc-8def-001205000017", "C300D5BB-1234-4ABC-8DEF-079305000123",
    "00000000-0000-4000-8000-000000000001",
    "9f0c2d4e-5b6a-4c3d-8e9f-0912345678ab", "1792281602100", "1792281602100_assignment_suggestions",
    "172.18.0.5:8000", "3.18.0", "ABCD2345EF", "2026-10-15T09:41:22.123456+07:00", "2026-10-15 09:41:22",
    "/api/files/0912345678", "anchors/0000000001234",
    # số khác: tổng đài, bưu chính, mã số thuế, đầu số chưa cấp, sai độ dài, dính chữ, thiếu từ khóa
    "1900 1234", "1800.1234", "100000", "MST: 0900123456", "MST: 0312345678", "Mã số thuế 0100109106",
    "Mã số doanh nghiệp: 0912345678", "0301234567", "09123456789", "0912345678901",
    "0912345678x", "0912  345  678", "0,0912345678", "3.0912345678", "0912345678.25", "số 123456789",
    "1234567890123",
    # dính chữ (#58): tiền tố điện thoại chỉ đi với di động 10 số, tiền tố không dính chữ, chữ số, "/", "-" phía trước
    "HSĐT0912345678", "QĐ-ĐT0912345678", "12/ĐT0912345678", "Hotel0912345678", "ĐT0301234567", "ĐT09123456789",
    "ĐT0912345678x", "ĐT001205000017",
    "Tài khoản 0011 0041 23456", "tài khoản cá nhân", "CMND 12345678", "Số CCCD: 001205000017abc",
    "CCCD 001 205 000 017x",
    "000205000017", "001427000017", "001227000017",
    # dãy số nhỏ của bảng, lịch (pypdf tách ô bằng một dấu cách): nhóm đầu 2 chữ số không mở đầu một số
    "Tuần 01 02 03 04 05 06", "các ngày 07 08 09 10 11", "tiết 09 10 11 12 13", "điểm 09 10 11 12 13 14 15",
    "Lịch trực: 01 02 03 04 05 06 07 08 09 10 11 12", "điểm 08.09.10.11.12", "STT\n01\n02\n03\n04\n05\n06",
    "điểm thi 09 08 07 10 09 08", "phòng 08 12 15 20 22", "các tuần lẻ 01 03 05 07 09 11",
    # cột bảng tách mỗi ô một dòng (pypdf đọc theo cột): số cuối dòng ghép với số đầu dòng sau; dãy đếm không là số
    "năm 2024\n2025\n2026", "Trang 12\n2026", "Mã ngành\n7480201\n7340101", "STT\n001\n002\n003\n004",
    "mã học phần 0101 0102 0103",
    # phẩy: tiền, số thập phân (chỉ phẩy nối hai dãy ≥ 9 chữ số mới tách hai số)
    "1,234,567 đồng", "12,345,678,901", "0912345678,25", "3,0912345678",
    # email giả
    "@pytest.fixture", "user@localhost", "a@b.c", "ten%40example.com",
]


# ---- đột biến dữ liệu vào ---------------------------------------------------------------------------------------

def national(value: str) -> list[int | None]:
    """Vị trí (trong ``value``) của từng chữ số theo cách viết trong nước 0xxx…; None là số 0 ngầm sau +84."""
    for cc in CC:
        if value.startswith(cc):
            slots: list[int | None] = [i for i, c in enumerate(value) if c.isdigit() and i >= len(cc)]
            return slots if value[slots[0]] == "0" else [None, *slots]
    return [i for i, c in enumerate(value) if c.isdigit()]


def put(value: str, slot: int | None, digit: str) -> str:
    return value if slot is None else value[:slot] + digit + value[slot + 1:]


Base = tuple[str, str, str, str, bool]          # (trước, giá trị, sau, loại, có từ khóa)
Op = Callable[[Base], list[tuple[str, str, str, str | None]]]    # → [(trước, giá trị mới, sau, loại mong đợi)]


def bases() -> list[Base]:
    out = []
    for text, items, kw, mutate in POSITIVE:
        if mutate and len(items) == 1:
            value, kind = items[0]
            start = text.index(value)
            out.append((text[:start], value, text[start + len(value):], kind, kw))
    return out


def op_change_digit(b: Base) -> list:
    """Đổi 1 chữ số ở phần ngẫu nhiên (CCCD vị trí 7–12, SĐT 5–10, CMND/STK 3 số cuối) → vẫn che, cùng loại."""
    before, value, after, kind, _ = b
    if kind == "email":
        return []
    slots = national(value)
    pick = {"cccd": slots[6:12], "phone": slots[4:10]}.get(kind, slots[-3:])
    rng = random.Random(f"{value}{kind}")
    out = []
    for slot in rng.sample(pick, 2):
        digit = str((int(value[slot]) + rng.randint(1, 9)) % 10)
        out.append((before, put(value, slot, digit), after, kind))
    return out


def op_province(b: Base) -> list:
    """Mã tỉnh → 000, 003, 097, 099: không che; có từ khóa định danh thì vẫn che (đường từ khóa)."""
    before, value, after, kind, kw = b
    if kind != "cccd":
        return []
    slots = national(value)
    out = []
    for code in ("000", "003", "097", "099"):
        new = value
        for slot, digit in zip(slots[:3], code):
            new = put(new, slot, digit)
        out.append((before, new, after, "cccd" if kw else None))
    return out


def op_century(b: Base) -> list:
    """Chữ số thế kỷ → 4…9, hoặc thế kỷ 21 (2/3) với năm sinh 27–99 khi năm nay là 2026: không che (trừ có từ khóa)."""
    before, value, after, kind, kw = b
    if kind != "cccd":
        return []
    slots = national(value)
    variants = [{3: c} for c in "456789"]
    variants += [{3: "2", 4: "2", 5: "7"}, {3: "3", 4: "5", 5: "0"}, {3: "2", 4: "9", 5: "9"}]    # 2027, 2050, 2099
    out = []
    for change in variants:
        new = value
        for i, digit in change.items():
            new = put(new, slots[i], digit)
        out.append((before, new, after, "cccd" if kw else None))
    return out


def op_length(b: Base) -> list:
    """Thêm chữ số 9 (vào cuối; SĐT: sau chữ số thứ 3, để máy bàn 11 số không thành 12 số dạng CCCD), hoặc bỏ chữ số
    cuối: không che."""
    before, value, after, kind, _ = b
    if kind not in ("cccd", "phone", "cmnd"):
        return []
    slots = national(value)
    at, last = (slots[2] if kind == "phone" else slots[-1]), slots[-1]
    return [(before, value[:at + 1] + "9" + value[at + 1:], after, None),
            (before, value[:last] + value[last + 1:], after, None)]


def op_prefix(b: Base) -> list:
    """Đầu số di động 10 số → 030, 050, 071, 080 (chưa cấp): không che; → 095 (cấp 07/2026): vẫn che."""
    before, value, after, kind, _ = b
    slots = national(value)
    if kind != "phone" or len(slots) != 10:
        return []                     # chỉ di động 10 số (máy bàn 02x, di động cũ 01x đều 11 số)
    out = []
    for code, want in (("030", None), ("050", None), ("071", None), ("080", None), ("095", "phone")):
        new = value
        for slot, digit in zip(slots[:3], code):
            new = put(new, slot, digit)
        out.append((before, new, after, want))
    return out


def op_separator(b: Base) -> list:
    """Đổi phân cách (cách ↔ chấm ↔ gạch): vẫn che. Phân cách → hai dấu cách: không che (thành nhiều ứng viên)."""
    before, value, after, kind, _ = b
    if kind == "email" or not any(c in SEPARATORS for c in value):
        return []
    out = [(before, "".join(new if c in SEPARATORS else c for c in value), after, kind)
           for new in " .-" if any(c in SEPARATORS and c != new for c in value)]
    out.append((before, "".join("  " if c in SEPARATORS else c for c in value), after, None))
    return out


def op_glue(b: Base) -> list:
    """Dán chữ liền trước / liền sau chữ số: không che. Không dán trước "+84", "(024)": phần số sau vẫn đứng riêng."""
    before, value, after, kind, _ = b
    if kind == "email":
        return []
    return [(before, value + "x", after, None)] + ([(before, "x" + value, after, None)] if value[0].isdigit() else [])


def op_wrap(b: Base) -> list:
    """Bọc ngoặc, thêm "." hay "," ngay sau: vẫn che (biên không đổi)."""
    before, value, after, kind, _ = b
    return [(before + "(", value, ")" + after, kind), (before, value, "." + after, kind),
            (before, value, "," + after, kind)]


def op_tax(b: Base) -> list:
    """Thêm "MST: " ngay trước SĐT 10 số viết trong nước: không che (cổng mã số thuế). Bỏ qua số dính sau tiền tố
    ("ĐTMST: …" không có từ khóa đứng riêng)."""
    before, value, after, kind, _ = b
    if kind != "phone" or len(national(value)) != 10 or value.startswith(CC) or before[-1:].isalpha():
        return []
    return [(before + "MST: ", value, after, None)]


def op_email(b: Base) -> list:
    """Email: bỏ @, đuôi miền 1 ký tự (miền hai nhãn) → không che; thêm +tag, viết hoa → vẫn che."""
    before, value, after, kind, _ = b
    if kind != "email":
        return []
    local, domain = value.split("@")
    out = [(before, value.replace("@", ""), after, None),
           (before, f"{local}+tag@{domain}", after, "email"),
           (before, value.upper(), after, "email")]
    if domain.count(".") == 1:
        out.append((before, f"{local}@{domain.split('.')[0]}.c", after, None))
    return out


def op_keyword(b: Base) -> list:
    """STK / CMND: bỏ từ khóa, hoặc từ khóa cách xa hơn 20 ký tự: không che."""
    before, value, after, kind, kw = b
    if kind not in ("cmnd", "account") or not kw:
        return []
    return [("Số hồ sơ: ", value, after, None), (before + " " * 21, value, after, None),
            (before.rstrip() + " của người làm đơn là ", value, after, None)]


OPERATORS: tuple[Op, ...] = (op_change_digit, op_province, op_century, op_length, op_prefix, op_separator, op_glue,
                             op_wrap, op_tax, op_email, op_keyword)


def mutated_inputs() -> list[tuple[str, str, Want]]:
    """(tên toán tử, chuỗi mới, kỳ vọng) cho mọi ca gốc."""
    out = []
    for b in bases():
        for op in OPERATORS:
            for before, value, after, want in op(b):
                spans = [(len(before), len(before) + len(value), want)] if want else []
                out.append((op.__name__, before + value + after, spans))
    return out


# ---- các phần kiểm (hàm thuần) ----------------------------------------------------------------------------------

def found(mod, text: str) -> Want:
    return [(s.start, s.end, s.kind) for s in mod.find(text, year=YEAR)]


def check_positive(mod) -> list[str]:
    out = []
    for text, items, _, _ in POSITIVE:
        want, got = spans_of(text, items), found(mod, text)
        if got != want:
            out.append(f"dương tính {text!r}: {got} ≠ {want}")
    return out


def check_negative(mod) -> list[str]:
    return [f"âm tính {text!r}: {got}" for text in NEGATIVE if (got := found(mod, text))]


def check_mutated_inputs(mod) -> list[str]:
    return [f"đột biến dữ liệu {name} {text!r}: {got} ≠ {want}"
            for name, text, want in mutated_inputs() if (got := found(mod, text)) != want]


def check_constants(mod) -> list[str]:
    """Hai danh mục liệt kê từng phần tử: đổi danh mục thì phải sửa cả test (kèm ngày, nguồn trong chú thích)."""
    provinces = set("""001 002 004 006 008 010 011 012 014 015 017 019 020 022 024 025 026 027 030 031 033 034 035
        036 037 038 040 042 044 045 046 048 049 051 052 054 056 058 060 062 064 066 067 068 070 072 074 075 077 079
        080 082 083 084 086 087 089 091 092 093 094 095 096""".split())
    mobile = set("""032 033 034 035 036 037 038 039 052 055 056 058 059 070 076 077 078 079 081 082 083 084 085 086
        087 088 089 090 091 092 093 094 095 096 097 098 099""".split())
    out = []
    if mod.PROVINCES != provinces or len(provinces) != 63:
        out.append(f"PROVINCES lệch: {sorted(mod.PROVINCES ^ provinces)}")
    if mod.MOBILE_PREFIXES != mobile:
        out.append(f"MOBILE_PREFIXES lệch: {sorted(mod.MOBILE_PREFIXES ^ mobile)}")
    for label in (*(f"[{v}]" for v in mod.LABELS.values()), *(f"[{v}-12]" for v in mod.LABELS.values())):
        if not mod.LABEL_RE.fullmatch(label) or any(c in label for c in '<>"\\'):
            out.append(f"nhãn {label!r} không hợp lệ")
    if mod.LABEL_RE.search("[1] [12] [SĐT-1234]"):
        out.append("LABEL_RE nhận nhầm dấu trích dẫn")
    return out


# Fuzz tìm ra (60 000 chuỗi ghép giá trị và ký tự dính): một lượt che chưa đủ, vì che xong một khớp mới gỡ điều kiện
# chặn ("chữ số + phẩy", "dính chữ") của khớp bên cạnh — find phải lặp tới điểm bất động
STICKY = (
    "001205000017,0084nguyenvanb@example.com", "091209120011+840912345678", "0912 345 678,079305000123.(024)",
    "STK-3000 0000 079305000123_", "0912 345 678,0987654321 0987654321@",
    "001205000017:0912 345 678_091209120011,0912 345 678\r\nCMND:",
)


def check_idempotent(mod) -> list[str]:
    texts = [text for text, *_ in POSITIVE] + NEGATIVE + [text for _, text, _ in mutated_inputs()] + list(STICKY)
    out = [f"che lại bản đã che còn khớp: {text!r}" for text in texts
           if mod.mask(mod.mask(text, year=YEAR).text, year=YEAR).spans]
    for text in STICKY:            # bản che đánh số qua lối ra (nhãn trơn) cũng không còn gì để che
        if mod.mask(mod.Masker(year=YEAR).mask(text).text, year=YEAR).spans:
            out.append(f"lối ra còn che thêm bản Masker: {text!r}")
    return out


WORDS = ("văn", "bản", "đề", "nghị", "cấp", "bằng", "liên", "hệ", "ông", "bà", "tại", "trường", "phòng", "đào", "tạo",
         "ngày", "tháng", "gửi", "kèm", "theo")
VALUES = (*CCCD, *PHONES, *EMAILS, "0912345678", "079 305 000 123")


def random_text(rng: random.Random) -> str:
    """Từ và giá trị xen nhau, hai giá trị không đứng liền nhau (mỗi giá trị là một chuỗi số riêng)."""
    tokens: list[str] = []
    for _ in range(rng.randint(3, 25)):
        value = rng.random() < 0.35 and not (tokens and tokens[-1] in VALUES)
        tokens.append(rng.choice(VALUES) if value else rng.choice(WORDS))
    return " ".join(tokens)


def check_window(mod) -> list[str]:
    out = []
    rng = random.Random(44)
    for _ in range(200):          # 200 ca: (lo, hi) bất kỳ, miễn không rơi giữa khoảng che
        text = random_text(rng)
        m = mod.mask(text, year=YEAR)
        free = [p for p in range(len(text) + 1) if not any(s.start < p < s.end for s in m.spans)]
        lo, hi = sorted(rng.choice(free) for _ in range(2))
        got, want = m.text[slice(*m.window((lo, hi)))], mod.mask(text[lo:hi], year=YEAR).text
        if got != want:
            out.append(f"window {text!r} [{lo}:{hi}]: {got!r} ≠ {want!r}")
    # lo, hi rơi giữa số: lo về đầu nhãn, hi về cuối nhãn — cửa sổ không bao giờ cắt đôi một con số
    text = f"Liên hệ {PHONES[0]} hoặc {EMAILS[0]} trong giờ hành chính"
    m = mod.mask(text, year=YEAR)
    phone, email = text.index(PHONES[0]), text.index(EMAILS[0])
    for (lo, hi), want in (((phone + 3, phone + 7), "[SĐT]"), ((phone + 5, email + 4), "[SĐT] hoặc [EMAIL]"),
                           ((0, phone + 1), "Liên hệ [SĐT]"), ((email + 2, len(text)), "[EMAIL] trong giờ hành chính"),
                           ((phone, phone + len(PHONES[0])), "[SĐT]")):
        if (got := m.text[slice(*m.window((lo, hi)))]) != want:
            out.append(f"window giữa số [{lo}:{hi}]: {got!r} ≠ {want!r}")
    # nhãn đánh số dài hơn nhãn trơn: vẫn về đúng đầu / cuối nhãn
    numbered = mod.Masker(year=YEAR).mask(text)
    if (got := numbered.text[slice(*numbered.window((phone + 4, phone + 4)))]) != "[SĐT-1]":
        out.append(f"window Masker giữa số: {got!r}")
    return out


def check_masker(mod) -> list[str]:
    out = []
    masker = mod.Masker(year=YEAR)
    q = masker.mask("Số điện thoại 0912 345 678 là của ai?")
    p = masker.mask("Liên hệ 0912345678 hoặc +84 912 345 678 hoặc 84912345678, số khác 0987 654 321; "
                    f"email A@Example.com, a@example.com; CCCD {CCCD[1]}.")
    want_q = "Số điện thoại [SĐT-1] là của ai?"
    want_p = "Liên hệ [SĐT-1] hoặc [SĐT-1] hoặc [SĐT-1], số khác [SĐT-2]; email [EMAIL-1], [EMAIL-1]; CCCD [CCCD-1]."
    if (q.text, p.text) != (want_q, want_p):
        out.append(f"Masker: {q.text!r} / {p.text!r}")
    if masker.total != 8:
        out.append(f"Masker.total = {masker.total} ≠ 8")
    if p.counts() != {"cccd": 1, "phone": 4, "email": 2}:
        out.append(f"Masked.counts() = {p.counts()}")
    if masker.mask(p.text).spans:
        out.append("Masker che lại bản đã che")
    other = mod.Masker(year=YEAR).mask("0987 654 321 rồi 0912 345 678")
    if other.text != "[SĐT-1] rồi [SĐT-2]":
        out.append(f"Masker mới không đánh số lại từ 1: {other.text!r}")
    return out


@contextlib.contextmanager
def restored_loggers(*names: str) -> Iterator[None]:
    """Giữ nguyên trạng thái logger dùng chung (uvicorn.*) sau phần kiểm — bản đột biến không để lại bộ lọc."""
    saved = []
    for name in names:
        lg = logging.getLogger(name)
        saved.append((lg, lg.filters[:], lg.handlers[:], lg.level, lg.propagate,
                      [(h, h.filters[:]) for h in lg.handlers]))
    try:
        yield
    finally:
        for lg, filters, handlers, level, propagate, handler_filters in saved:
            lg.filters[:], lg.handlers[:], lg.propagate = filters, handlers, propagate
            lg.setLevel(level)
            for handler, hf in handler_filters:
                handler.filters[:] = hf


def _capture(logger: logging.Logger, formatter: logging.Formatter) -> io.StringIO:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return stream


def _stack_line(log: logging.Logger) -> None:
    log.info("ngăn xếp 0912 345 678", stack_info=True)      # dòng mã này nằm trong stack_info


def check_logging(mod) -> list[str]:
    from uvicorn.logging import AccessFormatter, DefaultFormatter

    out = []
    name = "test_pii.dich_vu"
    with restored_loggers(name, "uvicorn", "uvicorn.error", "uvicorn.access"):
        for lg in map(logging.getLogger, (name, "uvicorn", "uvicorn.error", "uvicorn.access")):
            lg.handlers.clear()     # bỏ cả bộ lọc thật mà create_app (test khác) đã gắn: chỉ kiểm bản ``mod``
            lg.filters.clear()
        log = logging.getLogger(name)
        stream = _capture(log, logging.Formatter("%(message)s"))
        access = _capture(logging.getLogger("uvicorn.access"),
                          AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False))
        error = _capture(logging.getLogger("uvicorn.error"), DefaultFormatter("%(message)s", use_colors=True))
        mod.install_log_redaction(log)
        mod.install_log_redaction(log)
        for where in (log, *log.handlers, logging.getLogger("uvicorn.error"), logging.getLogger("uvicorn.access"),
                      *logging.getLogger("uvicorn.access").handlers):
            if (n := sum(isinstance(f, mod.PiiFilter) for f in where.filters)) != 1:
                out.append(f"install_log_redaction hai lần: {n} bộ lọc ở {where!r}")
        if not all(f.access for f in logging.getLogger("uvicorn.access").filters if isinstance(f, mod.PiiFilter)):
            out.append("uvicorn.access không dùng PiiFilter(access=True)")

        values = {"cccd": CCCD[0], "phone": PHONES[0], "email": EMAILS[0], "account": f"STK {ACCOUNT}"}
        for ensure_ascii in (False, True):
            log.info(json.dumps({"event": "thu", **values}, ensure_ascii=ensure_ascii))
        log.info("%s gọi %s", "Ông A", PHONES[2])
        log.info({"so": "0912345678"})
        try:
            raise ValueError(f"CCCD {CCCD[0]} sai")
        except ValueError:
            log.exception(json.dumps({"event": "office.action.failed"}))
        _stack_line(log)
        # formatter tự dựng traceback từ exc_info (như vài thư viện nhật ký JSON): bộ lọc phải bỏ exc_info sau khi che
        rebuild = logging.StreamHandler(stream)
        rebuild.setFormatter(type("Rebuild", (logging.Formatter,), {"format": lambda self, r: "rebuild " + (
            self.formatException(r.exc_info) if r.exc_info else "không còn exc_info")})())
        log.addHandler(rebuild)
        try:
            raise ValueError(f"CCCD {CCCD[1]} sai")
        except ValueError:
            log.exception("lỗi")
        log.removeHandler(rebuild)
        log.info("%d", "không phải số")                       # ghép tham số hỏng → dòng redaction_failed
        lines = stream.getvalue()
        for line in lines.splitlines()[:2]:
            try:
                got = json.loads(line)
            except ValueError:
                out.append(f"JSON hỏng sau khi che: {line!r}")
                continue
            if got != {"event": "thu", "cccd": "[CCCD]", "phone": "[SĐT]", "email": "[EMAIL]", "account": "STK [STK]"}:
                out.append(f"JSON che sai: {got}")
        for needle in ("Ông A gọi [SĐT]", "{'so': '[SĐT]'}", "ValueError: CCCD [CCCD] sai", "ngăn xếp [SĐT]",
                       "rebuild không còn exc_info",
                       '{"event": "core.log.redaction_failed", "logger": "test_pii.dich_vu"}'):
            if needle not in lines:
                out.append(f"nhật ký thiếu {needle!r}")
        if "Traceback" not in lines or "_stack_line" not in lines:
            out.append("nhật ký mất traceback / stack")
        for value in (*CCCD, *PHONES, *EMAILS, ACCOUNT, "0912345678", "912 345 678"):
            if value in lines:
                out.append(f"nhật ký lọt {value!r}")

        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "172.18.0.5:51234", "GET",
                                                 "/api/search?q=0912345678", "1.1", 200)
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "172.18.0.5:51234", "GET",
                                                 "/api/files/don-0912345678.txt?q=0912%20345%20678", "1.1", 404)
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "172.18.0.5:51234", "GET",
                                                 "/healthz", "1.1", 200)
        want = ['172.18.0.5:51234 - "GET /api/search?… HTTP/1.1" 200 OK',
                '172.18.0.5:51234 - "GET /api/files/don-[SĐT].txt?… HTTP/1.1" 404 Not Found',
                '172.18.0.5:51234 - "GET /healthz HTTP/1.1" 200 OK']
        if access.getvalue().splitlines() != want:
            out.append(f"nhật ký truy cập: {access.getvalue().splitlines()}")
        # in màu thì uvicorn lấy color_message thay cho msg — phải ra bản đã che, không phải mẫu "%s"
        logging.getLogger("uvicorn.error").warning("Lỗi khi gửi tới %s", EMAILS[1],
                                                   extra={"color_message": "Lỗi khi gửi tới %s"})
        if error.getvalue() != "Lỗi khi gửi tới [EMAIL]\n":
            out.append(f"uvicorn.error: {error.getvalue()!r}")

        # bộ lọc idempotent: chạy lại trên bản ghi đã che không đổi gì
        record = logging.LogRecord(name, logging.INFO, __file__, 1, "ĐT %s", (PHONES[0],), None)
        flt = mod.PiiFilter()
        flt.filter(record)
        first = record.getMessage()
        if not flt.filter(record) or record.getMessage() != first or first != "ĐT [SĐT]":
            out.append(f"PiiFilter không idempotent: {first!r} → {record.getMessage()!r}")
    return out


CHECKS = (check_positive, check_negative, check_mutated_inputs, check_constants, check_idempotent, check_window,
          check_masker, check_logging)


def failures(mod) -> list[str]:
    """Mọi ca hỏng của module ``mod`` (bản thật phải là [])."""
    return [failure for check in CHECKS for failure in check(mod)]


# ---- test pytest ------------------------------------------------------------------------------------------------

def test_tables_are_large_enough():
    assert sum(len(items) for _, items, _, _ in POSITIVE) >= 40
    assert len(NEGATIVE) >= 40
    cases = mutated_inputs()
    assert len(cases) >= 150, len(cases)
    assert {name for name, _, _ in cases} == {op.__name__ for op in OPERATORS}      # toán tử nào cũng có ca
    assert any(want for _, _, want in cases) and any(not want for _, _, want in cases)


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_check(check):
    problems = check(pii)
    assert not problems, "\n".join(problems)


def test_find_is_sorted_and_non_overlapping():
    text = " ".join(text for text, *_ in POSITIVE)
    spans = pii.find(text, year=YEAR)
    assert len(spans) > len(POSITIVE)
    assert all(a.end <= b.start for a, b in zip(spans, spans[1:]))


def test_mask_plain_labels_and_counts():
    m = pii.mask(f"CCCD {CCCD[0]}, ĐT {PHONES[3]}, {EMAILS[0]}", year=YEAR)
    assert m.text == "CCCD [CCCD], ĐT [SĐT], [EMAIL]"
    assert m.labels == ("[CCCD]", "[SĐT]", "[EMAIL]")
    assert m.counts() == {"cccd": 1, "phone": 1, "email": 1}
    assert pii.mask_text("không có gì để che") == "không có gì để che"


def test_year_defaults_to_this_year():
    born_next_year = f"0012{(time.localtime().tm_year + 1) % 100:02d}000017"
    assert pii.find(born_next_year) == []
    assert pii.find(born_next_year, year=time.localtime().tm_year + 1) != []


def test_masked_text_is_valid_json_string():
    payload = json.dumps({"q": f"liên hệ {PHONES[0]} hoặc {EMAILS[0]}"}, ensure_ascii=False)
    assert json.loads(pii.mask_text(payload)) == {"q": "liên hệ [SĐT] hoặc [EMAIL]"}


def _cli(*args: str, stdin: str) -> subprocess.CompletedProcess:
    src = os.path.dirname(os.path.dirname(pii.__file__))
    env = {**os.environ, "PYTHONPATH": src, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "svc_files.pii", *args], input=stdin.encode(), capture_output=True,
                          env=env, timeout=60)


def test_cli_count_never_prints_values():
    text = f"Đơn đề nghị (giả lập): CCCD {CCCD[0]}, ĐT {PHONES[0]} / {PHONES[3]}, email {EMAILS[0]}, STK {ACCOUNT}\n"
    done = _cli("count", stdin=text)
    assert done.returncode == 0, done.stderr
    out = done.stdout.decode()
    assert json.loads(out) == {"chars": len(text), "total": 5,
                               "spans": {"cccd": 1, "phone": 2, "email": 1, "account": 1}}
    for value in (*CCCD, *PHONES, *EMAILS, ACCOUNT, "@"):
        assert value not in out


def test_cli_mask_prints_labels():
    done = _cli("mask", stdin=f"Liên hệ {PHONES[0]}, email {EMAILS[0]}.\n")
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode() == "Liên hệ [SĐT], email [EMAIL].\n"


@pytest.mark.parametrize("args", [(), ("che",), ("mask", "count")])
def test_cli_bad_usage_exits_2(args):
    done = _cli(*args, stdin="0912345678")
    assert done.returncode == 2
    assert done.stdout == b""
    assert "mask|count" in done.stderr.decode()


def _best_ms(text: str, runs: int = 3) -> float:
    best = float("inf")
    for _ in range(runs):
        started = time.perf_counter()
        pii.mask(text, year=YEAR)
        best = min(best, (time.perf_counter() - started) * 1000)
    return best


@pytest.mark.parametrize("text", ["12 " * 33000, "1 " * 50000, "a@" * 50000, "x@a." * 25000, "9" * 100000,
                                  "0912345678 " * 9000, "CCCD " + "1 " * 50000, "1\n" * 50000,
                                  "CCCD " + "1\n" * 50000, "001205000017,0084a@example.com " * 3200,
                                  "SĐT0912345678 " * 7000, "ĐT1 " * 25000],
                         ids=["12-cach", "1-cach", "a@", "x@a.", "9", "nhieu-sdt", "tu-khoa-dai", "1-xuong-dong",
                              "tu-khoa-xuong-dong", "hai-luot", "tien-to-sdt", "tien-to-ngan"])
def test_pathological_inputs_stay_fast(text):
    # ngân sách 500 ms (đo trên máy dev: ≤ 150 ms); lấy lần nhanh nhất trong 3 lần để không chập chờn
    assert _best_ms(text) <= 500


def test_ordinary_text_is_fast():
    rng = random.Random(44)
    words = [*WORDS, "131/ĐT-ĐHM", "05/3/2026", "200.000", "đồng", "Điều", "12", "khoản", *VALUES]
    text = " ".join(rng.choice(words) for _ in range(5000))[:20000]
    assert len(text) == 20000
    assert _best_ms(text) <= 50
