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


"""Đọc lớp chữ của PDF (F2.7): chữ tiếng Việt, bản scan, tệp khóa mật khẩu, tệp hỏng, tiến trình con có giới hạn."""

from __future__ import annotations

import asyncio
import io
import json
import unicodedata

import pytest

from conftest import pages_pdf, text_pdf
from svc_files.pdftext import MAX_COUNT, MAX_PAGES, PdfText, _parse, clean, extract, extract_pdf, join_pages


def test_reads_the_text_layer():
    got = extract(text_pdf("Cong van so 12/UBND-VP", "Ve viec (thu) ra soat"))
    assert got.status == "ok" and got.pages == 1 and got.note is None
    assert got.content == "Cong van so 12/UBND-VP\nVe viec (thu) ra soat"


def test_reads_vietnamese_from_a_real_pdf():
    try:
        from weasyprint import HTML
    except OSError:
        pytest.skip("máy này thiếu thư viện Pango của WeasyPrint (image svc-files có sẵn)")
    pdf = HTML(string="<p>Thông báo lịch đăng ký học phần học kỳ II năm học 2026–2027.</p>"
                      "<p>Đề nghị các khoa rà soát chứng chỉ ngoại ngữ B1 của sinh viên.</p>").write_pdf()
    got = extract(pdf)
    assert got.status == "ok"
    assert "rà soát chứng chỉ ngoại ngữ B1" in got.content
    assert got.content == unicodedata.normalize("NFC", got.content)


def test_a_scan_without_text_layer_is_empty():
    got = extract(text_pdf(pages=2))
    assert (got.status, got.pages, got.content) == ("empty", 2, "")


def test_only_the_first_pages_and_chars_are_kept():
    pdf = text_pdf("Trang nay co chu", pages=5)
    assert extract(pdf, max_pages=2).content == "Trang nay co chu\nTrang nay co chu"
    assert extract(pdf, max_pages=2).pages == 5
    assert extract(pdf, max_chars=10).content == "Trang nay"


def test_clean_removes_what_postgres_and_search_cannot_use():
    nfd = "Hu" + "o" + chr(0x31B) + "ng Y" + "e" + chr(0x302) + "n"
    raw = f"  A{chr(0)}B{chr(0x200B)}C  \t D{chr(0xAD)}E\n\n\n\n{nfd}{chr(0x2028)}cuoi{chr(0xFEFF)}  "
    assert clean(raw) == "ABC D" + "E\n\n" + unicodedata.normalize("NFC", nfd) + "\ncuoi"
    assert clean("Vi" + chr(0x200B) + "e" + chr(0x302) + "t") == "Vi" + chr(0xEA) + "t"   # dấu sau ký tự ẩn vẫn ghép


def test_password_protected_pdf_is_failed_but_owner_password_only_is_read():
    from pypdf import PdfReader, PdfWriter

    def locked(user: str) -> bytes:
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf("Noi dung mat"))))
        writer.encrypt(user_password=user, owner_password="chu-so-huu", algorithm="AES-128")
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    assert extract(locked("bi-mat")).status == "failed" and extract(locked("bi-mat")).note == "encrypted"
    assert extract(locked("")).content == "Noi dung mat"


def test_a_page_count_that_does_not_fit_the_column_is_not_kept():
    # PDF mã hóa (mật khẩu rỗng): pypdf trả nguyên /Count tệp tự khai — 3 tỉ không vừa cột int của CSDL
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf("Khai sai so trang"))))
    writer.encrypt(user_password="", owner_password="chu-so-huu", algorithm="AES-128")
    writer._root_object["/Pages"].get_object()[NameObject("/Count")] = NumberObject(3_000_000_000)
    out = io.BytesIO()
    writer.write(out)
    got = extract(out.getvalue())
    assert (got.status, got.pages, got.content) == ("ok", 1, "Khai sai so trang")   # số trang thật, không phải số khai


@pytest.mark.parametrize("out", [
    b'{"status": "ok", "pages": 1, "content": ""}',                # ok mà rỗng: vi phạm ràng buộc của bảng
    b'{"status": "empty", "pages": 1, "content": "co chu"}',
    b'{"status": "xong", "pages": 1, "content": "a"}',
    b'{"status": "ok", "pages": 3000000000, "content": "a"}',
    b'{"status": "ok", "pages": -1, "content": "a"}',
    b'{"status": "ok", "pages": true, "content": "a"}',
    b'{"status": "ok", "pages": 1, "content": "' + b"a" * 11 + b'"}',
    b'{"status": "failed", "pages": null, "content": "", "note": 5}',
    b'[]', b'khong phai json',
])
def test_child_output_is_checked_against_the_table(out):
    assert _parse(out, max_chars=10) == PdfText("failed", None, "", "bad output")


