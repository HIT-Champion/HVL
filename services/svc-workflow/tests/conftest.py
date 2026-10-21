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
from pathlib import Path
from typing import Any

import pytest

from svc_workflow.files import FilesError
from svc_workflow.flowable import ExternalJob, FlowableError, Task
from svc_workflow.hasura import Actor, HasuraError
from svc_workflow.notify import Notifier
from svc_workflow.schemas import FormSchema
from svc_workflow.workflow import Workflow

TENANT = uuid.UUID("c300d5bb-028f-44cc-ba10-7b5277a4225d")
OTHER = uuid.UUID("318da474-60d6-4a90-aa7f-928b31b8fc59")
DEPT_DT = uuid.UUID("5cc372aa-304d-4574-896c-4f3e781a2ce7")
DEPT_KTPM = uuid.UUID("7ee31261-b14c-4c42-8e1b-9a7e99935412")
DOC = "11111111-1111-4111-8111-111111111111"
OUT = "22222222-2222-4222-8222-222222222222"
NEW = "33333333-3333-4333-8333-333333333333"
SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"   # schemas/ ở gốc repo, dùng chung với giao diện


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
    # việc Flowable tạo tiếp sau khi một việc xong / khi quy trình bắt đầu (id việc mới, form, tham số add_task)
    follow_ups: dict[str, list[tuple[str, str, dict[str, Any]]]] = field(default_factory=dict)
    jobs: list[ExternalJob] = field(default_factory=list)
    jobs_done: list[str] = field(default_factory=list)
    jobs_failed: list[tuple[str, str]] = field(default_factory=list)
    down: bool = False
    claim_conflict: bool = False

    def add_task(self, task_id: str, form_key: str, *, assignee: str | None = None, groups: list[str] | None = None,
                 tenant: uuid.UUID = TENANT, urgency: str = "normal", created: str = "2026-10-18T09:00:00Z",
                 doc: str = DOC, process: str | None = None) -> None:
        self.tasks[task_id] = Task(task_id, form_key, form_key, assignee, process or f"p-{task_id}", created,
                                   {"tenantId": str(tenant), "documentId": doc, "urgency": urgency})
        self.groups[task_id] = groups or []

    def then(self, after: str, task_id: str, form_key: str, **kwargs: Any) -> None:
        """Khi việc (hoặc văn bản vừa khởi chạy quy trình) `after` xong thì Flowable tạo việc task_id."""
        self.follow_ups.setdefault(after, []).append((task_id, form_key, kwargs))

    def _follow(self, after: str, process: str) -> None:
        for task_id, form_key, kwargs in self.follow_ups.pop(after, []):
            self.add_task(task_id, form_key, process=process, **kwargs)

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
        done = self.tasks.pop(task_id, None)
        if done is not None:
            self._follow(task_id, done.process_instance_id)

    async def process_tasks(self, process_instance_id: str) -> list[Task]:
        if self.down:
            raise FlowableError("down")
        return [t for t in self.tasks.values() if t.process_instance_id == process_instance_id]

    async def acquire_jobs(self, topic: str, worker_id: str, **kwargs: Any) -> list[ExternalJob]:
        jobs, self.jobs = self.jobs, []
        return jobs

    async def complete_job(self, job_id: str, worker_id: str) -> None:
        self.jobs_done.append(job_id)

    async def fail_job(self, job_id: str, worker_id: str, message: str, retry_after: str = "PT1M") -> None:
        self.jobs_failed.append((job_id, message))

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
        self._follow(business_key, self.processes[business_key])
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
    outgoing: dict[str, Any] = field(default_factory=lambda: {
        "id": OUT, "direction": "out", "status": "draft", "created_by": "u-staff-dt", "department_id": str(DEPT_DT),
        "signer_id": None, "process_id": None, "urgency": "normal", "summary": "Thông báo lịch họp giao ban",
        "body": "Khoa thông báo lịch họp.", "recipients": ["Các bộ môn"], "register_number": None, "symbol": None,
        "verify_code": None,
    })
    numbered: list[dict[str, Any]] = field(default_factory=list)
    writes: list[tuple[str, dict[str, Any], Actor]] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    overdue: list[dict[str, Any]] = field(default_factory=list)
    fail_writes: str | None = None
    fail_notify: bool = False
    register_error: str | None = None
    # tiếp nhận văn bản đến: loại văn bản có trong danh mục, tệp → người tải lên, văn bản đến đã có
    document_types: set[str] = field(default_factory=lambda: {"CV", "TB", "QĐ"})
    uploads: dict[str, str] = field(default_factory=dict)
    received: list[dict[str, Any]] = field(default_factory=list)
    lookups: list[dict[str, Any]] = field(default_factory=list)
    # văn bản hạn chế (F3.7): tệp tải lên ở chế độ hạn chế; người đọc được văn bản (as_user); lỗi khi cấp quyền xem
    sealed: set[str] = field(default_factory=set)
    viewers: set[str] = field(default_factory=set)
    fail_share: bool = False

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
        if op == "Outgoing":
            return {"office_documents_by_pk": self.outgoing if actor.tenant_id == TENANT else None}
        if op == "NumberOutgoing":
            self.numbered.append(variables)
            code = self.outgoing["verify_code"] or variables["code"]
            self.outgoing.update(register_number=5, symbol="05/TB-CNTT", verify_code=code)
            return {"office_number_outgoing": [{"id": OUT, "register_number": 5, "symbol": "05/TB-CNTT",
                                                "verify_code": code}]}
        if op == "Document":
            return {"office_documents_by_pk": self.document if actor.tenant_id == TENANT else None}
        if op == "IntakeLookup":
            self.lookups.append(variables)
            same = [d for d in self.received if (d["symbol"], d["issuer_name"].lower(), d["issued_on"])
                    == (variables["symbol"], variables["issuer"].lower(), variables["issued"])]
            return {
                "office_document_types_by_pk": {"code": variables["type"]}
                if variables["type"] in self.document_types else None,
                "core_files": [{"id": f, "encrypted": f in self.sealed} for f in variables["files"]
                               if self.uploads.get(f) == variables["user"]],
                "office_documents": [{"id": d["id"]} for d in same[:1]],
            }
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
        if op == "SlaEvent":
            found = [w for w in self.writes if w[0] == "GhiSuKien" and w[1]["event"]["kind"] == variables["kind"]
                     and w[1]["event"]["data"].get("sla_task_id") == variables["task"]["sla_task_id"]]
            return {"office_document_events": [{"id": 1}] if found else []}
        if op == "People":
            return {"core_users": [{"id": u, "role": r["role"], "department_id": r["department_id"],
                                    "full_name": r.get("full_name", u)} for u, r in self.users.items() if r["enabled"]]}
        if op == "Brief":
            doc = {DOC: self.document, OUT: self.outgoing}.get(variables["id"])
            return {"office_documents_by_pk": {"summary": "Công văn về chuyển đổi số", "symbol": None,
                                               "created_by": None, "signer_id": None, **doc} if doc else None}
        if op == "Readers":  # danh sách xem của văn bản hạn chế: dùng chung tập viewers
            doc = {DOC: self.document, OUT: self.outgoing}.get(variables["id"])
            return {"office_documents_by_pk": {"restricted": doc.get("restricted", False),
                                               "created_by": doc.get("created_by")} if doc else None,
                    "office_document_acl": [{"user_id": u} for u in sorted(self.viewers)]}
        if op == "Notify":
            if self.fail_notify:
                raise HasuraError("Không gọi được Hasura")
            created = []
            for row in variables["rows"]:
                if any(n["user_id"] == row["user_id"] and n["key"] == row["key"] for n in self.notifications):
                    continue
                self.notifications.append({**row, "tenant_id": actor.tenant_id})
                created.append({"id": len(self.notifications), "created_at": "2026-10-19T09:00:00Z",
                                **{k: row[k] for k in ("user_id", "kind", "document_id", "data")}})
            return {"insert_core_notifications": {"returning": created}}
        # còn lại là mutation ghi
        if op == "ChoXem" and self.fail_share:
            raise HasuraError("Không gọi được Hasura")
        if self.fail_writes:
            raise HasuraError(self.fail_writes, "constraint-violation")
        self.writes.append((op, variables, actor))
        if "task_id" in (variables.get("event") or {}).get("data", {}):
            self.events_with_task.add(variables["event"]["data"]["task_id"])
        if op == "TiepNhan":
            self.received.append({**variables["doc"], "id": NEW})
            return {"insert_office_documents_one": {"id": NEW}}
        return {}

    async def as_user(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "query Visible" in query
        seen = actor.tenant_id == TENANT and actor.user_id in self.viewers
        return {"office_documents_by_pk": {"id": (variables or {})["id"]} if seen else None}

    async def aclose(self) -> None: ...

    async def ping(self) -> bool:
        return True

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if "OverdueDocuments" in query:
            return {"office_documents": self.overdue}
        return {"office_documents": []}

    def sent(self, kind: str | None = None) -> dict[str, set[str]]:
        """Thông báo đã ghi: loại → người nhận (lọc một loại nếu có)."""
        out: dict[str, set[str]] = {}
        for n in self.notifications:
            if kind is None or n["kind"] == kind:
                out.setdefault(n["kind"], set()).add(n["user_id"])
        return out


@dataclass
class FakeFiles:
    """svc-files giả: dựng PDF phát hành."""

    calls: list[tuple[str, str]] = field(default_factory=list)
    down: bool = False

    async def issue(self, actor: Actor, document_id: str) -> dict[str, Any]:
        if self.down:
            raise FilesError("svc-files trả 503", 503)
        self.calls.append((actor.user_id, document_id))
        return {"file_id": f"f-{len(self.calls)}", "sha256": "ab" * 32, "size_bytes": 4321}

    async def aclose(self) -> None: ...


@pytest.fixture
def files() -> FakeFiles:
    return FakeFiles()


@pytest.fixture
def flowable() -> FakeFlowable:
    return FakeFlowable()


@pytest.fixture
def hasura() -> FakeHasura:
    h = FakeHasura()
    h.users = {
        "u-manager-dt": {"id": "u-manager-dt", "department_id": str(DEPT_DT), "role": "manager", "enabled": True,
                         "full_name": "Phạm Thị Thu"},
        "u-staff-dt": {"id": "u-staff-dt", "department_id": str(DEPT_DT), "role": "staff", "enabled": True,
                       "full_name": "Nguyễn Văn An"},
        "u-staff-ktpm": {"id": "u-staff-ktpm", "department_id": str(DEPT_KTPM), "role": "staff", "enabled": True},
        "u-clerk": {"id": "u-clerk", "department_id": None, "role": "clerk", "enabled": True},
        "u-director": {"id": "u-director", "department_id": None, "role": "director", "enabled": True},
    }
    return h


@pytest.fixture
def notifier(hasura: FakeHasura) -> Notifier:
    return Notifier(hasura)  # type: ignore[arg-type]


@pytest.fixture
def workflow(hasura: FakeHasura, flowable: FakeFlowable, files: FakeFiles, notifier: Notifier) -> Workflow:
    return Workflow(hasura, flowable, files, notifier=notifier,  # type: ignore[arg-type]
                    intake=FormSchema.load(SCHEMAS / "van-ban-den.json"))
