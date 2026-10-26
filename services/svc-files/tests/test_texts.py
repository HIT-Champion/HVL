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


"""Vòng nền đọc lớp chữ của PDF (F2.7): đọc từ kho, ghi core.file_texts, kho lỗi thì để lượt sau."""

from __future__ import annotations

import asyncio
import io
import uuid
from functools import partial
from pathlib import Path

import pytest
from PIL import Image

from conftest import SAMPLE_TSV, TENANT_A, fake_tesseract, pages_pdf, text_pdf
from svc_files.docread.ocr import OcrResult, run_ocr
from svc_files.hasura import HasuraError
from svc_files.pdftext import MAX_CHARS, _starts_ok
from svc_files.texts import MAX_TRIES, OCR_RETRY, TextExtractor, from_ocr


def pending(hasura, store, data: bytes, *, size: int | None = None) -> str:
    file_id = str(uuid.uuid4())
    key = f"tenant/{TENANT_A}/2026/10/{file_id}"
    store.put(key, io.BytesIO(data), size=len(data), content_type="application/pdf", sha256_hex="00" * 32)
    hasura.pdfs.append({"id": file_id, "tenant_id": str(TENANT_A), "object_key": key,
                        "size_bytes": size if size is not None else len(data)})
    return file_id


def extractor(hasura, store, **kw) -> TextExtractor:
    return TextExtractor(hasura, store, max_bytes=1024 * 1024, **kw)


def test_reads_pending_pdfs_and_saves_the_text(hasura, store):
    ok = pending(hasura, store, text_pdf("Ke hoach tuyen sinh 2027"))
    scan = pending(hasura, store, text_pdf(pages=1))
    broken = pending(hasura, store, b"%PDF-1.4 hong")
    assert asyncio.run(extractor(hasura, store).run_once()) == 3
    assert hasura.texts[ok] == {"tenant_id": str(TENANT_A), "status": "ok", "pages": 1,
                                "content": "Ke hoach tuyen sinh 2027", "note": None, "page_starts": [0]}
    assert (hasura.texts[scan]["status"], hasura.texts[scan]["content"]) == ("empty", "")
    assert hasura.texts[scan]["page_starts"] is None and hasura.texts[broken]["page_starts"] is None
    assert hasura.texts[broken]["status"] == "failed" and hasura.texts[broken]["note"]
    assert asyncio.run(extractor(hasura, store).run_once()) == 0          # mỗi tệp chỉ đọc một lần


def test_reads_at_most_one_batch_per_round(hasura, store):
    for i in range(3):
        pending(hasura, store, text_pdf(f"Van ban {i}"))
    assert asyncio.run(extractor(hasura, store, batch=2).run_once()) == 2
    assert asyncio.run(extractor(hasura, store, batch=2).run_once()) == 1


def test_too_large_files_are_not_read(hasura, store):
    big = pending(hasura, store, text_pdf("To qua"), size=2 * 1024 * 1024)
    asyncio.run(extractor(hasura, store).run_once())
    assert hasura.texts[big] == {"tenant_id": str(TENANT_A), "status": "failed", "pages": None, "content": "",
                                 "note": "too large", "page_starts": None}


def test_storage_errors_leave_the_file_for_a_later_round_but_not_forever(hasura, store):
    stuck = pending(hasura, store, text_pdf("Chua doc duoc"))
    after = pending(hasura, store, text_pdf("Tep sau van doc"))
    store.unreadable.add(hasura.pdfs[0]["object_key"])
    worker = extractor(hasura, store)
    assert asyncio.run(worker.run_once()) == 1                       # tệp lỗi không chặn tệp sau
    assert stuck not in hasura.texts and hasura.texts[after]["status"] == "ok"
    for _ in range(MAX_TRIES - 2):
        assert asyncio.run(worker.run_once()) == 0 and stuck not in hasura.texts
    assert asyncio.run(worker.run_once()) == 1                       # lỗi mãi ở một tệp: thôi, ghi "failed"
    assert (hasura.texts[stuck]["status"], hasura.texts[stuck]["note"]) == ("failed", "unreadable")


def test_a_file_missing_from_storage_is_failed_at_once(hasura, store):
    lost = pending(hasura, store, text_pdf("Mat tep"))
    store.objects.clear()
    assert asyncio.run(extractor(hasura, store).run_once()) == 1
    assert (hasura.texts[lost]["status"], hasura.texts[lost]["note"]) == ("failed", "missing")


def test_a_result_the_database_rejects_does_not_block_the_queue(hasura, store):
    # vd tệp dựng có ý đồ khai số trang không vừa cột int: lần sau PENDING_TEXTS vẫn trả nó đầu tiên
    bad = pending(hasura, store, text_pdf("Tep doc"))
    good = pending(hasura, store, text_pdf("Tep tot"))
    hasura.rejected.add(bad)
    assert asyncio.run(extractor(hasura, store).run_once()) == 2
    assert hasura.texts[bad] == {"tenant_id": str(TENANT_A), "status": "failed", "pages": None, "content": "",
                                 "note": "not saved", "page_starts": None}
    assert hasura.texts[good]["status"] == "ok"


