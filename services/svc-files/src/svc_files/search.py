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

"""Tìm kiếm văn bản (F1.7): Meilisearch xếp hạng, Hasura quyết ai được xem.

- Meilisearch chỉ trả về id (``displayedAttributes: ["id"]``), luôn lọc theo thuê ước lấy từ token.
- Kết quả lấy lại từ Hasura **bằng token người dùng**: văn bản họ không được đọc bị bỏ, và dữ liệu trả về
  là bản mới nhất trong CSDL chứ không phải bản sao trong chỉ mục. Quy tắc quyền chỉ nằm ở db/metadata.
- Không trả tổng số kết quả của Meilisearch: con số đó tính cả văn bản người dùng không được đọc.
- Đồng bộ: định kỳ đọc văn bản có ``updated_at`` mới qua Hasura rồi ghi đè vào Meilisearch theo id.
  Mỗi lượt đọc lùi lại một khoảng (overlap) để không sót giao dịch ghi xong muộn hơn thời điểm của nó.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx2

INDEX_SETTINGS: dict[str, Any] = {
    # `content` để dành cho lớp chữ của PDF (F2.7)
    "searchableAttributes": ["symbol", "summary", "issuer_name", "content"],
    "filterableAttributes": ["tenant_id", "direction", "status", "type_code", "urgency", "year"],
    "sortableAttributes": ["issued_ts"],
    "displayedAttributes": ["id"],
}

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

log = logging.getLogger("svc_files")


class SearchError(Exception):
    """Meilisearch không trả lời hoặc trả lỗi."""


class MeiliClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        index: str,
        *,
        timeout_s: float = 10.0,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.index = index
        self._http = httpx2.AsyncClient(
            base_url=base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._http.get("/health")
        except httpx2.HTTPError:
            return False
        return r.status_code == 200

    async def _request(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        try:
            r = await self._http.request(method, path, json=body)
        except httpx2.HTTPError as exc:
            raise SearchError(f"Không gọi được Meilisearch: {exc}") from exc
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            raise SearchError(f"Meilisearch trả {r.status_code}: {data.get('code')} {data.get('message')}")
        return data

    async def ensure_index(self) -> int:
        """Tạo chỉ mục nếu chưa có và áp cấu hình; trả về uid của tác vụ cấu hình."""
        try:
            await self._request("GET", f"/indexes/{self.index}")
        except SearchError:
            await self._request("POST", "/indexes", {"uid": self.index, "primaryKey": "id"})
        task = await self._request("PATCH", f"/indexes/{self.index}/settings", INDEX_SETTINGS)
        return int(task["taskUid"])

    async def upsert(self, docs: list[dict[str, Any]]) -> int:
        task = await self._request("POST", f"/indexes/{self.index}/documents?primaryKey=id", docs)
        return int(task["taskUid"])

    async def search(self, q: str, filters: list[str], limit: int, offset: int) -> list[str]:
        data = await self._request(
            "POST",
            f"/indexes/{self.index}/search",
            {"q": q, "filter": filters, "limit": limit, "offset": offset, "attributesToRetrieve": ["id"]},
        )
        return [str(hit["id"]) for hit in data.get("hits", [])]

    async def wait(self, task_uid: int, timeout_s: float = 30.0) -> None:
        """Đợi một tác vụ xử lý xong — dùng khi cần đọc ngay điều vừa ghi (test, lệnh dựng lại chỉ mục)."""
        deadline = time.monotonic() + timeout_s
        while True:
            task = await self._request("GET", f"/tasks/{task_uid}")
            if task["status"] == "succeeded":
                return
            if task["status"] in {"failed", "canceled"}:
                raise SearchError(f"Tác vụ {task_uid} lỗi: {task.get('error')}")
            if time.monotonic() > deadline:
                raise SearchError(f"Tác vụ {task_uid} chưa xong sau {timeout_s} giây")
            await asyncio.sleep(0.1)


# --- dữ liệu và bộ lọc ---------------------------------------------------------------------------


def to_index_doc(row: dict[str, Any]) -> dict[str, Any]:
    issued = date.fromisoformat(row["issued_on"]) if row.get("issued_on") else None
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "direction": row["direction"],
        "status": row["status"],
        "type_code": row["type_code"],
        "urgency": row["urgency"],
        "symbol": row.get("symbol"),
        "issuer_name": row.get("issuer_name"),
        "summary": row["summary"],
        "year": issued.year if issued else None,
        "issued_ts": int(datetime(issued.year, issued.month, issued.day, tzinfo=UTC).timestamp()) if issued else None,
    }


def _quoted(value: str) -> str:
    # Giá trị đã được kiểm ở tầng API; vẫn thoát ký tự để không ghép được thêm điều kiện vào bộ lọc.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True)
class SearchQuery:
    q: str
    direction: str | None = None
    status: str | None = None
    type_code: str | None = None
    urgency: str | None = None
    year: int | None = None


def build_filter(tenant_id: uuid.UUID, query: SearchQuery) -> list[str]:
    """Các điều kiện AND. Điều kiện thuê ước luôn đứng đầu và lấy từ token, không từ tham số."""
    parts = [f"tenant_id = {_quoted(str(tenant_id))}"]
    for name in ("direction", "status", "type_code", "urgency"):
        value = getattr(query, name)
        if value is not None:
            parts.append(f"{name} = {_quoted(value)}")
    if query.year is not None:
        parts.append(f"year = {int(query.year)}")
    return parts


# --- tìm kiếm ------------------------------------------------------------------------------------


class _Meili(Protocol):
    async def search(self, q: str, filters: list[str], limit: int, offset: int) -> list[str]: ...


class _Hasura(Protocol):
    async def visible_documents(self, token: str, ids: list[str]) -> dict[str, dict[str, Any]]: ...


async def search_documents(
    meili: _Meili,
    hasura: _Hasura,
    *,
    token: str,
    tenant_id: uuid.UUID,
    query: SearchQuery,
    limit: int,
    offset: int,
    max_rounds: int = 5,
) -> tuple[list[dict[str, Any]], int | None]:
    """Trả về (văn bản được đọc theo thứ tự xếp hạng, offset của trang sau hoặc None nếu hết).

    Lấy dư từ Meilisearch rồi lọc qua Hasura; người chỉ được đọc ít văn bản có thể cần vài vòng.
    """
    batch = min(max(limit * 2, 20), 100)
    filters = build_filter(tenant_id, query)
    hits: list[dict[str, Any]] = []
    cursor = offset
    for _ in range(max_rounds):
        ids = await meili.search(query.q, filters, batch, cursor)
        if not ids:
            return hits, None
        visible = await hasura.visible_documents(token, ids)
        for i, doc_id in enumerate(ids):
            if doc_id in visible:
                hits.append(visible[doc_id])
                if len(hits) == limit:
                    return hits, cursor + i + 1
        cursor += len(ids)
        if len(ids) < batch:
            return hits, None
    return hits, cursor


# --- đồng bộ chỉ mục -----------------------------------------------------------------------------


class _Source(Protocol):
    async def changed_documents(self, since: datetime, limit: int, offset: int) -> list[dict[str, Any]]: ...


class _Sink(Protocol):
    async def ensure_index(self) -> int: ...
    async def upsert(self, docs: list[dict[str, Any]]) -> int: ...


class Indexer:
    def __init__(
        self,
        source: _Source,
        sink: _Sink,
        *,
        interval_s: float = 5.0,
        overlap_s: float = 60.0,
        page: int = 500,
    ) -> None:
        self.source = source
        self.sink = sink
        self.interval_s = interval_s
        self.overlap = timedelta(seconds=overlap_s)
        self.page = page
        self.cursor: datetime | None = None
        self.last_task: int | None = None
        self.ready = False
        # id → updated_at đã đẩy trong cửa sổ overlap: không đẩy lại văn bản chưa đổi
        self._pushed: dict[str, datetime] = {}

    async def sync_once(self) -> int:
        """Một lượt đồng bộ; trả về số văn bản đã đẩy sang Meilisearch."""
        if not self.ready:
            self.last_task = await self.sink.ensure_index()
            self.ready = True
        since = self.cursor - self.overlap if self.cursor else EPOCH
        newest = self.cursor
        pushed = 0
        offset = 0
        while True:
            rows = await self.source.changed_documents(since, self.page, offset)
            fresh = []
            for row in rows:
                at = datetime.fromisoformat(row["updated_at"])
                newest = at if newest is None or at > newest else newest
                if self._pushed.get(row["id"]) != at:
                    fresh.append(row)
                    self._pushed[row["id"]] = at
            if fresh:
                self.last_task = await self.sink.upsert([to_index_doc(r) for r in fresh])
                pushed += len(fresh)
            if len(rows) < self.page:
                break
            offset += self.page
        self.cursor = newest
        if newest is not None:
            floor = newest - self.overlap
            self._pushed = {k: v for k, v in self._pushed.items() if v >= floor}
        return pushed

    async def run(self) -> None:
        while True:
            try:
                count = await self.sync_once()
                if count:
                    log.info(json.dumps({"event": "core.search.synced", "documents": count}))
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết; lượt sau thử lại
                log.warning(json.dumps({"event": "core.search.sync_failed", "error": str(exc)}, ensure_ascii=False))
            await asyncio.sleep(self.interval_s)
