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

"""Gọi Hasura GraphQL bằng vai trò service (db/README.md, mục "Dịch vụ gọi Hasura").

Mỗi yêu cầu mang thuê ước và người thực hiện của Action đang xử lý — lấy từ biến phiên Hasura gửi sang,
không từ dữ liệu client. Trigger sổ kiểm toán đọc các giá trị này nên mỗi thay đổi ghi đúng người làm.
Nhiều mutation trong một yêu cầu chạy trong một giao dịch: hoặc ghi hết, hoặc không ghi gì.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx2


class HasuraError(Exception):
    """Hasura không trả lời, hoặc trả lỗi."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Actor:
    """Người gọi Action, lấy từ biến phiên Hasura (đã kiểm từ JWT)."""

    user_id: str
    tenant_id: uuid.UUID
    role: str
    department_id: uuid.UUID | None
    request_id: str = ""

    @classmethod
    def from_session(cls, session: dict[str, str], request_id: str = "") -> Actor:
        dept = session.get("x-hasura-department-id")
        return cls(
            user_id=session["x-hasura-user-id"],
            tenant_id=uuid.UUID(session["x-hasura-tenant-id"]),
            role=session["x-hasura-role"],
            department_id=uuid.UUID(dept) if dept else None,
            request_id=request_id,
        )

    @property
    def groups(self) -> list[str]:
        """Nhóm ứng viên Flowable của người này (xem processes/*.bpmn20.xml)."""
        t = self.tenant_id
        if self.role == "director":
            return [f"t:{t}:director"]
        if self.role == "manager" and self.department_id:
            return [f"t:{t}:d:{self.department_id}:manager"]
        if self.role == "clerk":
            return [f"t:{t}:clerk"]
        return []


class HasuraClient:
    def __init__(
        self,
        base_url: str,
        admin_secret: str,
        *,
        timeout_s: float = 10.0,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._secret = admin_secret
        self._http = httpx2.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._http.get("/healthz")
        except httpx2.HTTPError:
            return False
        return r.status_code == 200

    async def _call(self, query: str, variables: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            r = await self._http.post("/v1/graphql", json={"query": query, "variables": variables}, headers=headers)
        except httpx2.HTTPError as exc:
            raise HasuraError(f"Không gọi được Hasura: {exc}") from exc
        if r.status_code != 200:
            raise HasuraError(f"Hasura trả HTTP {r.status_code}")
        body = r.json()
        if body.get("errors"):
            first = body["errors"][0]
            raise HasuraError(str(first.get("message")), (first.get("extensions") or {}).get("code"))
        return body["data"]

    async def as_service(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "X-Hasura-Admin-Secret": self._secret,
            "X-Hasura-Role": "service",
            "X-Hasura-Tenant-Id": str(actor.tenant_id),
            "X-Hasura-User-Id": actor.user_id,
        }
        if actor.request_id:
            headers["X-Hasura-Request-Id"] = actor.request_id
        return await self._call(query, variables or {}, headers)

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Việc nội bộ chỉ đọc, xuyên thuê ước (đối soát): khóa quản trị, không kèm vai trò."""
        return await self._call(query, variables or {}, {"X-Hasura-Admin-Secret": self._secret})


# --- truy vấn dùng chung -------------------------------------------------------------------------------

REGISTER_INCOMING = """
mutation Register($id: uuid!) {
  office_register_incoming(args: {document_id: $id}) { id status register_number process_id urgency due_on }
}"""

SET_PROCESS = """
mutation SetProcess($id: uuid!, $pid: String!) {
  update_office_documents_by_pk(pk_columns: {id: $id}, _set: {process_id: $pid}) { id }
}"""

DOCUMENT = """
query Document($id: uuid!) {
  office_documents_by_pk(id: $id) { id direction status urgency due_on registered_at process_id }
}"""

OPEN_ASSIGNMENTS = """
query OpenAssignments($doc: uuid!) {
  office_assignments(where: {document_id: {_eq: $doc}, status: {_eq: "open"}}) {
    id parent_id department_id user_id role due_on assigned_by
  }
}"""

USER = """
query User($id: String!) {
  core_users_by_pk(id: $id) { id department_id role enabled }
}"""

# Văn bản đi: đủ trường để kiểm trước khi trình, duyệt, phát hành
OUTGOING = """
query Outgoing($id: uuid!) {
  office_documents_by_pk(id: $id) {
    id direction status created_by department_id signer_id process_id urgency summary body recipients
    register_number symbol verify_code
  }
}"""

NUMBER_OUTGOING = """
mutation NumberOutgoing($id: uuid!, $code: String!) {
  office_number_outgoing(args: {document_id: $id, verify_code: $code}) { id register_number symbol verify_code }
}"""

# Vài dòng về văn bản để ghi vào thông báo (trích yếu, số ký hiệu) — giữ nguyên như lúc gửi
BRIEF = """
query Brief($id: uuid!) {
  office_documents_by_pk(id: $id) { id direction summary symbol urgency created_by signer_id }
}"""

TASK_DONE = """
query TaskDone($doc: uuid!, $task: jsonb!) {
  office_document_events(where: {document_id: {_eq: $doc}, data: {_contains: $task}}, limit: 1) { id }
}"""

# Đối soát: văn bản đã vào sổ mà chưa gắn quy trình (lỗi giữa chừng lúc registerIncoming)
UNLINKED = """
query Unlinked {
  office_documents(where: {direction: {_eq: "in"}, status: {_eq: "registered"}, process_id: {_is_null: true}},
                   limit: 100) { id tenant_id urgency due_on created_by }
}"""

# Văn bản đến quá hạn giải quyết mà chưa báo (xuyên thuê ước, vòng nền của svc-workflow)
OVERDUE_DOCUMENTS = """
query OverdueDocuments($today: date!) {
  office_documents(where: {direction: {_eq: "in"}, status: {_eq: "in_progress"}, due_on: {_lt: $today},
                           _not: {events: {kind: {_eq: "office.document.overdue"}}}},
                   order_by: {due_on: asc}, limit: 100) {
    id tenant_id summary symbol due_on
    assignments(where: {status: {_eq: "open"}}) { user_id department_id assigned_by }
  }
}"""

TENANT_USERS = """
query TenantUsers { core_users { id department_id username full_name email role enabled } }"""

UPSERT_USERS = """
mutation UpsertUsers($rows: [core_users_insert_input!]!) {
  insert_core_users(objects: $rows, on_conflict: {constraint: users_pkey,
    update_columns: [department_id, username, full_name, email, role, enabled]}) { affected_rows }
}"""