def test_hasura_down_saves_nothing_and_raises_to_the_loop(hasura, store):
    pending(hasura, store, text_pdf("Cho Hasura"))
    worker = extractor(hasura, store)
    original = hasura.save_text

    async def down(**kw):
        raise HasuraError("Hasura tắt")

    hasura.save_text = down
    with pytest.raises(HasuraError):
        asyncio.run(worker.run_once())
    hasura.save_text = original
    assert hasura.texts == {}


# --- chữ theo trang (F4.2) --------------------------------------------------------------------------------------


def test_page_boundaries_are_saved_with_the_text(hasura, store):
    doc = pending(hasura, store, pages_pdf(("Dieu 1. Pham vi ap dung",), (), ("Dieu 2. Han nop ho so 12/12/2026",)))
    asyncio.run(extractor(hasura, store).run_once())
    saved = hasura.texts[doc]
    assert saved["pages"] == 3 and saved["page_starts"] == [0, 24, 24]      # trang 2 trống: cùng vị trí trang 3
    assert saved["content"][saved["page_starts"][2]:].startswith("Dieu 2.")


# --- bản scan: nhận dạng chữ (#253) -------------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "ocr"
# TSV Tesseract trang 1 của hai bản scan trong seed/van-ban-den (make van-ban-mau)
NOTICE = (FIXTURES / "13-thong-bao-ban-scan.tsv").read_text(encoding="utf-8")
DECISION = (FIXTURES / "22-quyet-dinh-scan-3-trang.tsv").read_text(encoding="utf-8")


class FakeOcr:
    """Thay ``run_ocr`` của vòng nền: trả kết quả định sẵn; đếm số lần gọi và số lần chạy cùng lúc nhiều nhất."""

    def __init__(self, result: OcrResult) -> None:
        self.result = result
        self.calls: list[bytes] = []
        self.running = self.most = 0

    async def __call__(self, data: bytes) -> OcrResult:
        self.calls.append(data)
        self.running += 1
        self.most = max(self.most, self.running)
        await asyncio.sleep(0.01)
        self.running -= 1
        return self.result


