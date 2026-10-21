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

"""Gợi ý đã đọc và sổ kiểm toán của tác tử đọc văn bản đến (F4.1), qua Hasura bằng vai trò ``agent``.

Tác tử không có client Keycloak: svc-files gọi Hasura bằng khóa quản trị kèm ``X-Hasura-Role: agent``, thuê ước lấy
từ token đã kiểm của văn thư, ``X-Hasura-User-Id`` là danh tính tác tử (``MOC_AGENT_ID``). Preset của vai trò ép
``tenant_id``, ``agent_id`` của gợi ý và ``actor_id``, ``actor_kind = agent`` của dòng sổ — dữ liệu gửi lên không
giả được. Vai trò ``agent`` không có quyền nào trên văn bản, không đọc ``core.files`` (db/metadata).

Lưu gợi ý và ghi sổ trong cùng một mutation = một giao dịch: không có gợi ý nào mà sổ không biết.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from ..hasura import HasuraError

SUGGESTION = """
query GoiYDaCo($id: uuid!) { office_intake_suggestions_by_pk(file_id: $id) { file_id status method pages fields warnings
  summary_source model duration_ms read_at } }"""

SAVE = """
mutation LuuGoiY($o: office_intake_suggestions_insert_input!, $e: core_audit_log_insert_input!) {
  insert_office_intake_suggestions_one(object: $o, on_conflict: {constraint: intake_suggestions_pkey, update_columns:
    [requested_by, status, method, pages, fields, warnings, summary_source, model, duration_ms]}) { file_id read_at }
  insert_core_audit_log(objects: [$e]) { affected_rows } }"""

LOG = """
mutation GhiSoTacTu($e: core_audit_log_insert_input!) { insert_core_audit_log(objects: [$e]) { affected_rows } }"""

# danh mục chung của mọi thuê ước (khóa code) — khóa quản trị
TYPES = """
query LoaiVanBan { office_document_types { code name in_symbol } }"""

ACTION = "intake.suggested"
ROLE = "agent"
TYPES_TTL_S = 600.0


class _Hasura(Protocol):
    async def as_role(self, role: str, tenant_id: uuid.UUID, user_id: str, request_id: str, query: str,
                      variables: dict[str, Any]) -> dict[str, Any]: ...
    async def admin(self, query: str, variables: dict[str, Any], headers: dict[str, str] | None = None,
                    ) -> dict[str, Any]: ...


def audit_row(request_id: str, file_id: uuid.UUID, diff: dict[str, Any]) -> dict[str, Any]:
    """Dòng sổ ``intake.suggested`` — chỉ các cột vai trò agent được ghi; người làm, thuê ước do preset đặt."""
    return {"request_id": request_id, "action": ACTION, "entity": "core.files", "entity_id": str(file_id),
            "diff": diff}


class SuggestionStore:
    def __init__(self, hasura: _Hasura, agent_id: str, *, types_ttl_s: float = TYPES_TTL_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.hasura = hasura
        self.agent_id = agent_id
        self.types_ttl_s = types_ttl_s
        self._clock = clock
        self._types: frozenset[str] | None = None
        self._types_at = 0.0

    async def _agent(self, tenant_id: uuid.UUID, request_id: str, query: str, variables: dict[str, Any],
                     ) -> dict[str, Any]:
        return await self.hasura.as_role(ROLE, tenant_id, self.agent_id, request_id, query, variables)

    async def cached(self, tenant_id: uuid.UUID, file_id: uuid.UUID, request_id: str) -> dict[str, Any] | None:
        data = await self._agent(tenant_id, request_id, SUGGESTION, {"id": str(file_id)})
        return data.get("office_intake_suggestions_by_pk")

    async def save(self, tenant_id: uuid.UUID, request_id: str, row: dict[str, Any], diff: dict[str, Any]) -> str:
        """Upsert gợi ý + một dòng sổ, cùng giao dịch; trả ``read_at`` do CSDL đặt."""
        data = await self._agent(tenant_id, request_id, SAVE,
                                 {"o": row, "e": audit_row(request_id, uuid.UUID(row["file_id"]), diff)})
        return str(data["insert_office_intake_suggestions_one"]["read_at"])

    async def log(self, tenant_id: uuid.UUID, request_id: str, file_id: uuid.UUID, diff: dict[str, Any]) -> None:
        """Chỉ ghi sổ (đọc hỏng: không có gợi ý để lưu)."""
        await self._agent(tenant_id, request_id, LOG, {"e": audit_row(request_id, file_id, diff)})

    async def type_codes(self) -> frozenset[str] | None:
        """Mã loại văn bản trong danh mục, giữ 10 phút. CSDL lỗi thì dùng bản cũ, chưa có bản nào thì None."""
        now = self._clock()
        if self._types is None or now - self._types_at >= self.types_ttl_s:
            try:
                data = await self.hasura.admin(TYPES, {})
                codes = frozenset(str(t["code"]) for t in data.get("office_document_types") or [])
            except (HasuraError, KeyError, TypeError, AttributeError):
                return self._types      # danh mục chỉ để lọc mã; CSDL lỗi thật thì bước lưu sẽ báo
            self._types, self._types_at = codes, now
        return self._types
