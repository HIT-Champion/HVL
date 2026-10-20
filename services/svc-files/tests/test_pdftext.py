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


"""Đọc lớp chữ của PDF (F2.7): chữ tiếng Việt, bản scan, tệp khóa mật khẩu, tệp hỏng, tiến trình con có giới hạn."""

from __future__ import annotations

import asyncio
import io
import unicodedata

import pytest

from conftest import text_pdf
from svc_files.pdftext import MAX_COUNT, PdfText, _parse, clean, extract, extract_pdf


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


# --- tiến trình con -----------------------------------------------------------------------------------------


def test_subprocess_returns_the_same_text():
    got = asyncio.run(extract_pdf(text_pdf("Doc trong tien trinh con")))
    assert (got.status, got.pages, got.content) == ("ok", 1, "Doc trong tien trinh con")


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