def scan_pdf(*pages: bool) -> bytes:
    """PDF scan: trang True là một ảnh trắng (Pillow ghi PDF), trang False không có ảnh nào."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject

    out = io.BytesIO()
    images = [Image.new("L", (1240, 1754), 255) for _ in pages]
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=150)
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(out.getvalue())))
    for i, has_image in enumerate(pages):
        if not has_image:
            writer.pages[i][NameObject("/Resources")] = DictionaryObject()
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_a_scan_is_recognized_and_saved_page_by_page(hasura, store, log_records):
    scan = pending(hasura, store, text_pdf(pages=3))
    ocr = FakeOcr(OcrResult("ok", 3, (DECISION, "", NOTICE)))
    assert asyncio.run(extractor(hasura, store, ocr=ocr).run_once()) == 1
    saved = hasura.texts[scan]
    assert (saved["status"], saved["pages"], saved["note"]) == ("ok", 3, "ocr 3/3")
    starts, content = saved["page_starts"], saved["content"]
    # trang 2 không có ảnh: giữ chỗ, cùng vị trí trang 3 — trích dẫn "tr. 3" vẫn đúng trang
    assert len(starts) == 3 and starts[0] == 0 and starts[1] == starts[2]
    assert "Số: 1875/QĐ-UBND" in content[:starts[1]] and "36/TTr-SKHCN" in content[:starts[1]]
    assert content[starts[2]:].startswith("TRƯỜNG ĐẠI HỌC MẪU") and "Số: 128/TB-ĐHM" in content[starts[2]:]
    assert _starts_ok(starts, "ok", len(content))
    (event,) = [r for r in log_records if r["event"] == "core.file.text_ocr"]
    assert (event["file_id"], event["status"], event["pages_read"], event["note"]) == (scan, "ok", 3, "ocr 3/3")
    assert event["chars"] == len(content) and "UBND" not in str(event)       # nhật ký không mang chữ của tệp


def test_only_files_without_a_text_layer_are_recognized(hasura, store):
    layer = pending(hasura, store, text_pdf("Ke hoach tuyen sinh 2027"))
    broken = pending(hasura, store, b"%PDF-1.4 hong")
    scan_bytes = text_pdf(pages=1)
    scan = pending(hasura, store, scan_bytes)
    ocr = FakeOcr(OcrResult("ok", 1, (NOTICE,)))
    assert asyncio.run(extractor(hasura, store, ocr=ocr).run_once()) == 3
    assert ocr.calls == [scan_bytes]
    assert (hasura.texts[layer]["status"], hasura.texts[layer]["note"]) == ("ok", None)
    assert hasura.texts[broken]["status"] == "failed"
    assert (hasura.texts[scan]["status"], hasura.texts[scan]["note"]) == ("ok", "ocr 1/1")


def test_scans_are_recognized_one_at_a_time(hasura, store):
    for _ in range(4):
        pending(hasura, store, text_pdf(pages=1))
    ocr = FakeOcr(OcrResult("ok", 1, (NOTICE,)))
    worker = extractor(hasura, store, ocr=ocr, batch=5)
    assert asyncio.run(worker.run_once()) == 4
    assert len(ocr.calls) == 4 and ocr.most == 1


@pytest.mark.parametrize(("result", "note"), [
    (OcrResult("failed", 2, (), "no_text"), "ocr no_text"),
    (OcrResult("failed", 2, (), "too_many_pixels"), "ocr too_many_pixels"),
    (OcrResult("ok", 2, (SAMPLE_TSV.split("\n", 2)[0], "")), "ocr 2/2 blank"),      # chỉ dòng tiêu đề: không có từ
])
def test_a_scan_without_recognized_text_stays_empty_with_the_reason(hasura, store, result, note):
    scan = pending(hasura, store, text_pdf(pages=2))
    ocr = FakeOcr(result)
    worker = extractor(hasura, store, ocr=ocr)
    assert asyncio.run(worker.run_once()) == 1
    assert hasura.texts[scan] == {"tenant_id": str(TENANT_A), "status": "empty", "pages": 2, "content": "",
                                  "note": note, "page_starts": None}
    assert asyncio.run(worker.run_once()) == 0 and len(ocr.calls) == 1      # không đọc lại, không vào vòng MAX_TRIES


@pytest.mark.parametrize("note", sorted(OCR_RETRY))
def test_ocr_failing_on_the_machine_is_retried_but_not_forever(hasura, store, note):
    # máy bận quá giờ, thiếu RAM, thiếu tesseract: không phải lỗi của bản scan, lượt sau OCR lại như lỗi kho
    scan = pending(hasura, store, text_pdf(pages=2))
    after = pending(hasura, store, text_pdf("Tep sau van doc"))
    ocr = FakeOcr(OcrResult("failed", None, (), note))
    worker = extractor(hasura, store, ocr=ocr)
    assert asyncio.run(worker.run_once()) == 1                       # bản scan chờ không chặn tệp sau
    assert scan not in hasura.texts and hasura.texts[after]["status"] == "ok"
    for _ in range(MAX_TRIES - 2):
        assert asyncio.run(worker.run_once()) == 0 and scan not in hasura.texts
    assert asyncio.run(worker.run_once()) == 1 and len(ocr.calls) == MAX_TRIES
    assert hasura.texts[scan] == {"tenant_id": str(TENANT_A), "status": "empty", "pages": 2, "content": "",
                                  "note": f"ocr {note}", "page_starts": None}
    assert asyncio.run(worker.run_once()) == 0 and len(ocr.calls) == MAX_TRIES


def test_a_scan_is_recognized_once_the_machine_is_free_again(hasura, store):
    scan = pending(hasura, store, text_pdf(pages=1))
    ocr = FakeOcr(OcrResult("failed", 1, (), "timeout"))
    worker = extractor(hasura, store, ocr=ocr)
    assert asyncio.run(worker.run_once()) == 0 and scan not in hasura.texts
    ocr.result = OcrResult("ok", 1, (NOTICE,))
    assert asyncio.run(worker.run_once()) == 1
    assert (hasura.texts[scan]["status"], hasura.texts[scan]["note"]) == ("ok", "ocr 1/1")


def test_without_ocr_a_scan_stays_empty_as_before(hasura, store):
    scan = pending(hasura, store, text_pdf(pages=1))
    asyncio.run(extractor(hasura, store).run_once())
    assert (hasura.texts[scan]["status"], hasura.texts[scan]["note"]) == ("empty", None)


def test_recognized_text_fits_the_table():
    page = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            + "\n".join(f"5\t1\t1\t1\t{i}\t1\t10\t{10 * i}\t50\t9\t95\t{'chu' * 30}" for i in range(400)))
    text = from_ocr(OcrResult("ok", 9, (page, page, page)), 9)
    assert text.status == "ok" and len(text.content) == MAX_CHARS and text.note == "ocr 3/9"
    assert text.page_starts == [0, 36_400] and _starts_ok(text.page_starts, "ok", len(text.content))
    assert from_ocr(OcrResult("ok", None, (page,)), None).note == "ocr 1/?"


def test_the_real_ocr_path_keeps_page_positions(hasura, store, tmp_path):
    # run_ocr thật (tiến trình con, ảnh nhúng của PDF) với tesseract giả: trang 2 không có ảnh vẫn giữ chỗ
    ocr = partial(run_ocr, kind="pdf", binary=str(fake_tesseract(tmp_path)), max_pages=3, timeout_s=30)
    scan = pending(hasura, store, scan_pdf(True, False, True))
    asyncio.run(extractor(hasura, store, ocr=ocr).run_once())
    saved = hasura.texts[scan]
    assert (saved["status"], saved["pages"], saved["note"]) == ("ok", 3, "ocr 3/3")
    first = saved["content"][:saved["page_starts"][1]].rstrip("\n")
    assert saved["page_starts"][1] == saved["page_starts"][2] and saved["content"][saved["page_starts"][2]:] == first
