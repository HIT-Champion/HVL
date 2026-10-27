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

"""Vòng nền đọc lớp chữ của tệp PDF (F2.7) rồi ghi vào core.file_texts.

Không đọc lúc tải lên: lúc đó tệp chưa gắn vào văn bản nào, chưa biết văn bản có hạn chế không (tệp của văn bản
hạn chế không được đọc chữ — hasura.PENDING_TEXTS). Đọc ở vòng nền còn bù được các tệp tải lên trước khi có F2.7.
Vòng đồng bộ tìm kiếm (search.py) thấy chữ mới ghi thì đẩy lại văn bản sang Meilisearch.

F4.2: ghi kèm ``page_starts`` (vị trí đầu từng trang trong nội dung) để trợ lý hỏi đáp cắt đoạn theo trang
(assist/index.py); hàng đợi có thêm bản phát hành văn bản đi (role ``issued``).

#253: PDF không có lớp chữ (bản scan) thì nhận dạng chữ bằng Tesseract (``ocr.run_ocr``: tiến trình con có
giới hạn bộ nhớ, CPU, điểm ảnh) vài trang đầu, rồi ghi ``ok`` như lớp chữ, ``note`` = "ocr <số trang đã đọc>/<số
trang>". Vòng nền đọc lần lượt từng tệp nên mỗi lúc chỉ một tệp OCR. Không ra chữ vì tệp (không có ảnh, ảnh trắng…)
thì giữ ``empty`` kèm lý do: bản scan mờ không phải tệp hỏng, và tệp đã có dòng kết quả thì không bị đọc lại. Hỏng vì
máy (quá giờ, thiếu bộ nhớ, thiếu tesseract — ``OCR_RETRY``) thì thử lại tới MAX_TRIES lượt rồi mới ghi ``empty``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Any, Protocol

from .hasura import HasuraError
from .layout import tsv_lines
from .ocr import OcrResult
from .pdftext import MAX_CHARS, PdfText, clean, extract_pdf, join_pages
from .storage import ObjectMissing, StorageError

log = logging.getLogger("svc_files")

MAX_TRIES = 5      # số lượt liền một tệp gặp lỗi có thể tự hết (kho, OCR phía máy) trước khi ghi kết quả cuối
# OCR hỏng vì máy (bận quá giờ, thiếu RAM — SIGKILL của bộ diệt OOM —, thiếu tesseract hay gói ngôn ngữ): thử lại như
# lỗi kho. Lý do còn lại là của tệp (không có ảnh, ảnh trắng, quá nhiều điểm ảnh, mật khẩu, hỏng): ghi `empty` ngay.
OCR_RETRY = {"timeout", "memory", "no_tesseract", "engine_failed"}

Ocr = Callable[[bytes], Awaitable[OcrResult]]


class OcrRetry(Exception):
    """OCR hỏng vì máy: tệp ở lại hàng đợi; hết MAX_TRIES lượt thì ghi ``text`` (``empty`` kèm lý do)."""

    def __init__(self, text: PdfText) -> None:
        super().__init__(text.note)
        self.text = text


def from_ocr(got: OcrResult, pages: int | None) -> PdfText:
    """Kết quả OCR của một PDF không có lớp chữ → dòng core.file_texts. ``pages``: số trang pypdf đếm được."""
    if got.status != "ok":
        return PdfText("empty", pages, "", f"ocr {got.note or 'failed'}")
    # mỗi trang một TSV (trang không có ảnh: chuỗi rỗng, vẫn giữ chỗ) → các dòng trên → dưới, trái → phải
    full, starts = join_pages([clean("\n".join(line.text for line in tsv_lines([tsv]))) for tsv in got.tsv])
    content = full[:MAX_CHARS].rstrip()
    total = pages if pages is not None else got.pages
    read = f"ocr {len(got.tsv)}/{total if total is not None else '?'}"
    if not content:
        return PdfText("empty", pages, "", f"{read} blank")
    return PdfText("ok", pages, content, read, [s for s in starts if s <= len(content)])


class _Hasura(Protocol):
    async def pending_texts(self, limit: int) -> list[dict[str, Any]]: ...
    async def save_text(self, *, file_id: str, tenant_id: str, status: str, pages: int | None, content: str,
                        note: str | None, page_starts: list[int] | None) -> None: ...


class _Store(Protocol):
    def read_stream(self, key: str, chunk_size: int = ...) -> Iterator[bytes]: ...


class TextExtractor:
    def __init__(self, hasura: _Hasura, store: _Store, *, interval_s: float = 10.0, max_bytes: int,
                 batch: int = 5, timeout_s: float | None = None, ocr: Ocr | None = None) -> None:
        self.hasura = hasura
        self.store = store
        self.interval_s = interval_s
        self.max_bytes = max_bytes
        self.batch = batch
        self.timeout_s = timeout_s
        self.ocr = ocr                       # None: bản scan giữ `empty` (MOC_TEXT_OCR_PAGES=0)
        self._tries: dict[str, int] = {}     # id tệp → số lượt kho không đọc được (lỗi có thể tự hết)

    def _read(self, key: str) -> bytes:
        return b"".join(self.store.read_stream(key))

    async def _extract(self, row: dict[str, Any]) -> PdfText:
        if int(row["size_bytes"]) > self.max_bytes:
            return PdfText("failed", None, "", "too large")
        data = await asyncio.to_thread(self._read, row["object_key"])
        if self.timeout_s is None:
            text = await extract_pdf(data)
        else:
            text = await extract_pdf(data, timeout_s=self.timeout_s)
        if text.status != "empty" or self.ocr is None:
            return text
        started = time.monotonic()
        got = await self.ocr(data)
        text = from_ocr(got, text.pages)
        # chỉ số đếm được, không ghi chữ nhận dạng: nhật ký đi ra kho log tập trung
        log.info(json.dumps({"event": "core.file.text_ocr", "file_id": row["id"], "status": text.status,
                             "pages_read": len(got.tsv), "chars": len(text.content), "note": text.note,
                             "seconds": round(time.monotonic() - started, 1)}))
        if got.status != "ok" and got.note in OCR_RETRY:
            raise OcrRetry(text)
        return text

    async def run_once(self) -> int:
        """Đọc một lượt tối đa `batch` tệp; trả về số tệp đã ghi kết quả.

        PENDING_TEXTS luôn trả tệp cũ nhất trước, nên tệp nào cũng phải đi tới một dòng kết quả, kể cả tệp
        dựng có ý đồ: nếu không, một tệp lỗi chặn việc đọc chữ của mọi thuê ước.
        """
        done = 0
        for row in await self.hasura.pending_texts(self.batch):
            try:
                text = await self._extract(row)
            except ObjectMissing:
                text = PdfText("failed", None, "", "missing")
            except (StorageError, OcrRetry) as exc:
                # kho chưa lên, đứt kết nối, OCR quá giờ lúc máy bận: lượt sau thử lại; lỗi mãi ở một tệp thì thôi,
                # ghi "failed" (kho) hay `empty` kèm lý do (OCR)
                tries = self._tries[row["id"]] = self._tries.get(row["id"], 0) + 1
                log.warning(json.dumps({"event": "core.file.text_unread", "file_id": row["id"], "tries": tries,
                                        "error": str(exc)}, ensure_ascii=False))
                if tries < MAX_TRIES:
                    continue
                text = exc.text if isinstance(exc, OcrRetry) else PdfText("failed", None, "", "unreadable")
            self._tries.pop(row["id"], None)
            await self._save(row, text)
            log.info(json.dumps({"event": "core.file.text_extracted", "file_id": row["id"], "status": text.status,
                                 "pages": text.pages, "chars": len(text.content), "note": text.note}))
            done += 1
        return done

    async def _save(self, row: dict[str, Any], text: PdfText) -> None:
        try:
            await self.hasura.save_text(file_id=row["id"], tenant_id=row["tenant_id"], status=text.status,
                                        pages=text.pages, content=text.content, note=text.note,
                                        page_starts=text.page_starts)
        except HasuraError as exc:
            # CSDL không nhận kết quả này: ghi "failed" trơn để hàng đợi đi tiếp. Hasura tắt thì lần ghi này cũng
            # lỗi và lỗi đi lên vòng ngoài — tệp chưa có dòng kết quả, lượt sau đọc lại.
            log.warning(json.dumps({"event": "core.file.text_rejected", "file_id": row["id"], "error": str(exc)},
                                   ensure_ascii=False))
            await self.hasura.save_text(file_id=row["id"], tenant_id=row["tenant_id"], status="failed",
                                        pages=None, content="", note="not saved", page_starts=None)

    async def run(self) -> None:
        while True:
            try:
                done = await self.run_once()
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "core.file.text_failed", "error": str(exc)}, ensure_ascii=False))
                done = 0
            # còn tồn (vd tệp tải lên trước khi có F2.7) thì đọc tiếp ngay, hết thì nghỉ
            await asyncio.sleep(0 if done == self.batch else self.interval_s)
