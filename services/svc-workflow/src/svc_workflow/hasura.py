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
Tác tử gợi ý giao việc (F4.3, advisor.py) lưu gợi ý và ghi sổ bằng vai trò ``agent`` (``as_agent``).
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

    async def as_user(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Hỏi bằng đúng vai trò và phiên của người gọi Action: quyền đọc do Hasura xét như khi chính họ hỏi."""
        headers = {
            "X-Hasura-Admin-Secret": self._secret,
            "X-Hasura-Role": actor.role,
            "X-Hasura-Tenant-Id": str(actor.tenant_id),
            "X-Hasura-User-Id": actor.user_id,
        }
        if actor.department_id:
            headers["X-Hasura-Department-Id"] = str(actor.department_id)
        return await self._call(query, variables or {}, headers)

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Việc nội bộ chỉ đọc, xuyên thuê ước (đối soát): khóa quản trị, không kèm vai trò."""
        return await self._call(query, variables or {}, {"X-Hasura-Admin-Secret": self._secret})

    async def as_agent(self, tenant_id: uuid.UUID, agent_id: str, query: str, variables: dict[str, Any] | None = None,
                       *, request_id: str = "") -> dict[str, Any]:
        """Tác tử (F4.3, gợi ý giao việc): vai trò ``agent``, danh tính tác tử ở ``X-Hasura-User-Id``. Preset của vai
        trò ép thuê ước, ``agent_id`` của gợi ý, ``actor_id`` và ``actor_kind = agent`` của dòng sổ — dữ liệu gửi lên
        không giả được; vai trò này không đọc, không sửa văn bản (db/metadata)."""
        headers = {
            "X-Hasura-Admin-Secret": self._secret,
            "X-Hasura-Role": "agent",
            "X-Hasura-Tenant-Id": str(tenant_id),
            "X-Hasura-User-Id": agent_id,
        }
        if request_id:
            headers["X-Hasura-Request-Id"] = request_id
        return await self._call(query, variables or {}, headers)


# --- truy vấn dùng chung -------------------------------------------------------------------------------

REGISTER_INCOMING = """
mutation Register($id: uuid!) {
  office_register_incoming(args: {document_id: $id}) { id status register_number process_id urgency due_on }
}"""

# Gắn quy trình chỉ khi văn bản chưa có: hai lần gọi chen nhau (bấm đúp, job đối soát) thì một lần thắng
CLAIM_PROCESS = """
mutation ClaimProcess($id: uuid!, $pid: String!) {
  update_office_documents(where: {id: {_eq: $id}, process_id: {_is_null: true}}, _set: {process_id: $pid}) {
    affected_rows
  }
}"""

PROCESS_OF = """
query ProcessOf($id: uuid!) {
  office_documents_by_pk(id: $id) { process_id }
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
    register_number symbol verify_code restricted recipient_tenant_ids
  }
}"""

NUMBER_OUTGOING = """
mutation NumberOutgoing($id: uuid!, $code: String!) {
  office_number_outgoing(args: {document_id: $id, verify_code: $code}) { id register_number symbol verify_code }
}"""

# Vài dòng về văn bản để ghi vào thông báo (trích yếu, số ký hiệu) — giữ nguyên như lúc gửi
BRIEF = """
query Brief($id: uuid!) {
  office_documents_by_pk(id: $id) { id direction summary symbol urgency created_by signer_id restricted }
}"""

# Văn bản hạn chế (F3.7): người phải làm việc đang mở được thêm vào danh sách xem; đã có tên thì giữ nguyên
SHARE = """
mutation ChoXem($rows: [office_document_acl_insert_input!]!) {
  insert_office_document_acl(objects: $rows, on_conflict: {constraint: document_acl_pkey, update_columns: []}) {
    affected_rows
  }
}"""

# Văn bản hạn chế (F3.7): ai được nhắc hạn — người có tên trong danh sách xem và người tạo
READERS = """
query Readers($id: uuid!) {
  office_documents_by_pk(id: $id) { restricted created_by }
  office_document_acl(where: {document_id: {_eq: $id}}) { user_id }
}"""

# Hỏi bằng phiên của người gọi (as_user): null nếu người đó không đọc được văn bản
VISIBLE = """
query Visible($id: uuid!) {
  office_documents_by_pk(id: $id) { id }
}"""

TASK_DONE = """
query TaskDone($doc: uuid!, $task: jsonb!) {
  office_document_events(where: {document_id: {_eq: $doc}, data: {_contains: $task}}, limit: 1) { id data }
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
    id tenant_id summary symbol due_on restricted
    assignments(where: {status: {_eq: "open"}}) { user_id department_id assigned_by }
  }
}"""

TENANT_USERS = """
query TenantUsers { core_users { id department_id username full_name email role enabled } }"""

# --- liên thông văn bản trong hệ thống (F3.12, dispatch.py) ----------------------------------------------

# Đối soát (as_system, xuyên thuê ước): dòng chờ chuyển đã đến hạn thử, và dòng đã chuyển mà chưa báo bên nhận
PENDING_DISPATCHES = """
query PendingDispatches($now: timestamptz!) {
  office_dispatches(where: {_or: [
    {status: {_eq: "pending"}, next_attempt_at: {_lte: $now}},
    {status: {_in: ["delivered", "duplicate"]}, notified_at: {_is_null: true}}
  ]}, order_by: {created_at: asc}, limit: 50) { id }
}"""

# as_system: attempts để tính lần thử sau (lùi dần), from_unit để ghi tên đơn vị gửi vào thông báo
DISPATCH = """
query Dispatch($id: uuid!) {
  office_dispatches_by_pk(id: $id) {
    id tenant_id to_tenant_id document_id status incoming_document_id notified_at attempts from_unit { name }
  }
}"""

# as_system: dòng chờ chuyển của một văn bản vừa phát hành
DOCUMENT_DISPATCHES = """
query DocumentDispatches($doc: uuid!) {
  office_dispatches(where: {document_id: {_eq: $doc}, status: {_eq: "pending"}}) { id }
}"""

# Gọi trong phiên của bên nhận (hàm office.deliver_dispatch): văn bản đến, tệp, sự kiện của hai bên, một giao dịch
DELIVER = """
mutation Deliver($id: uuid!) {
  office_deliver_dispatch(args: {dispatch_id: $id}) { id status incoming_document_id last_error }
}"""

DISPATCH_RETRY = """
mutation DispatchRetry($id: uuid!, $error: String!, $next: timestamptz!) {
  update_office_dispatches_by_pk(pk_columns: {id: $id}, _inc: {attempts: 1},
                                 _set: {last_error: $error, next_attempt_at: $next}) { id }
}"""

# svc-files từ chối chép vĩnh viễn: dòng chờ thành failed (hàm office.fail_dispatch, phiên của bên gửi)
FAIL_DISPATCH = """
mutation FailDispatch($id: uuid!, $reason: String!) {
  office_fail_dispatch(args: {dispatch_id: $id, reason: $reason}) { id status last_error }
}"""

DISPATCH_NOTIFIED = """
mutation DispatchNotified($id: uuid!, $now: timestamptz!) {
  update_office_dispatches_by_pk(pk_columns: {id: $id}, _set: {notified_at: $now}) { id }
}"""

# Hỏi bằng phiên service của người trình: view chỉ có các đơn vị khác, không có chính đơn vị mình
DISPATCH_UNITS = """
query DispatchUnits($ids: [uuid!]!) {
  office_dispatch_units(where: {id: {_in: $ids}}) { id name }
}"""

UPSERT_USERS = """
mutation UpsertUsers($rows: [core_users_insert_input!]!) {
  insert_core_users(objects: $rows, on_conflict: {constraint: users_pkey,
    update_columns: [department_id, username, full_name, email, role, enabled]}) { affected_rows }
}"""
