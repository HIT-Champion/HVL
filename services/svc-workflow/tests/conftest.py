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

"""Bản giả của Flowable và Hasura cho test đơn vị — đủ hành vi để kiểm nghiệp vụ, không cần Docker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from svc_workflow.flowable import FlowableError, Task
from svc_workflow.hasura import Actor, HasuraError
from svc_workflow.workflow import Workflow

TENANT = uuid.UUID("c300d5bb-028f-44cc-ba10-7b5277a4225d")
OTHER = uuid.UUID("318da474-60d6-4a90-aa7f-928b31b8fc59")
DEPT_DT = uuid.UUID("5cc372aa-304d-4574-896c-4f3e781a2ce7")
DEPT_KTPM = uuid.UUID("7ee31261-b14c-4c42-8e1b-9a7e99935412")
DOC = "11111111-1111-4111-8111-111111111111"


def actor(role: str, user: str = "u-1", tenant: uuid.UUID = TENANT, dept: uuid.UUID | None = None) -> Actor:
    return Actor(user, tenant, role, dept, "req-1")


@dataclass
class FakeFlowable:
    tasks: dict[str, Task] = field(default_factory=dict)
    groups: dict[str, list[str]] = field(default_factory=dict)
    processes: dict[str, str] = field(default_factory=dict)
    claims: list[tuple[str, str | None]] = field(default_factory=list)
    completed: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    started: list[dict[str, Any]] = field(default_factory=list)
    down: bool = False
    claim_conflict: bool = False

    def add_task(self, task_id: str, form_key: str, *, assignee: str | None = None, groups: list[str] | None = None,
                 tenant: uuid.UUID = TENANT, urgency: str = "normal", created: str = "2026-10-18T09:00:00Z",
                 doc: str = DOC) -> None:
        self.tasks[task_id] = Task(task_id, form_key, form_key, assignee, f"p-{task_id}", created,
                                   {"tenantId": str(tenant), "documentId": doc, "urgency": urgency})
        self.groups[task_id] = groups or []

    async def aclose(self) -> None: ...

    async def deploy_dir(self, directory: str) -> list[str]:
        return []

    async def task(self, task_id: str) -> Task | None:
        if self.down:
            raise FlowableError("down")
        return self.tasks.get(task_id)

    async def candidate_groups(self, task_id: str) -> list[str]:
        return self.groups.get(task_id, [])

    async def claim(self, task_id: str, user_id: str | None) -> None:
        if self.claim_conflict and user_id:
            raise FlowableError("taken", 409)
        self.claims.append((task_id, user_id))

    async def complete(self, task_id: str, variables: dict[str, Any]) -> None:
        if self.down:
            raise FlowableError("down")
        self.completed.append((task_id, variables))
        self.tasks.pop(task_id, None)

    async def tasks_for(self, user_id: str, groups: list[str]) -> list[Task]:
        if self.down:
            raise FlowableError("down")
        return [t for t in self.tasks.values() if t.assignee == user_id
                or (t.assignee is None and set(self.groups[t.id]) & set(groups))]

    async def find_process(self, key: str, business_key: str) -> str | None:
        return self.processes.get(business_key)

    async def start_process(self, key: str, business_key: str, variables: dict[str, Any]) -> str:
        if self.down:
            raise FlowableError("down")
        self.started.append(variables)
        self.processes[business_key] = f"proc-{business_key}"
        return self.processes[business_key]


@dataclass
class FakeHasura:
    """Trả lời theo tên operation trong câu truy vấn; ghi lại mọi lệnh ghi."""

    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    departments: set[str] = field(default_factory=lambda: {str(DEPT_DT), str(DEPT_KTPM)})
    assignments: list[dict[str, Any]] = field(default_factory=list)
    events_with_task: set[str] = field(default_factory=set)
    document: dict[str, Any] = field(default_factory=lambda: {
        "id": DOC, "direction": "in", "status": "registered", "urgency": "khan", "due_on": None,
        "registered_at": "2026-10-18T08:00:00Z", "process_id": None,
    })
    writes: list[tuple[str, dict[str, Any], Actor]] = field(default_factory=list)
    fail_writes: str | None = None
    register_error: str | None = None

    async def as_service(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        op = query.split("(")[0].split()[1] if query.strip().startswith(("query", "mutation")) else ""
        if op == "Register":
            if self.register_error:
                raise HasuraError(self.register_error, "unexpected")
            if actor.tenant_id != TENANT:
                raise HasuraError("không có văn bản x", "data-exception")
            self.document.update(status="registered", register_number=7)
            return {"office_register_incoming": [{**self.document, "register_number": 7}]}
        if op == "Document":
            return {"office_documents_by_pk": self.document if actor.tenant_id == TENANT else None}
        if op == "OpenAssignments":
            return {"office_assignments": [a for a in self.assignments if a["status"] == "open"]}
        if op == "User":
            return {"core_users_by_pk": self.users.get(variables["id"])}
        if op == "Managers":
            dept = variables["dept"]
            return {
                "office_departments_by_pk": {"id": dept} if dept in self.departments else None,
                "core_users": [{"id": u} for u, row in self.users.items()
                               if row["department_id"] == dept and row["role"] == "manager" and row["enabled"]],
            }
        if op == "TaskDone":
            found = variables["task"]["task_id"] in self.events_with_task
            return {"office_document_events": [{"id": 1}] if found else []}
        # còn lại là mutation ghi
        if self.fail_writes:
            raise HasuraError(self.fail_writes, "constraint-violation")
        self.writes.append((op, variables, actor))
        if "event" in variables:
            self.events_with_task.add(variables["event"]["data"]["task_id"])
        return {}

    async def aclose(self) -> None: ...

    async def ping(self) -> bool:
        return True

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"office_documents": []}


@pytest.fixture
def flowable() -> FakeFlowable:
    return FakeFlowable()


@pytest.fixture
def hasura() -> FakeHasura:
    h = FakeHasura()
    h.users = {
        "u-manager-dt": {"id": "u-manager-dt", "department_id": str(DEPT_DT), "role": "manager", "enabled": True},
        "u-staff-dt": {"id": "u-staff-dt", "department_id": str(DEPT_DT), "role": "staff", "enabled": True},
        "u-staff-ktpm": {"id": "u-staff-ktpm", "department_id": str(DEPT_KTPM), "role": "staff", "enabled": True},
        "u-clerk": {"id": "u-clerk", "department_id": None, "role": "clerk", "enabled": True},
    }
    return h


@pytest.fixture
def workflow(hasura: FakeHasura, flowable: FakeFlowable) -> Workflow:
    return Workflow(hasura, flowable)  # type: ignore[arg-type]