def test_child_output_that_fits_is_kept():
    assert _parse(b'{"status": "ok", "pages": 2, "content": "abc", "note": null}', 10) == PdfText("ok", 2, "abc")
    long_note = '{"status": "failed", "pages": null, "content": "", "note": "' + "x" * 300 + '"}'
    assert _parse(long_note.encode(), 10).note == "x" * 200


# --- ranh giới trang (F4.2) ----------------------------------------------------------------------------------


def test_page_starts_mark_where_each_page_begins():
    got = extract(pages_pdf(("Trang mot", "dong hai"), ("Trang hai",), ("Trang ba",)))
    assert got.content == "Trang mot\ndong hai\nTrang hai\nTrang ba"
    assert got.page_starts == [0, 19, 29]
    pages = [got.content[a:b].strip() for a, b in zip(got.page_starts, [*got.page_starts[1:], len(got.content)])]
    assert pages == ["Trang mot\ndong hai", "Trang hai", "Trang ba"]


def test_empty_pages_share_the_position_of_the_next_page():
    assert extract(pages_pdf((), ("Chi trang hai co chu",))).page_starts == [0, 0]
    assert extract(pages_pdf(("Mot",), (), (), ("Bon",))).page_starts == [0, 4, 4, 4]
    got = extract(pages_pdf(("Mot",), ()))
    assert (got.content, got.page_starts) == ("Mot", [0, 3])          # trang trống cuối: vị trí = độ dài


def test_pages_after_the_cut_are_dropped():
    got = extract(pages_pdf(("Trang nay co chu",), ("Trang hai",), ("Trang ba",)), max_chars=20)
    assert got.content == "Trang nay co chu\nTra" and got.page_starts == [0, 17]
    got = extract(pages_pdf(("Trang nay co chu",), ("Trang hai",)), max_chars=17)
    assert got.content == "Trang nay co chu" and got.page_starts == [0]   # chỉ còn dấu xuống dòng của trang 2


def test_page_starts_only_when_ok():
    assert extract(text_pdf(pages=2)).page_starts is None                  # bản scan
    assert extract(text_pdf("Mot dong", pages=2)).page_starts == [0, 9]


def test_join_pages_keeps_old_single_page_result():
    assert join_pages(["a\nb"]) == ("a\nb", [0])
    assert join_pages([]) == ("", [])
    assert join_pages(["", ""]) == ("", [0, 0])


@pytest.mark.parametrize("starts", [
    [], [1], [0, 5], [0, 2, 1], [0, "1"], [0, True], [0.0], "0", {"0": 0}, [0] * (MAX_PAGES + 1),
])
def test_child_page_starts_are_checked_against_the_table(starts):
    out = json.dumps({"status": "ok", "pages": 2, "content": "abcd", "page_starts": starts}).encode()
    assert _parse(out, max_chars=10) == PdfText("failed", None, "", "bad output")


def test_child_page_starts_only_with_ok():
    out = json.dumps({"status": "empty", "pages": 1, "content": "", "page_starts": [0]}).encode()
    assert _parse(out, max_chars=10) == PdfText("failed", None, "", "bad output")


def test_child_page_starts_that_fit_are_kept():
    out = json.dumps({"status": "ok", "pages": 3, "content": "abcd", "page_starts": [0, 2, 2]}).encode()
    assert _parse(out, max_chars=10) == PdfText("ok", 3, "abcd", None, [0, 2, 2])
    out = json.dumps({"status": "ok", "pages": 1, "content": "abcd", "page_starts": [0] * MAX_PAGES}).encode()
    assert _parse(out, max_chars=10).page_starts == [0] * MAX_PAGES


# --- tiến trình con -----------------------------------------------------------------------------------------


def test_subprocess_returns_the_same_text():
    got = asyncio.run(extract_pdf(text_pdf("Doc trong tien trinh con")))
    assert (got.status, got.pages, got.content) == ("ok", 1, "Doc trong tien trinh con")


def test_subprocess_returns_page_starts():
    got = asyncio.run(extract_pdf(pages_pdf(("Trang mot",), (), ("Trang ba",))))
    assert (got.status, got.content, got.page_starts) == ("ok", "Trang mot\nTrang ba", [0, 10, 10])


@pytest.mark.parametrize("data", [b"", b"khong phai PDF", b"%PDF-1.4\n" + b"\xff" * 1000])
def test_broken_files_never_raise(data):
    got = asyncio.run(extract_pdf(data))
    assert got.status == "failed" and got.content == "" and got.note


def test_a_slow_file_is_killed():
    got = asyncio.run(extract_pdf(text_pdf("cham"), timeout_s=0.001))
    assert (got.status, got.note) == ("failed", "timeout")


def test_memory_limit_applies_to_the_child_process():
    # 32 MB không đủ cho pypdf đọc tệp: tiến trình con hết bộ nhớ, svc-files vẫn chạy và ghi "failed"
    got = asyncio.run(extract_pdf(text_pdf("nhieu bo nho"), memory_mb=32))
    assert (got.status, got.note) == ("failed", "memory")
