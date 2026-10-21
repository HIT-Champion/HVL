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

"""Vòng nền của chỉ mục đoạn (F4.2): đồng bộ đoạn từ Hasura sang Meilisearch, rồi nhúng đoạn chưa có véc-tơ.

Một tác vụ, chạy tuần tự để ghi và nhúng không đua nhau:

- ``sync_once``: như ``search.Indexer`` của F2.7 — con trỏ thời gian lùi ``overlap`` để không sót giao dịch ghi xong
  muộn, lật trang theo id. Văn bản đổi khi: sửa văn bản (``updated_at``), một tệp vừa đọc chữ (``extracted_at``),
  giao việc mới (``assigned_at``). Mỗi văn bản: so đoạn muốn có (chunks.build) với đoạn đang có trong chỉ mục —
  thừa thì xóa (văn bản bật hạn chế, bị hủy, văn bản đi về dự thảo: xóa hết); mới hoặc đổi chữ thì thay cả đoạn và
  đặt lại véc-tơ null; chỉ đổi thuộc tính lọc thì cập nhật một phần, giữ véc-tơ. Mọi tác vụ Meilisearch của lượt
  phải thành công thì con trỏ mới tiến. Cấu hình embedder lỗi không chặn đồng bộ: chỉ mất tìm theo nghĩa, thử lại sau.
- ``embed_once``: lấy một lô đoạn chưa nhúng bằng mô hình hiện tại, gọi mô hình nhúng, ghi véc-tơ. Lô lỗi không do
  đường gọi thì nhúng lại từng đoạn; đoạn vẫn làm mô hình lỗi (HTTP lỗi, NaN…) được đánh dấu ``"<mô hình>#failed"``
  để không chặn mãi các đoạn sau — chỉ tìm được theo từ khóa, nhúng lại khi chữ đổi hoặc đổi mô hình.
- ``hold``: lượt hỏi đang chờ mô hình thì không mở lô nhúng nền mới.
- ``embed_pending`` / ``embed_failed``: số đoạn còn chờ nhúng / đã đánh dấu hỏng, đếm cuối mỗi vòng cho ``/readyz``.

Nhật ký không bao giờ có chữ văn bản: ``office.assist.indexed``, ``office.assist.embedded``,
``office.assist.embed_skipped`` (id các đoạn bị đánh dấu hỏng), ``office.assist.index_failed``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from ..search import _quoted
from .ai import TRANSIENT
from .chunks import build, embed_input, meta_update
from .meili import embedder_name

log = logging.getLogger("svc_files")

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
FETCH_PAGE = 1000          # đọc đoạn đang có của một văn bản theo trang (tối đa 300 đoạn + đoạn meta)
WAIT_S = 120.0             # đợi tác vụ Meilisearch (đổi embedder trên chỉ mục lớn có thể lâu)
EMBEDDER_RETRY_S = 60.0    # cấu hình embedder lỗi: thử lại sau chừng này giây (đồng bộ vẫn chạy mỗi vòng)
FAILED = "#failed"         # embed_model = "<mô hình>#failed": đoạn làm mô hình lỗi tất định (tên Ollama không có #)
CANARY = "Mộc"             # câu mẫu: mô hình nhúng được nó thì lỗi của một đoạn là do đoạn, không do mô hình


class Embedder(Protocol):
    """Phần của client mô hình (assist/ai.py, luồng C) mà vòng nền dùng; thêm ``embed_error`` nếu có (lý do lần lỗi
    gần nhất, xem ``ai.TRANSIENT``) — không có thì mọi lỗi coi như có thể do đoạn, câu mẫu quyết định."""

    @property
    def embed_model(self) -> str: ...

    @property
    def embed_available(self) -> bool: ...

    async def embed(self, texts: list[str], *, query: bool, timeout_s: float) -> list[list[float]] | None: ...


class _Source(Protocol):
    async def chunk_sources(self, since: datetime, limit: int, after: str) -> list[dict[str, Any]]: ...


class _Index(Protocol):
    async def ensure(self) -> int: ...
    async def ensure_embedder(self, embedder: str | None, dims: int) -> int | None: ...
    async def fetch(self, filter: Any, fields: list[str], limit: int,  # noqa: A002 — tên của API
                    offset: int = 0) -> list[dict[str, Any]]: ...
    async def count(self, filter: Any) -> int: ...  # noqa: A002 — tên của API
    async def replace(self, docs: list[dict[str, Any]]) -> int: ...
    async def update(self, docs: list[dict[str, Any]]) -> int: ...
    async def delete_ids(self, ids: list[str]) -> int: ...
    async def wait(self, task_uid: int, timeout_s: float = ...) -> None: ...


def changed_at(row: dict[str, Any]) -> datetime:
    """Lần đổi cuối của văn bản theo chỉ mục đoạn: sửa văn bản, tệp vừa đọc chữ, giao việc mới."""
    times = [row["updated_at"]]
    times += [text["extracted_at"] for f in row.get("files") or []
              if (text := (f.get("file") or {}).get("text")) and text.get("extracted_at")]
    times += [a["assigned_at"] for a in row.get("assignments") or [] if a.get("assigned_at")]
    return max(datetime.fromisoformat(t) for t in times)


class ChunkIndexer:
    def __init__(
        self,
        index: _Index,
        source: _Source,
        ai: Embedder | None = None,
        *,
        dims: int = 1024,
        batch: int = 8,
        interval_s: float = 5.0,
        overlap_s: float = 60.0,
        page: int = 20,               # văn bản mỗi lần đọc Hasura: mỗi văn bản kèm chữ mọi tệp (tới 50 000 ký tự/tệp)
        embed_budget_s: float = 20.0,  # mỗi vòng nhúng tối đa chừng này rồi quay lại đồng bộ
        embed_timeout_s: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.index = index
        self.source = source
        self.ai = ai
        self.model: str | None = ((ai.embed_model or "").strip() or None) if ai is not None else None
        self.embedder = embedder_name(self.model) if self.model else None
        self.dims = dims
        self.batch = batch
        self.interval_s = interval_s
        self.overlap = timedelta(seconds=overlap_s)
        self.page = page
        self.embed_budget_s = embed_budget_s
        self.embed_timeout_s = embed_timeout_s
        self._clock = clock
        self.cursor: datetime | None = None
        self.ensured = False          # đã áp cấu hình tìm từ khóa
        self.embedder_ready = False   # đã áp cấu hình embedder (thêm embedder hiện tại, bỏ embedder cũ)
        self.ready = False            # đã áp cấu hình và xong một lượt đồng bộ đầy đủ
        self.embed_pending: int | None = None   # đoạn chờ nhúng bằng mô hình hiện tại; None: không nhúng, chưa đếm
        self.embed_failed: int | None = None    # đoạn đã đánh dấu hỏng với mô hình hiện tại
        self._embedder_retry_at = 0.0
        self._hold_until = 0.0
        # id văn bản → (changed_at, dấu các đoạn) đã ghi trong cửa sổ overlap: không đọc lại chỉ mục khi không đổi
        self._pushed: dict[str, tuple[datetime, tuple[tuple[str, str, str], ...]]] = {}

    # --- nhường mô hình cho lượt hỏi ------------------------------------------------------------------------------

    def hold(self, seconds: float) -> None:
        """Không mở lô nhúng nền mới trong ``seconds`` giây tới (lượt hỏi đang cần mô hình)."""
        self._hold_until = max(self._hold_until, self._clock() + seconds)

    @property
    def held(self) -> bool:
        return self._clock() < self._hold_until

    # --- đồng bộ --------------------------------------------------------------------------------------------------

    def _fresh(self, chunk: dict[str, Any]) -> dict[str, Any]:
        """Đoạn mới hoặc đổi chữ: thay cả tài liệu, véc-tơ về null để vòng nhúng làm lại. Embedder chưa áp được thì
        không gửi ``_vectors``: tên embedder lạ có thể làm Meilisearch từ chối cả lô, hỏng luôn đường từ khóa."""
        doc = {**chunk, "embed_model": None}
        if self.embedder and self.embedder_ready:
            doc["_vectors"] = {self.embedder: None}
        return doc

    async def _have(self, document_id: str) -> dict[str, dict[str, Any]]:
        where = f"document_id = {_quoted(document_id)}"
        have: dict[str, dict[str, Any]] = {}
        offset = 0
        while True:
            rows = await self.index.fetch(where, ["id", "text_sha", "meta_sha"], FETCH_PAGE, offset)
            have.update((str(r["id"]), r) for r in rows)
            if len(rows) < FETCH_PAGE:
                return have
            offset += len(rows)

    async def _ensure_embedder(self) -> None:
        """Áp cấu hình embedder một lần; lỗi thì ghi nhật ký, thử lại sau ``EMBEDDER_RETRY_S``. Không chặn đồng bộ:
        đoạn vẫn vào chỉ mục, vẫn bị xóa đúng lúc, vẫn tìm được theo từ khóa — chỉ tìm theo nghĩa phải chờ."""
        if self.embedder_ready or self._clock() < self._embedder_retry_at:
            return
        try:
            task = await self.index.ensure_embedder(self.embedder, self.dims)
            if task is not None:
                await self.index.wait(task, WAIT_S)
        except Exception as exc:  # noqa: BLE001 — chỉ mất tìm theo nghĩa; đồng bộ đoạn vẫn phải chạy
            self._embedder_retry_at = self._clock() + EMBEDDER_RETRY_S
            log.warning(json.dumps({"event": "office.assist.index_failed", "stage": "embedder",
                                    "embedder": self.embedder, "error": str(exc)}, ensure_ascii=False))
            return
        self.embedder_ready = True

    async def sync_once(self) -> dict[str, int]:
        """Một lượt đồng bộ; trả về số văn bản có thay đổi, số đoạn đã ghi, số đoạn đã xóa."""
        if not self.ensured:
            await self.index.wait(await self.index.ensure(), WAIT_S)
            self.ensured = True
        await self._ensure_embedder()
        since = self.cursor - self.overlap if self.cursor else EPOCH
        newest = self.cursor
        after = str(uuid.UUID(int=0))
        counts = {"documents": 0, "chunks": 0, "deleted": 0}
        fresh: dict[str, tuple[datetime, tuple[tuple[str, str, str], ...]]] = {}
        tasks: list[int] = []
        while True:
            rows = await self.source.chunk_sources(since, self.page, after)
            replace: list[dict[str, Any]] = []
            update: list[dict[str, Any]] = []
            delete: list[str] = []
            for row in rows:
                at = changed_at(row)
                newest = at if newest is None or at > newest else newest
                want = build(row)
                mark = (at, tuple((c["id"], c["text_sha"], c["meta_sha"]) for c in want))
                if self._pushed.get(row["id"]) == mark:
                    continue
                have = await self._have(str(row["id"]))
                wanted = {c["id"] for c in want}
                gone = [cid for cid in have if cid not in wanted]
                new = [self._fresh(c) for c in want
                       if c["id"] not in have or have[c["id"]].get("text_sha") != c["text_sha"]]
                moved = [meta_update(c) for c in want if c["id"] in have
                         and have[c["id"]].get("text_sha") == c["text_sha"]
                         and have[c["id"]].get("meta_sha") != c["meta_sha"]]
                delete += gone
                replace += new
                update += moved
                if gone or new or moved:
                    counts["documents"] += 1
                fresh[row["id"]] = mark
            # gom theo trang; xóa trước để id thừa không bao giờ còn sau lần thay của chính văn bản đó
            if delete:
                tasks.append(await self.index.delete_ids(delete))
            if replace:
                tasks.append(await self.index.replace(replace))
            if update:
                tasks.append(await self.index.update(update))
            counts["deleted"] += len(delete)
            counts["chunks"] += len(replace) + len(update)
            if len(rows) < self.page:
                break
            after = rows[-1]["id"]
        # đợi mọi tác vụ của lượt trước khi nhúng: Meilisearch xử lý tuần tự nhưng một tác vụ lỗi không kéo tác vụ sau
        # lỗi theo — tác vụ nào lỗi thì cả lượt lỗi, con trỏ giữ nguyên, lượt sau đọc lại từ đầu cửa sổ
        for task in tasks:
            await self.index.wait(task, WAIT_S)
        self._pushed.update(fresh)        # chỉ ghi nhận sau khi Meilisearch đã xử lý xong
        self.cursor = newest
        if newest is not None:
            floor = newest - self.overlap
            self._pushed = {k: v for k, v in self._pushed.items() if v[0] >= floor}
        self.ready = True
        if counts["documents"]:
            log.info(json.dumps({"event": "office.assist.indexed", **counts}))
        return counts

    # --- nhúng ----------------------------------------------------------------------------------------------------

    @property
    def failed_mark(self) -> str:
        return f"{self.model}{FAILED}"

    def _pending(self) -> str:
        """Bộ lọc đoạn còn phải nhúng: chưa nhúng hoặc nhúng bằng mô hình khác, trừ đoạn đã hỏng với mô hình này."""
        return (f"embed_model IS NULL OR (embed_model != {_quoted(self.model or '')} "
                f"AND embed_model != {_quoted(self.failed_mark)})")

    def _transient(self) -> bool:
        """Lần nhúng vừa lỗi không do nội dung (``ai.TRANSIENT``): lượt sau thử lại, không đánh dấu đoạn nào."""
        return getattr(self.ai, "embed_error", None) in TRANSIENT

    async def embed_once(self) -> int:
        """Nhúng một lô đoạn chưa có véc-tơ của mô hình hiện tại; trả về số đoạn đã xử lý — nhúng được hoặc đánh dấu
        hỏng (0: không làm gì)."""
        ai = self.ai
        if (ai is None or not self.model or not self.embedder or not self.embedder_ready
                or not ai.embed_available or self.held):
            return 0
        started = self._clock()
        rows = await self.index.fetch(self._pending(), ["id", "kind", "text", "symbol", "summary"], self.batch)
        if not rows:
            return 0
        vectors = await ai.embed([embed_input(r) for r in rows], query=False, timeout_s=self.embed_timeout_s)
        if vectors is not None and len(vectors) == len(rows):
            done, bad = list(zip(rows, vectors, strict=True)), []
        elif self._transient():
            done, bad = [], []
        else:
            done, bad = await self._one_by_one(ai, rows)
        if not done and not bad:
            log.warning(json.dumps({"event": "office.assist.index_failed", "error": "embed_unavailable",
                                    "reason": getattr(ai, "embed_error", None), "chunks": len(rows),
                                    "model": self.model}))
            return 0
        task = await self.index.update(
            [{"id": r["id"], "embed_model": self.model,
              "_vectors": {self.embedder: {"embeddings": v, "regenerate": False}}} for r, v in done]
            + [{"id": r["id"], "embed_model": self.failed_mark} for r in bad])   # _vectors giữ null
        await self.index.wait(task, WAIT_S)
        if bad:
            log.warning(json.dumps({"event": "office.assist.embed_skipped", "model": self.model, "chunks": len(bad),
                                    "ids": [r["id"] for r in bad]}))
        if done:
            log.info(json.dumps({"event": "office.assist.embedded", "chunks": len(done), "model": self.model,
                                 "duration_ms": int((self._clock() - started) * 1000)}))
        return len(done) + len(bad)

    async def _one_by_one(self, ai: Embedder, rows: list[dict[str, Any]],
                          ) -> tuple[list[tuple[dict[str, Any], list[float]]], list[dict[str, Any]]]:
        """Lô lỗi không do đường gọi: nhúng lại từng đoạn để tách đoạn làm mô hình lỗi tất định khỏi phần còn lại.
        Đoạn chỉ bị đánh dấu hỏng khi mô hình vẫn nhúng được đoạn khác hoặc câu mẫu — lỗi chung (Ollama hết bộ nhớ,
        lỗi 500 với mọi đầu vào) không làm hỏng oan cả chỉ mục, và chỉ tốn thêm hai lần gọi mỗi vòng."""
        done: list[tuple[dict[str, Any], list[float]]] = []
        bad: list[dict[str, Any]] = []
        works = False                       # trong lượt này mô hình đã nhúng được đoạn khác hoặc câu mẫu
        for row in rows:
            if self.held:                   # lượt hỏi cần mô hình: dừng, lượt sau làm tiếp
                break
            got = await ai.embed([embed_input(row)], query=False, timeout_s=self.embed_timeout_s)
            if got is not None and len(got) == 1:
                done.append((row, got[0]))
                works = True
            elif self._transient():         # Ollama tắt, bận, quá giờ: phần còn lại để lượt sau
                break
            elif works or (not self.held and await self._model_works(ai)):
                works = True
                bad.append(row)
            else:                           # câu mẫu cũng lỗi: lỗi chung của mô hình, không do đoạn
                break
        return done, bad

    async def _model_works(self, ai: Embedder) -> bool:
        got = await ai.embed([CANARY], query=False, timeout_s=self.embed_timeout_s)
        return got is not None and len(got) == 1

    async def count(self) -> None:
        """Đếm đoạn còn chờ nhúng và đoạn hỏng của mô hình hiện tại (``/readyz``); không nhúng thì None."""
        if not self.model or not self.ensured:
            self.embed_pending = self.embed_failed = None
            return
        self.embed_pending = await self.index.count(self._pending())
        self.embed_failed = await self.index.count(f"embed_model = {_quoted(self.failed_mark)}")

    async def run(self) -> None:
        while True:
            try:
                await self.sync_once()
                deadline = self._clock() + self.embed_budget_s
                while self._clock() < deadline and await self.embed_once() == self.batch:
                    pass
                await self.count()
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "office.assist.index_failed", "error": str(exc)},
                                       ensure_ascii=False))
            await asyncio.sleep(self.interval_s)
