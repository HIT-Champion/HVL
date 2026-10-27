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

"""Gọi Hasura GraphQL bằng vai trò service (db/README.md, mục "Dịch vụ gọi Hasura").

Mỗi yêu cầu mang thuê ước và người thực hiện của Action đang xử lý — lấy từ biến phiên Hasura gửi sang,
không từ dữ liệu client. Trigger sổ kiểm toán đọc các giá trị này nên mỗi thay đổi ghi đúng người làm.
Nhiều mutation trong một yêu cầu chạy trong một giao dịch: hoặc ghi hết, hoặc không ghi gì.
Tác tử gợi ý giao việc (F4.3, advisor.py) lưu gợi ý và ghi sổ bằng vai trò ``agent`` (``as_agent``).

Ở đây chỉ có máy khách và câu của phần chung (danh bạ); câu GraphQL của Văn phòng điện tử nằm ở
``office/queries.py``.
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


def _traced(headers: dict[str, str], request_id: str) -> dict[str, str]:
    """Mã yêu cầu đi cùng lời gọi: ``X-Hasura-Request-Id`` thành biến phiên, trigger sổ kiểm toán ghi vào
    ``core.audit_log.request_id``; ``X-Request-Id`` để nhật ký của Hasura (``docker logs``, cột ``request_id`` của log
    tập trung) mang cùng mã.
    Mã rỗng (việc nền không có yêu cầu gốc) thì không gửi gì."""
    if request_id:
        headers["X-Hasura-Request-Id"] = request_id
        headers["X-Request-Id"] = request_id
    return headers


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
        return await self._call(query, variables or {}, _traced(headers, actor.request_id))

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
        return await self._call(query, variables or {}, _traced(headers, actor.request_id))

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
        return await self._call(query, variables or {}, _traced(headers, request_id))


# --- danh bạ (directory.py) -----------------------------------------------------------------------------

TENANT_USERS = """
query TenantUsers { core_users { id department_id username full_name email role enabled } }"""

UPSERT_USERS = """
mutation UpsertUsers($rows: [core_users_insert_input!]!) {
  insert_core_users(objects: $rows, on_conflict: {constraint: users_pkey,
    update_columns: [department_id, username, full_name, email, role, enabled]}) { affected_rows }
}"""
