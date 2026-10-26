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

"""Gọi Flowable REST (chỉ trong mạng nội bộ, tài khoản rest-admin).

Flowable là chủ trạng thái quy trình: đang ở bước nào, ai phải làm. Dữ liệu nghiệp vụ nằm ở PostgreSQL
(docs/du-thi/ke-hoach-phat-trien.md §2.1). Flowable không biết người dùng Keycloak; việc được giao cho nhóm
ứng viên dạng ``t:<tenant>:director`` hoặc ``t:<tenant>:d:<phòng>:manager``, hoặc đích danh theo ``sub``.

Hoàn thành việc (``complete``) và việc giao ra ngoài (``complete_job``) có thể đụng một giao dịch khác trên cùng phiên
quy trình, ví dụ worker gợi ý giao việc: Flowable khóa lạc quan, rollback một bên và REST trả 500 "Unhandled
exception" kèm ``FlowableOptimisticLockingException``. Chỉ lỗi đó được gọi lại, sau ``RETRY_DELAYS_S`` (#189).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import pathlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx2

log = logging.getLogger("svc_workflow")

# thông điệp của FlowableOptimisticLockingException (DbSqlSession), REST đặt vào trường "exception" của body lỗi 500
CONCURRENT = "was updated by another transaction concurrently"
RETRY_DELAYS_S = (0.2, 0.5)    # gọi lại sau chừng này giây; giao dịch bị hủy đã rollback hết nên gọi lại an toàn


class FlowableError(Exception):
    def __init__(self, message: str, status: int | None = None, *, concurrent: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.concurrent = concurrent    # bị hủy vì giao dịch khác cùng sửa phiên quy trình (khóa lạc quan)


@dataclass(frozen=True)
class ExternalJob:
    """Việc Flowable giao ra ngoài (external worker): ở đây là bước "nhắc hạn" sau timer quá hạn."""

    id: str
    process_instance_id: str
    element_id: str
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    form_key: str
    assignee: str | None
    process_instance_id: str
    created_at: str
    variables: dict[str, Any] = field(default_factory=dict)
    # "<khóa>:<phiên bản>:<id>": khóa cho biết việc thuộc quy trình Văn phòng hay của một ứng dụng (apps/)
    process_definition_id: str = ""
    due_at: str | None = None

    @property
    def process_key(self) -> str:
        """Khóa quy trình; rỗng khi id không mang khóa (Flowable bỏ khóa khi id quá 64 ký tự, xem apps/bpmn.MAX_KEY):
        không khớp quy trình nào, việc không lộ sang ứng dụng khác."""
        key, sep, _ = self.process_definition_id.partition(":")
        return key if sep else ""


def _variables(values: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for name, value in values.items():
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, int):
            kind = "long"
        else:
            kind, value = "string", ("" if value is None else str(value))
        out.append({"name": name, "type": kind, "value": value})
    return out


def _task(row: dict[str, Any]) -> Task:
    return Task(
        id=row["id"],
        name=row.get("name") or "",
        form_key=row.get("formKey") or "",
        assignee=row.get("assignee"),
        process_instance_id=row["processInstanceId"],
        created_at=row["createTime"],
        variables={v["name"]: v.get("value") for v in row.get("variables") or []},
        process_definition_id=row.get("processDefinitionId") or "",
        due_at=row.get("dueDate"),
    )


class FlowableClient:
    def __init__(
        self,
        base_url: str,
        user: str,
        password: str,
        *,
        timeout_s: float = 15.0,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx2.AsyncClient(base_url=base_url, auth=(user, password), timeout=timeout_s, transport=transport)
        # API external worker nằm cạnh REST API chính: …/flowable-rest/external-job-api
        self._jobs = base_url.rstrip("/").removesuffix("/service") + "/external-job-api/acquire/jobs"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            r = await self._http.request(method, path, **kwargs)
        except httpx2.HTTPError as exc:
            raise FlowableError(f"Không gọi được Flowable: {exc}") from exc
        if r.status_code >= 400:
            raise FlowableError(f"Flowable trả {r.status_code}: {r.text[:300]}", r.status_code,
                                concurrent=r.status_code == 500 and CONCURRENT in r.text)
        return r.json() if r.content else None

    async def ping(self) -> bool:
        try:
            await self._request("GET", "/management/engine")
        except FlowableError:
            return False
        return True

    # --- định nghĩa quy trình ---------------------------------------------------------------------

    async def deploy_dir(self, directory: str) -> list[str]:
        """Deploy mọi *.bpmn20.xml chưa có; tên deployment gắn băm nội dung nên tệp không đổi thì bỏ qua."""
        deployed = []
        for path in sorted(pathlib.Path(directory).glob("*.bpmn20.xml")):
            content = path.read_bytes()
            name = f"{path.name.removesuffix('.bpmn20.xml')}@{hashlib.sha256(content).hexdigest()[:12]}"
            existing = await self._request("GET", "/repository/deployments", params={"name": name})
            if existing["data"]:
                continue
            await self._request(
                "POST", "/repository/deployments", params={"deploymentName": name},
                files={"file": (path.name, content, "text/xml")},
            )
            deployed.append(name)
        return deployed

    # --- phiên quy trình ----------------------------------------------------------------------------

    async def find_process(self, key: str, business_key: str) -> str | None:
        data = await self._request(
            "GET", "/runtime/process-instances", params={"processDefinitionKey": key, "businessKey": business_key},
        )
        if data["data"]:
            return data["data"][0]["id"]
        # đã chạy xong cũng tính là có (không khởi chạy lại)
        hist = await self._request(
            "GET", "/history/historic-process-instances",
            params={"processDefinitionKey": key, "businessKey": business_key},
        )
        return hist["data"][0]["id"] if hist["data"] else None

    async def start_process(self, key: str, business_key: str, variables: dict[str, Any]) -> str:
        data = await self._request(
            "POST", "/runtime/process-instances",
            json={"processDefinitionKey": key, "businessKey": business_key, "variables": _variables(variables)},
        )
        return data["id"]

    async def delete_process(self, process_id: str, reason: str) -> None:
        """Hủy phiên vừa khởi chạy thừa (lần gọi khác đã gắn phiên của nó vào văn bản): chưa ai làm gì trong đó."""
        await self._request("DELETE", f"/runtime/process-instances/{process_id}", params={"deleteReason": reason})

    async def set_variables(self, process_id: str, variables: dict[str, Any]) -> None:
        """Ghi biến của phiên quy trình: PUT tạo biến chưa có, ghi đè biến đã có (POST thì 409 khi đã có). Chỉ tác dụng
        với việc tạo sau đó — việc đang mở giữ người được giao lúc tạo."""
        await self._request("PUT", f"/runtime/process-instances/{process_id}/variables", json=_variables(variables))

    # --- việc ---------------------------------------------------------------------------------------

    async def tasks_for(self, user_id: str, groups: list[str]) -> list[Task]:
        """Việc giao đích danh cho user_id, cộng việc chưa ai nhận của các nhóm ứng viên."""
        found: dict[str, Task] = {}
        queries = [{"assignee": user_id}]
        if groups:
            queries.append({"candidateGroupIn": groups, "unassigned": True})
        for q in queries:
            data = await self._request(
                "POST", "/query/tasks", json={**q, "includeProcessVariables": True, "size": 500},
            )
            for row in data["data"]:
                found[row["id"]] = _task(row)
        return list(found.values())

    async def task(self, task_id: str) -> Task | None:
        try:
            row = await self._request("GET", f"/runtime/tasks/{task_id}")
        except FlowableError as exc:
            if exc.status == 404:
                return None
            raise
        variables = await self._request("GET", f"/runtime/process-instances/{row['processInstanceId']}/variables")
        row["variables"] = variables
        return _task(row)

    async def process_tasks(self, process_instance_id: str) -> list[Task]:
        """Việc đang mở của một phiên quy trình — sau mỗi bước, để báo người phải làm bước kế tiếp."""
        data = await self._request(
            "POST", "/query/tasks",
            json={"processInstanceId": process_instance_id, "includeProcessVariables": True, "size": 50},
        )
        return [_task(row) for row in data["data"]]

    async def candidate_groups(self, task_id: str) -> list[str]:
        links = await self._request("GET", f"/runtime/tasks/{task_id}/identitylinks")
        return [link["group"] for link in links if link.get("group") and link.get("type") == "candidate"]

    async def claim(self, task_id: str, user_id: str | None) -> None:
        """Nhận việc cho user_id; None trả việc về nhóm. Người khác đã nhận thì Flowable trả 409."""
        await self._request("POST", f"/runtime/tasks/{task_id}", json={"action": "claim", "assignee": user_id})

    async def _post_again_if_concurrent(self, path: str, body: dict[str, Any]) -> Any:
        """POST làm phiên quy trình đi tiếp; bị hủy vì khóa lạc quan thì gọi lại theo ``RETRY_DELAYS_S``. Lỗi khác,
        kể cả 5xx khác, đi thẳng lên."""
        delays = list(RETRY_DELAYS_S)
        while True:
            try:
                return await self._request("POST", path, json=body)
            except FlowableError as exc:
                if not exc.concurrent or not delays:
                    raise
                delay = delays.pop(0)
                log.info(json.dumps({"event": "office.flowable.retry_concurrent", "path": path, "after_s": delay}))
            await asyncio.sleep(delay)

    async def complete(self, task_id: str, variables: dict[str, Any]) -> None:
        await self._post_again_if_concurrent(
            f"/runtime/tasks/{task_id}", {"action": "complete", "variables": _variables(variables)},
        )

    # --- việc giao ra ngoài (external worker) ----------------------------------------------------------

    async def acquire_jobs(self, topic: str, worker_id: str, *, count: int = 20,
                           lock: str = "PT2M") -> list[ExternalJob]:
        """Nhận và khóa tối đa count việc của topic; quá hạn khóa mà chưa xong thì Flowable giao lại."""
        rows = await self._request("POST", self._jobs, json={
            "topic": topic, "workerId": worker_id, "numberOfTasks": count, "lockDuration": lock,
        })
        return [
            ExternalJob(
                id=row["id"],
                process_instance_id=row.get("processInstanceId") or "",
                element_id=row.get("elementId") or "",
                variables={v["name"]: v.get("value") for v in row.get("variables") or []},
            )
            for row in rows or []
        ]

    async def complete_job(self, job_id: str, worker_id: str) -> None:
        await self._post_again_if_concurrent(f"{self._jobs}/{job_id}/complete", {"workerId": worker_id})

    async def fail_job(self, job_id: str, worker_id: str, message: str, retry_after: str = "PT1M") -> None:
        """Báo lỗi: Flowable bớt một lần thử và giao lại sau retry_after; hết lượt thử thì vào hàng việc chết."""
        await self._request("POST", f"{self._jobs}/{job_id}/fail", json={
            "workerId": worker_id, "errorMessage": message[:255], "retryTimeout": retry_after,
        })

    # --- quy trình của ứng dụng (apps/, #301) -----------------------------------------------------------

    async def deployments(self, name_like: str, *, size: int = 1) -> list[dict[str, Any]]:
        """Deployment có tên khớp mẫu LIKE, mới nhất trước."""
        data = await self._request("GET", "/repository/deployments", params={
            "nameLike": name_like, "sort": "deployTime", "order": "desc", "size": size,
        })
        return data["data"]

    async def deploy_zip(self, name: str, filename: str, content: bytes) -> dict[str, Any]:
        """Một deployment gồm mọi tệp trong zip (BPMN thành định nghĩa quy trình, tệp khác thành tài nguyên)."""
        return await self._request("POST", "/repository/deployments", params={"deploymentName": name},
                                   files={"file": (filename, content, "application/zip")})

    async def resource(self, deployment_id: str, name: str) -> bytes | None:
        """Nội dung một tài nguyên của deployment; None nếu không có."""
        path = f"/repository/deployments/{quote(deployment_id, safe='')}/resourcedata/{quote(name, safe='')}"
        try:
            r = await self._http.get(path)
        except httpx2.HTTPError as exc:
            raise FlowableError(f"Không gọi được Flowable: {exc}") from exc
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise FlowableError(f"Flowable trả {r.status_code}: {r.text[:300]}", r.status_code)
        return r.content

    async def definitions(self, **params: Any) -> list[dict[str, Any]]:
        """Định nghĩa quy trình theo bộ lọc của REST (key, keyLike, deploymentId, suspended…)."""
        data = await self._request("GET", "/repository/process-definitions", params={**params, "size": 1000})
        return data["data"]

    async def definition(self, definition_id: str) -> dict[str, Any] | None:
        try:
            return await self._request("GET", f"/repository/process-definitions/{quote(definition_id, safe='')}")
        except FlowableError as exc:
            if exc.status == 404:
                return None
            raise

    async def set_definition_state(self, definition_id: str, action: str) -> None:
        """action: suspend | activate, kèm các phiên đang chạy của định nghĩa đó."""
        await self._request("PUT", f"/repository/process-definitions/{quote(definition_id, safe='')}",
                            json={"action": action, "includeProcessInstances": True})

    async def start_definition(self, definition_id: str, variables: list[dict[str, Any]]) -> str:
        """Bắt đầu đúng phiên bản định nghĩa đã chọn; biến đã ghi kiểu (REST variable)."""
        data = await self._request("POST", "/runtime/process-instances",
                                   json={"processDefinitionId": definition_id, "variables": variables})
        return data["id"]

    async def query_tasks(self, query: dict[str, Any]) -> list[Task]:
        data = await self._request("POST", "/query/tasks", json={**query, "includeProcessVariables": True, "size": 500})
        return [_task(row) for row in data["data"]]

    async def historic_processes(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        data = await self._request("POST", "/query/historic-process-instances",
                                   json={**query, "includeProcessVariables": True, "size": 500})
        return data["data"]

    async def complete_typed(self, task_id: str, variables: list[dict[str, Any]]) -> None:
        """Như complete() nhưng biến đã ghi kiểu (REST variable): số, đúng/sai của form ứng dụng giữ nguyên kiểu."""
        await self._post_again_if_concurrent(f"/runtime/tasks/{task_id}", {"action": "complete",
                                                                           "variables": variables})
