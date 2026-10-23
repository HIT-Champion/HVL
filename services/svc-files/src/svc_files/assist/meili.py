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

"""Chỉ mục đoạn của trợ lý hỏi đáp (F4.2) trên Meilisearch: một tài liệu mỗi đoạn, khóa ``id``.

Dùng lại ``MeiliClient`` của tìm kiếm F2.7 (gọi HTTP, phân loại lỗi, ``wait``), chỉ mục riêng ``MOC_ASK_INDEX``.

Tìm theo nghĩa bằng embedder ``userProvided``: svc-files tự gọi Ollama ``/api/embed`` rồi ghi véc-tơ vào
``_vectors.<embedder>``. Không dùng nguồn ``ollama`` của Meilisearch: Meilisearch phải vào mạng ``ai``, và khi Ollama
tắt (CI) tác vụ thêm tài liệu lỗi cả lô — hỏng luôn đường từ khóa. ``_vectors.<embedder>: null`` = chưa có véc-tơ,
đoạn vẫn tìm được bằng từ khóa. Embedder đặt tên theo mô hình (``embedder_name``): đổi mô hình là bỏ embedder cũ
(cùng véc-tơ của nó) và vòng nền nhúng lại.
"""

from __future__ import annotations

import re
from typing import Any

from ..search import MeiliClient, SearchError

SEARCHABLE = ["text", "symbol", "summary", "issuer_name"]          # thứ tự là thứ tự ưu tiên khi xếp hạng
FILTERABLE = ["tenant_id", "document_id", "direction", "status", "type_code", "year", "department_id", "created_by",
              "assignee_departments", "assignee_users", "kind", "embed_model"]
DISPLAYED = ["id", "document_id", "kind", "file_id", "file_role", "page", "seq", "text", "symbol", "summary",
             "text_sha", "meta_sha", "embed_model"]
EMBEDDER_PREFIX = "emb_"


def embedder_name(model: str) -> str:
    """Tên embedder Meilisearch của một mô hình nhúng: ``"emb_"`` + slug chữ thường (``[^a-z0-9]+`` → ``_``),
    vd ``qwen3-embedding:0.6b`` → ``emb_qwen3_embedding_0_6b``."""
    return EMBEDDER_PREFIX + re.sub(r"[^a-z0-9]+", "_", model.lower())


class ChunkIndex(MeiliClient):
    """Chỉ mục ``chunks``. Mọi hàm ghi trả về uid tác vụ của Meilisearch; ``wait`` để đợi tác vụ xong.

    Cấu hình áp làm hai tác vụ riêng (mỗi lần khởi động, như F2.7): ``ensure`` cho tìm từ khóa — đồng bộ đoạn cần nó;
    ``ensure_embedder`` cho tìm theo nghĩa — lỗi thì chỉ mất tìm theo nghĩa, đồng bộ và xóa đoạn vẫn chạy."""

    async def ensure(self) -> int:
        """Tạo chỉ mục nếu chưa có, áp cấu hình tìm từ khóa; trả về uid tác vụ cấu hình."""
        try:
            await self._request("GET", f"/indexes/{self.index}")
        except SearchError:      # chưa có chỉ mục (lỗi khác thì lần tạo dưới đây cũng lỗi và đi lên)
            await self._request("POST", "/indexes", {"uid": self.index, "primaryKey": "id"})
        settings = {"searchableAttributes": SEARCHABLE, "filterableAttributes": FILTERABLE,
                    "displayedAttributes": DISPLAYED}
        task = await self._request("PATCH", f"/indexes/{self.index}/settings", settings)
        return int(task["taskUid"])

    async def ensure_embedder(self, embedder: str | None, dims: int) -> int | None:
        """Áp cấu hình embedder (sau ``ensure``); trả về uid tác vụ, None khi không có gì để đổi.

        Mọi embedder ``emb_*`` khác ``embedder`` bị bỏ (đặt null): đổi mô hình thì véc-tơ cũ không còn dùng được.
        ``embedder`` None: không tìm theo nghĩa, không embedder nào."""
        current = await self._request("GET", f"/indexes/{self.index}/settings/embedders") or {}
        embedders: dict[str, Any] = {name: None for name in current
                                     if name.startswith(EMBEDDER_PREFIX) and name != embedder}
        if embedder:
            embedders[embedder] = {"source": "userProvided", "dimensions": dims}
        if not embedders:
            return None
        task = await self._request("PATCH", f"/indexes/{self.index}/settings", {"embedders": embedders})
        return int(task["taskUid"])

    async def fetch(self, filter: str | list[Any] | None, fields: list[str], limit: int,  # noqa: A002 — tên của API
                    offset: int = 0) -> list[dict[str, Any]]:
        """Tài liệu khớp bộ lọc (không có ``_vectors``), theo thứ tự trong chỉ mục."""
        body: dict[str, Any] = {"fields": fields, "limit": limit, "offset": offset}
        if filter is not None:
            body["filter"] = filter
        data = await self._request("POST", f"/indexes/{self.index}/documents/fetch", body)
        return list(data.get("results") or [])

    async def count(self, filter: str | list[Any]) -> int:  # noqa: A002 — tên của API
        """Số tài liệu khớp bộ lọc: ``total`` của ``/documents/fetch`` (không bị chặn 1 000 như ``estimatedTotalHits``
        của ``/search``)."""
        data = await self._request("POST", f"/indexes/{self.index}/documents/fetch",
                                   {"filter": filter, "fields": ["id"], "limit": 1})
        return int(data.get("total") or 0)

    async def replace(self, docs: list[dict[str, Any]]) -> int:
        """Thêm hoặc thay cả tài liệu (POST): trường nào không gửi thì mất."""
        task = await self._request("POST", f"/indexes/{self.index}/documents?primaryKey=id", docs)
        return int(task["taskUid"])

    async def update(self, docs: list[dict[str, Any]]) -> int:
        """Cập nhật một phần (PUT): chỉ các trường gửi lên, trường khác giữ nguyên."""
        task = await self._request("PUT", f"/indexes/{self.index}/documents?primaryKey=id", docs)
        return int(task["taskUid"])

    async def delete_ids(self, ids: list[str]) -> int:
        task = await self._request("POST", f"/indexes/{self.index}/documents/delete-batch", ids)
        return int(task["taskUid"])

    async def delete_where(self, filter: str | list[Any]) -> int:  # noqa: A002 — tên của API
        task = await self._request("POST", f"/indexes/{self.index}/documents/delete", {"filter": filter})
        return int(task["taskUid"])

    async def search(self, body: dict[str, Any]) -> list[dict[str, Any]]:  # type: ignore[override]
        """Tìm với thân yêu cầu dựng sẵn (retrieve.py); mỗi kết quả giữ ``_rankingScore`` nếu có."""
        data = await self._request("POST", f"/indexes/{self.index}/search", body)
        return list(data.get("hits") or [])

    async def multi_search(self, bodies: list[dict[str, Any]]) -> list[tuple[list[dict[str, Any]], int]]:
        """Nhiều câu tìm trên chỉ mục này trong một yêu cầu (``/multi-search``) → (kết quả, ``estimatedTotalHits``)
        theo đúng thứ tự câu tìm."""
        data = await self._request("POST", "/multi-search",
                                   {"queries": [{"indexUid": self.index, **body} for body in bodies]})
        return [(list(r.get("hits") or []), int(r.get("estimatedTotalHits") or 0)) for r in data.get("results") or []]
