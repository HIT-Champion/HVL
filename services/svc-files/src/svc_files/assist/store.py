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

"""Sổ kiểm toán của trợ lý hỏi đáp (F4.2), qua Hasura bằng vai trò ``agent`` — như docread/store.py (F4.1).

Trợ lý không có client Keycloak: svc-files gọi Hasura bằng khóa quản trị kèm ``X-Hasura-Role: agent``, thuê ước lấy
từ token đã kiểm của người hỏi, ``X-Hasura-User-Id`` là danh tính tác tử (``MOC_ASSISTANT_ID``). Preset của vai trò ép
``actor_id``, ``actor_kind = agent``, thuê ước; check chỉ cho cặp ``assistant.answered`` / ``ai.questions`` (và
``intake.suggested`` / ``core.files`` của F4.1). Vai trò ``agent`` không đọc văn bản, không đọc chữ của tệp.

Mỗi lượt hỏi một dòng; ``entity_id`` là ``ask_id`` (lượt ``extract`` và lượt ``generate`` của cùng câu hỏi chung một
``ask_id``). ``diff`` chỉ có giá trị vô hướng (giao diện hiểu mảng là ``[cũ, mới]``) và **không** có câu hỏi, câu trả
lời, số ký hiệu, đoạn trích. Câu hỏi và câu trả lời không lưu ở đâu cả.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from ..hasura import HasuraError

LOG = """
mutation GhiSoTroLy($e: core_audit_log_insert_input!) { insert_core_audit_log(objects: [$e]) { affected_rows } }"""

ACTION = "assistant.answered"
ENTITY = "ai.questions"
ROLE = "agent"
DIFF_KEYS = ("user_id", "ask_id", "mode", "status", "answer_source", "hits", "cited", "documents", "semantic",
             "model", "embed_model", "duration_ms", "warnings", "route", "route_reason", "followup",
             "model_where")


class _Hasura(Protocol):
    async def as_role(self, role: str, tenant_id: uuid.UUID, user_id: str, request_id: str, query: str,
                      variables: dict[str, Any]) -> dict[str, Any]: ...


def audit_row(request_id: str, ask_id: str, diff: dict[str, Any]) -> dict[str, Any]:
    """Dòng sổ ``assistant.answered`` — chỉ các cột vai trò agent được ghi; người làm, thuê ước do preset đặt."""
    return {"request_id": request_id, "action": ACTION, "entity": ENTITY, "entity_id": ask_id,
            "diff": {k: diff.get(k) for k in DIFF_KEYS}}


class AnswerLog:
    def __init__(self, hasura: _Hasura, assistant_id: str) -> None:
        self.hasura = hasura
        self.assistant_id = assistant_id

    async def write(self, tenant_id: uuid.UUID, request_id: str, ask_id: str, diff: dict[str, Any]) -> None:
        """Ghi một dòng sổ; lỗi (cả khi Hasura không báo dòng nào được ghi) → ``HasuraError``."""
        data = await self.hasura.as_role(ROLE, tenant_id, self.assistant_id, request_id, LOG,
                                         {"e": audit_row(request_id, ask_id, diff)})
        written = ((data or {}).get("insert_core_audit_log") or {}).get("affected_rows")
        if written != 1:
            raise HasuraError("Hasura không ghi dòng sổ nào của trợ lý")
