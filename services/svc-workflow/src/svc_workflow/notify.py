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

"""Thông báo từng người (F2.5): ghi ``core.notifications`` rồi đẩy qua Centrifugo tới kênh riêng của người nhận.

Bảng là nơi giữ thông báo; Centrifugo chỉ đẩy bản sao tới trình duyệt đang mở. Đẩy hỏng thì người dùng vẫn thấy
khi tải lại trang, nên lỗi đẩy chỉ ghi nhật ký. Khóa chống trùng (ràng buộc ``notifications_once``): gọi lại một
Action, timer bắn lại không sinh thông báo thứ hai và không đẩy lại.

Kênh riêng là ``personal:#<sub>``: Centrifugo tự đưa mỗi kết nối vào kênh của đúng người trong token Keycloak đã
kiểm, trình duyệt không tự đăng ký được kênh của người khác (realtime/config.yaml).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx2

from .flowable import FlowableClient, Task
from .hasura import Actor, HasuraClient

log = logging.getLogger("svc_workflow")

NOTIFY = """
mutation Notify($rows: [core_notifications_insert_input!]!) {
  insert_core_notifications(objects: $rows, on_conflict: {constraint: notifications_once, update_columns: []}) {
    returning { id user_id kind document_id data created_at }
  }
}"""

PEOPLE = """
query People {
  core_users(where: {enabled: {_eq: true}}) { id role department_id full_name }
}"""


@dataclass(frozen=True)
class Person:
    id: str
    role: str
    department_id: str | None
    full_name: str


class People(dict[str, Person]):
    """Người dùng đang hoạt động của một thuê ước, theo id (sub)."""

    def with_role(self, role: str, department_id: str | None = None) -> set[str]:
        return {p.id for p in self.values()
                if p.role == role and (department_id is None or p.department_id == department_id)}

    def group(self, tenant: str, name: str) -> set[str]:
        """Người trong nhóm ứng viên Flowable: t:<tenant>:director, t:<tenant>:clerk, t:<tenant>:d:<phòng>:manager."""
        parts = name.split(":")
        if len(parts) < 3 or parts[0] != "t" or parts[1] != tenant:
            return set()
        if len(parts) == 3 and parts[2] in ("director", "clerk"):
            return self.with_role(parts[2])
        if len(parts) == 5 and parts[2] == "d" and parts[4] == "manager":
            return self.with_role("manager", parts[3])
        return set()

    def leaders(self, tenant: str, assignee: str | None, groups: Iterable[str]) -> set[str]:
        """Người phải biết khi một việc để quá hạn: lãnh đạo phòng của chuyên viên, còn lại là lãnh đạo đơn vị.

        Việc của chính lãnh đạo đơn vị thì không báo ai thêm.
        """
        if assignee:
            person = self.get(assignee)
            if person is None or person.role == "director":
                return set()
            if person.role == "staff" and person.department_id:
                managers = self.with_role("manager", person.department_id) - {assignee}
                if managers:
                    return managers
            return self.with_role("director") - {assignee}
        if any(g == f"t:{tenant}:director" for g in groups):
            return set()
        return self.with_role("director")


def brief_of(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Phần văn bản ghi kèm thông báo. Văn bản hạn chế (F3.7) chỉ có nhãn, không trích yếu, số ký hiệu — CSDL cũng
    gọt cho mọi đường ghi (migration 1792281601600), đây là để khỏi gửi đi ngay từ đầu."""
    if not doc:
        return {}
    if doc.get("restricted"):
        return {**{k: doc[k] for k in ("urgency", "direction") if doc.get(k)}, "restricted": True}
    return {k: doc[k] for k in ("summary", "symbol", "urgency", "direction") if doc.get(k)}


async def load_people(hasura: HasuraClient, actor: Actor) -> People:
    rows = (await hasura.as_service(actor, PEOPLE))["core_users"]
    return People({r["id"]: Person(r["id"], r["role"], r["department_id"], r["full_name"]) for r in rows})


async def task_people(flowable: FlowableClient, actor: Actor, task: Task, people: People) -> set[str]:
    """Người phải làm một việc: người được giao đích danh, hoặc mọi người trong các nhóm ứng viên."""
    if task.assignee:
        return {task.assignee} if task.assignee in people else set()
    found: set[str] = set()
    for group in await flowable.candidate_groups(task.id):
        found |= people.group(str(actor.tenant_id), group)
    return found


class Notifier:
    def __init__(self, hasura: HasuraClient, centrifugo_url: str = "", api_key: str = "", *,
                 timeout_s: float = 3.0, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.hasura = hasura
        self._key = api_key
        # không cấu hình Centrifugo thì chỉ lưu thông báo, người dùng thấy khi tải lại trang
        self._http = (httpx2.AsyncClient(base_url=centrifugo_url, timeout=timeout_s, transport=transport)
                      if centrifugo_url and api_key else None)

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def people(self, actor: Actor) -> People:
        return await load_people(self.hasura, actor)

    async def task_people(self, flowable: FlowableClient, actor: Actor, task: Task, people: People) -> set[str]:
        return await task_people(flowable, actor, task, people)

    async def send(self, actor: Actor, user_ids: Iterable[str], kind: str, key: str,
                   document_id: str | None, data: dict[str, Any]) -> list[str]:
        """Ghi rồi đẩy một thông báo cho từng người → những người vừa nhận (bỏ người đã có thông báo cùng khóa).

        Lỗi ghi CSDL (HasuraError) được ném ra cho nơi gọi quyết định; lỗi đẩy chỉ ghi nhật ký.
        """
        users = sorted({u for u in user_ids if u})
        if not users:
            return []
        rows = [{"user_id": u, "kind": kind, "key": key, "document_id": document_id, "data": data} for u in users]
        result = await self.hasura.as_service(actor, NOTIFY, {"rows": rows})
        created = result["insert_core_notifications"]["returning"]
        await self._push(created)
        return [row["user_id"] for row in created]

    async def _push(self, rows: list[dict[str, Any]]) -> None:
        if self._http is None or not rows:
            return
        commands = [
            {"publish": {"channel": f"personal:#{row['user_id']}",
                         "data": {k: row[k] for k in ("id", "kind", "document_id", "data", "created_at")}}}
            for row in rows
        ]
        try:
            r = await self._http.post("/api/batch", json={"commands": commands}, headers={"X-API-Key": self._key})
        except httpx2.HTTPError as exc:
            log.warning(json.dumps({"event": "core.notification.push_failed", "error": str(exc)}, ensure_ascii=False))
            return
        if r.status_code != 200:
            log.warning(json.dumps({"event": "core.notification.push_failed", "status": r.status_code}))
            return
        try:
            replies = r.json().get("replies", [])
        except ValueError:
            replies = [{"error": "trả lời không phải JSON"}]
        errors = [reply["error"] for reply in replies if "error" in reply]
        if errors:
            log.warning(json.dumps({"event": "core.notification.push_failed", "errors": errors}, ensure_ascii=False))
