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

"""Vòng nền đọc lớp chữ của tệp PDF (F2.7) rồi ghi vào core.file_texts.

Không đọc lúc tải lên: lúc đó tệp chưa gắn vào văn bản nào, chưa biết văn bản có hạn chế không (tệp của văn bản
hạn chế không được đọc chữ — hasura.PENDING_TEXTS). Đọc ở vòng nền còn bù được các tệp tải lên trước khi có F2.7.
Vòng đồng bộ tìm kiếm (search.py) thấy chữ mới ghi thì đẩy lại văn bản sang Meilisearch.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any, Protocol

from .hasura import HasuraError
from .pdftext import PdfText, extract_pdf
from .storage import ObjectMissing, StorageError

log = logging.getLogger("svc_files")

MAX_TRIES = 5      # số lượt liền kho không đọc được một tệp (mà tệp vẫn có) trước khi ghi "failed"


class _Hasura(Protocol):
    async def pending_texts(self, limit: int) -> list[dict[str, Any]]: ...
    async def save_text(self, *, file_id: str, tenant_id: str, status: str, pages: int | None, content: str,
                        note: str | None) -> None: ...


class _Store(Protocol):
    def read_stream(self, key: str, chunk_size: int = ...) -> Iterator[bytes]: ...


class TextExtractor:
    def __init__(self, hasura: _Hasura, store: _Store, *, interval_s: float = 10.0, max_bytes: int,
                 batch: int = 5, timeout_s: float | None = None) -> None:
        self.hasura = hasura
        self.store = store
        self.interval_s = interval_s
        self.max_bytes = max_bytes
        self.batch = batch
        self.timeout_s = timeout_s
        self._tries: dict[str, int] = {}     # id tệp → số lượt kho không đọc được (lỗi có thể tự hết)

    def _read(self, key: str) -> bytes:
        return b"".join(self.store.read_stream(key))

    async def _extract(self, row: dict[str, Any]) -> PdfText:
        if int(row["size_bytes"]) > self.max_bytes:
            return PdfText("failed", None, "", "too large")
        data = await asyncio.to_thread(self._read, row["object_key"])
        if self.timeout_s is None:
            return await extract_pdf(data)
        return await extract_pdf(data, timeout_s=self.timeout_s)

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
            except StorageError as exc:
                # kho chưa lên hoặc đứt kết nối: lượt sau thử lại; lỗi mãi ở một tệp thì thôi, ghi "failed"
                tries = self._tries[row["id"]] = self._tries.get(row["id"], 0) + 1
                log.warning(json.dumps({"event": "core.file.text_unread", "file_id": row["id"], "tries": tries,
                                        "error": str(exc)}, ensure_ascii=False))
                if tries < MAX_TRIES:
                    continue
                text = PdfText("failed", None, "", "unreadable")
            self._tries.pop(row["id"], None)
            await self._save(row, text)
            log.info(json.dumps({"event": "core.file.text_extracted", "file_id": row["id"], "status": text.status,
                                 "pages": text.pages, "chars": len(text.content), "note": text.note}))
            done += 1
        return done

    async def _save(self, row: dict[str, Any], text: PdfText) -> None:
        try:
            await self.hasura.save_text(file_id=row["id"], tenant_id=row["tenant_id"], status=text.status,
                                        pages=text.pages, content=text.content, note=text.note)
        except HasuraError as exc:
            # CSDL không nhận kết quả này: ghi "failed" trơn để hàng đợi đi tiếp. Hasura tắt thì lần ghi này cũng
            # lỗi và lỗi đi lên vòng ngoài — tệp chưa có dòng kết quả, lượt sau đọc lại.
            log.warning(json.dumps({"event": "core.file.text_rejected", "file_id": row["id"], "error": str(exc)},
                                   ensure_ascii=False))
            await self.hasura.save_text(file_id=row["id"], tenant_id=row["tenant_id"], status="failed",
                                        pages=None, content="", note="not saved")

    async def run(self) -> None:
        while True:
            try:
                done = await self.run_once()
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "core.file.text_failed", "error": str(exc)}, ensure_ascii=False))
                done = 0
            # còn tồn (vd tệp tải lên trước khi có F2.7) thì đọc tiếp ngay, hết thì nghỉ
            await asyncio.sleep(0 if done == self.batch else self.interval_s)
