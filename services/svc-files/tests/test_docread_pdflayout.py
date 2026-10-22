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

"""Lớp chữ giữ bố cục của PDF (F4.1): cột, giới hạn trang, mật khẩu, tệp hỏng, tiến trình con có giới hạn."""

from __future__ import annotations

import asyncio
import io
import unicodedata

import pytest

from conftest import text_pdf
from svc_files.docread.pdflayout import PAGE_CHARS, PdfLayout, _parse, clean, extract, extract_layout


def pdf_with(stream: bytes) -> bytes:
    """PDF một trang A4, Helvetica, nội dung là luồng lệnh vẽ chữ cho trước."""
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[4 0 R]/Count 1>>",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 3 0 R>>>>/Contents 5 0 R>>",
            b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def two_columns() -> bytes:
    """Đầu công văn: cơ quan bên trái, quốc hiệu bên phải cùng một hàng."""
    return pdf_with(b"BT /F1 11 Tf 60 780 Td (UBND TINH MAU) Tj ET "
                    b"BT /F1 11 Tf 330 780 Td (CONG HOA XA HOI CHU NGHIA VIET NAM) Tj ET "
                    b"BT /F1 11 Tf 60 760 Td (So: 12/QD-UBND) Tj ET")


def locked(user_password: str) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf("Noi dung cong van mat"))))
    writer.encrypt(user_password=user_password, owner_password="chu-so-huu", algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_layout_keeps_the_gap_between_columns():
    got = extract(two_columns())
    assert got.status == "ok" and got.pages == 1 and not got.truncated
    first, second = got.texts[0].split("\n")
    assert first.startswith("UBND TINH MAU   ") and first.rstrip().endswith("CONG HOA XA HOI CHU NGHIA VIET NAM")
    assert second == "So: 12/QD-UBND"


def test_only_the_first_pages_are_read_but_all_are_counted():
    got = extract(text_pdf("Trang co chu", pages=5), max_pages=2)
    assert got.texts == ("Trang co chu", "Trang co chu") and got.pages == 5


def test_a_scan_without_text_layer_is_empty():
    got = extract(text_pdf(pages=2))
    assert (got.status, got.pages) == ("empty", 2) and all(t == "" for t in got.texts)


def test_password_needed_is_failed_password_owner_password_only_is_read():
    assert extract(locked("bi-mat")) == PdfLayout("failed", None, (), "password")
    assert extract(locked("")).texts[0] == "Noi dung cong van mat"


def test_clean_keeps_spacing_but_drops_invisible_characters():
    nfd = "Quy" + "e" + chr(0x302) + chr(0x301) + "t"         # "Quyết" dạng tổ hợp
    raw = f"  A{chr(0)}B{chr(0x200B)}C\t   D\r\n{nfd}   {chr(0xFEFF)}\n"
    assert clean(raw) == "  ABC    D\n" + unicodedata.normalize("NFC", nfd)


def test_long_pages_are_cut_and_flagged(monkeypatch):
    import svc_files.docread.pdflayout as pdflayout

    monkeypatch.setattr(pdflayout, "PAGE_CHARS", 10)
    got = extract(text_pdf("Mot dong rat dai cua trang dau"))
    assert got.status == "ok" and got.texts == ("Mot dong r",) and got.truncated


@pytest.mark.parametrize("out", [
    b'{"status": "ok", "pages": 1, "texts": [""]}',                 # ok mà không có chữ
    b'{"status": "empty", "pages": 1, "texts": ["co chu"]}',
    b'{"status": "xong", "pages": 1, "texts": ["a"]}',
    b'{"status": "ok", "pages": -1, "texts": ["a"]}',
    b'{"status": "ok", "pages": true, "texts": ["a"]}',
    b'{"status": "ok", "pages": 1, "texts": ["a", "b", "c", "d"]}',  # nhiều trang hơn đã xin
    b'{"status": "ok", "pages": 1, "texts": [1]}',
    b'{"status": "ok", "pages": 1, "texts": "a"}',
    b'{"status": "failed", "pages": null, "texts": [], "note": "la"}',
    b'{"status": "failed", "pages": null, "texts": [], "note": []}',
    b'{"status": "ok", "pages": 1, "texts": ["a"], "truncated": "co"}',
    b'[]', b'khong phai json',
])
def test_child_output_is_checked(out):
    assert _parse(out, max_pages=3) == PdfLayout("failed", None, (), "corrupt")


def test_child_output_that_fits_is_kept():
    got = _parse(b'{"status": "ok", "pages": 2, "texts": ["a", ""], "note": null, "truncated": true}', 3)
    assert got == PdfLayout("ok", 2, ("a", ""), None, True)
    assert _parse(b'{"status": "failed", "pages": null, "texts": [], "note": "password"}', 3).note == "password"
    assert _parse(b'{"status": "ok", "pages": 1, "texts": ["' + b"a" * (PAGE_CHARS + 1) + b'"]}', 3).note == "corrupt"


# --- tiến trình con -----------------------------------------------------------------------------------------


def test_subprocess_returns_the_same_layout():
    assert asyncio.run(extract_layout(two_columns())) == extract(two_columns())


@pytest.mark.parametrize("data", [b"", b"khong phai PDF", b"%PDF-1.4\n" + b"\xff" * 1000],
                         ids=["rong", "khong-phai-pdf", "pdf-hong"])
def test_broken_files_never_raise(data):
    got = asyncio.run(extract_layout(data))
    assert got.status == "failed" and got.note == "corrupt" and got.texts == ()


def test_password_is_reported_from_the_subprocess():
    assert asyncio.run(extract_layout(locked("bi-mat"))).note == "password"


def test_a_slow_file_is_killed():
    got = asyncio.run(extract_layout(text_pdf("cham"), timeout_s=0.001))
    assert (got.status, got.note) == ("failed", "timeout")


def test_memory_limit_applies_to_the_child_process():
    got = asyncio.run(extract_layout(text_pdf("nhieu bo nho"), memory_mb=32))
    assert (got.status, got.note) == ("failed", "memory")
