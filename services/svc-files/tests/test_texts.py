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


"""Vòng nền đọc lớp chữ của PDF (F2.7): đọc từ kho, ghi core.file_texts, kho lỗi thì để lượt sau."""

from __future__ import annotations

import asyncio
import io
import uuid

import pytest

from conftest import TENANT_A, pages_pdf, text_pdf
from svc_files.hasura import HasuraError
from svc_files.texts import MAX_TRIES, TextExtractor


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
