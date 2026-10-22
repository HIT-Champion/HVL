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

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from svc_workflow.dispatch import Dispatcher
from svc_workflow.files import DispatchFileError, FilesError
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
RECEIVED_BY_HAND = "44444444-4444-4444-8444-444444444444"  # văn bản đến bên nhận đã tiếp nhận tay trước liên thông
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)  # next_attempt_at = now() lúc trigger tạo dòng: đến hạn ngay
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
    # topic của từng việc giao ra ngoài (id việc → topic); không ghi thì là việc nhắc hạn moc-sla
    topics: dict[str, str] = field(default_factory=dict)
    acquired: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # (topic, count/lock) mỗi lần nhận
    jobs_done: list[str] = field(default_factory=list)
    jobs_failed: list[tuple[str, str]] = field(default_factory=list)
    jobs_retry: dict[str, str] = field(default_factory=dict)  # id việc → retry_after của lần báo lỗi cuối
    down: bool = False
    claim_conflict: bool = False
    gone_on_complete: bool = False  # lần gọi khác vừa hoàn thành việc: Flowable trả 404
    fail_complete: int = 0  # số lần hoàn thành việc tiếp theo lỗi (Flowable quá tải), các lệnh khác vẫn chạy
    deleted: list[str] = field(default_factory=list)
    slow: bool = False  # nhường lượt khi khởi chạy quy trình: hai lần gọi chen nhau như trên mạng thật

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
        if self.gone_on_complete:
            raise FlowableError("gone", 404)
        if self.fail_complete:
            self.fail_complete -= 1
            raise FlowableError("busy", 503)
        self.completed.append((task_id, variables))
        done = self.tasks.pop(task_id, None)
        if done is not None:
            self._follow(task_id, done.process_instance_id)

    async def process_tasks(self, process_instance_id: str) -> list[Task]:
        if self.down:
            raise FlowableError("down")
        return [t for t in self.tasks.values() if t.process_instance_id == process_instance_id]

    async def acquire_jobs(self, topic: str, worker_id: str, **kwargs: Any) -> list[ExternalJob]:
        """Như Flowable: chỉ giao việc đúng topic, việc của topic khác nằm lại chờ worker của nó."""
        self.acquired.append((topic, kwargs))
        jobs = [j for j in self.jobs if self.topics.get(j.id, "moc-sla") == topic]
        self.jobs = [j for j in self.jobs if j not in jobs]
        return jobs

    async def complete_job(self, job_id: str, worker_id: str) -> None:
        self.jobs_done.append(job_id)

    async def fail_job(self, job_id: str, worker_id: str, message: str, retry_after: str = "PT1M") -> None:
        self.jobs_failed.append((job_id, message))
        self.jobs_retry[job_id] = retry_after

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
        if self.slow:
            await asyncio.sleep(0)
        self.started.append(variables)
        n = sum(1 for v in self.started if v.get("documentId") == business_key)
        self.processes[business_key] = f"proc-{business_key}" + (f"-{n}" if n > 1 else "")
        self._follow(business_key, self.processes[business_key])
        return self.processes[business_key]

    async def delete_process(self, process_id: str, reason: str) -> None:
        self.deleted.append(process_id)
        for task_id in [t.id for t in self.tasks.values() if t.process_instance_id == process_id]:
            del self.tasks[task_id]


@dataclass
class FakeHasura:
    """Trả lời theo tên operation trong câu truy vấn; ghi lại mọi lệnh ghi."""

    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    departments: set[str] = field(default_factory=lambda: {str(DEPT_DT), str(DEPT_KTPM)})
    assignments: list[dict[str, Any]] = field(default_factory=list)
    events_with_task: set[str] = field(default_factory=set)
    saved_flows: dict[str, dict[str, Any]] = field(default_factory=dict)  # task_id → biến Flowable ghi cùng sự kiện
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
    # lần gọi khác gắn quy trình này vào văn bản ngay trước lần ghi của mình (giành process_id thua)
    rival_process: str | None = None
    # bản sao svc-workflow khác ghi xong việc ngay sau lần kiểm TaskDone của mình (một lần)
    done_elsewhere: bool = False
    # chỉ mục task_once chặn lần ghi mà không có sự kiện nào của văn bản này mang task_id (một lần)
    task_once_elsewhere: bool = False
    slow: bool = False  # nhường lượt ở mỗi lần gọi: hai lần gọi chen nhau như trên mạng thật
    # liên thông (F3.12): đơn vị trong hệ thống (id → tên); người dùng của thuê ước khác TENANT; dòng liên thông; văn
    # bản đến dựng ở bên nhận; dòng đã có bản sao tệp (svc-files ghi core.files bên nhận trước khi CSDL gắn tệp)
    units: dict[str, str] = field(default_factory=lambda: {str(TENANT): "Khoa Công nghệ thông tin",
                                                           str(OTHER): "Khoa Kinh tế"})
    tenant_users: dict[uuid.UUID, dict[str, dict[str, Any]]] = field(default_factory=dict)
    dispatches: dict[str, dict[str, Any]] = field(default_factory=dict)
    arrived: dict[str, dict[str, Any]] = field(default_factory=dict)
    copied: set[str] = field(default_factory=set)
    dispatch_events: list[dict[str, Any]] = field(default_factory=list)
    dispatch_calls: list[tuple[str, dict[str, Any], Actor | None]] = field(default_factory=list)
    already_received: bool = False  # bên nhận đã có văn bản đến trùng → duplicate
    deliver_rejects: str | None = None  # hàm CSDL bắt check_violation → failed + last_error
    deliver_error: str | None = None  # hàm CSDL ném lỗi (văn bản nguồn chưa phát hành…) → Hasura trả lỗi
    fail_dispatch_query: bool = False
    fail_notified: int = 0  # số lần DispatchNotified tiếp theo lỗi (dịch vụ dừng ngay sau khi báo)
    fail_fail: bool = False  # FailDispatch lỗi (Hasura không gọi được)
    # gợi ý giao việc (F4.3): văn bản đến đã có (id → dòng kèm assignments), dòng gợi ý đã lưu, sổ của tác tử, mọi lần
    # gọi bằng vai trò agent; lỗi CSDL khi lưu (mã ràng buộc/trigger) hoặc khi đọc
    past: dict[str, dict[str, Any]] = field(default_factory=dict)
    suggestions: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_audit: list[dict[str, Any]] = field(default_factory=list)
    agent_calls: list[tuple[str, dict[str, Any], uuid.UUID, str, str]] = field(default_factory=list)
    suggest_reads: list[str] = field(default_factory=list)
    save_error: str | None = None
    fail_suggest_reads: bool = False

    def add_past(self, doc_id: str, *, department: uuid.UUID | str | None = None, user: str | None = None,
                 registered_at: str = "2026-09-01T02:00:00Z", due_on: str | None = None,
                 lead_due: str | None = None, restricted: bool = False, direction: str = "in",
                 cancelled: bool = False) -> None:
        """Văn bản đến đã giao: một lần giao chủ trì (phòng, hoặc thẳng một người) — như _plan_direct ghi."""
        lead = {"department_id": str(department) if department else None, "user_id": user,
                "due_on": lead_due, "role": "lead", "parent_id": None,
                "status": "cancelled" if cancelled else "open", "assigned_at": registered_at}
        self.past[doc_id] = {"id": doc_id, "direction": direction, "restricted": restricted,
                             "registered_at": registered_at, "due_on": due_on,
                             "assignments": [lead] if department or user else []}

    def _sealed(self, doc_id: str) -> bool:
        doc = self.document if doc_id == DOC else self.past.get(doc_id)
        return bool(doc and (doc.get("restricted") or doc.get("direction") != "in"))

    async def _suggest_op(self, op: str, actor: Actor, variables: dict[str, Any]) -> dict[str, Any] | None:
        """Các truy vấn vai trò service của tác tử gợi ý giao việc; None nếu không phải."""
        if op not in {"GiaoViecVanBan", "GiaoViecLichSu", "GiaoViecNguoiChuTri", "GiaoViecDonVi"}:
            return None
        self.suggest_reads.append(op)
        if self.fail_suggest_reads:
            raise HasuraError("Không gọi được Hasura")
        assert actor.role == "service"
        if op == "GiaoViecVanBan":
            doc = {**self.document, "restricted": self.document.get("restricted", False)} \
                if variables["id"] == DOC else self.past.get(variables["id"])
            if doc is None or actor.tenant_id != TENANT:
                return {"office_documents_by_pk": None}
            return {"office_documents_by_pk": {k: doc.get(k) for k in
                                               ("id", "direction", "restricted", "registered_at", "due_on")}}
        if op == "GiaoViecLichSu":
            rows = []
            for doc_id in variables["ids"]:
                doc = self.past.get(doc_id)
                if doc is None or doc["direction"] != "in" or doc["restricted"]:
                    continue
                leads = sorted((a for a in doc["assignments"] if a["role"] == "lead" and a["parent_id"] is None
                                and a["status"] != "cancelled"), key=lambda a: a["assigned_at"])
                rows.append({"id": doc_id, "registered_at": doc["registered_at"], "due_on": doc["due_on"],
                             "assignments": [{k: a[k] for k in ("department_id", "user_id", "due_on")}
                                             for a in leads[:1]]})
            return {"office_documents": rows}
        if op == "GiaoViecNguoiChuTri":
            return {"core_users": [{"id": u, "department_id": self.users[u]["department_id"]}
                                   for u in variables["users"] if u in self.users]}
        return {"office_departments": [{"id": d} for d in sorted(self.departments)],
                "core_users": [{"department_id": r["department_id"]} for r in self.users.values()
                               if r["role"] == "manager" and r["enabled"] and r["department_id"]]}

    async def as_agent(self, tenant_id: uuid.UUID, agent_id: str, query: str, variables: dict[str, Any] | None = None,
                       *, request_id: str = "") -> dict[str, Any]:
        """Vai trò agent: chỉ đọc document_id của gợi ý; lưu gợi ý + dòng sổ cùng giao dịch, như trigger CSDL chặn."""
        variables = variables or {}
        op = query.split("(")[0].split()[1]
        self.agent_calls.append((op, variables, tenant_id, agent_id, request_id))
        if op == "GiaoViecDaGoiY":
            if self.fail_suggest_reads:
                raise HasuraError("Không gọi được Hasura")
            row = self.suggestions.get(variables["id"])
            return {"office_assignment_suggestions_by_pk": {"document_id": row["document_id"]} if row else None}
        assert op == "LuuGoiYGiaoViec", op
        row, entry = variables["o"], variables["e"]
        assert "tenant_id" not in row and "agent_id" not in row     # preset của vai trò agent đặt
        assert not {"actor_id", "actor_kind", "tenant_id"} & set(entry)
        if self.save_error:
            raise HasuraError(self.save_error, "constraint-violation")
        if row["document_id"] in self.suggestions:
            raise HasuraError('duplicate key value violates unique constraint "assignment_suggestions_pkey"',
                              "constraint-violation")
        if self._sealed(row["document_id"]) or any(self._sealed(e["document_id"]) for e in row["evidence"]):
            raise HasuraError("assignment_suggestions_sealed: văn bản hạn chế", "constraint-violation")
        self.suggestions[row["document_id"]] = {**row, "tenant_id": str(tenant_id), "agent_id": agent_id}
        self.agent_audit.append({**entry, "tenant_id": str(tenant_id), "actor_id": agent_id, "actor_kind": "agent"})
        return {"insert_office_assignment_suggestions_one": {"document_id": row["document_id"]},
                "insert_core_audit_log": {"affected_rows": 1}}

    def add_dispatch(self, to: str, doc: str = OUT) -> dict[str, Any]:
        """Như trigger documents_dispatch: một dòng pending mỗi (văn bản, đơn vị) — có rồi thì thôi."""
        for row in self.dispatches.values():
            if (row["document_id"], row["to_tenant_id"]) == (doc, to):
                return row
        row_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dispatch:{doc}:{to}"))
        self.dispatches[row_id] = {
            "id": row_id, "tenant_id": str(TENANT), "document_id": doc, "to_tenant_id": to, "status": "pending",
            "file_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"file:{row_id}")), "incoming_document_id": None,
            "source_verify_code": self.outgoing.get("verify_code"), "attempts": 0, "last_error": None,
            "next_attempt_at": LONG_AGO, "notified_at": None, "delivered_at": None,
        }
        return self.dispatches[row_id]

    def deliver_row(self, row: dict[str, Any]) -> None:
        """Như office.deliver_dispatch khi dòng còn pending: văn bản đến received, sự kiện hai bên, delivered."""
        if self.already_received:
            row.update(status="duplicate", incoming_document_id=RECEIVED_BY_HAND)
            self.dispatch_events.append({"document_id": row["document_id"], "actor_kind": "service",
                                         "kind": "office.document.dispatch_duplicate",
                                         "data": {"dispatch_id": row["id"]}})
            return
        if self.deliver_rejects:
            row.update(status="failed", last_error=self.deliver_rejects)
            return
        incoming = str(uuid.uuid5(uuid.NAMESPACE_URL, f"incoming:{row['id']}"))
        self.arrived[incoming] = {
            "id": incoming, "tenant_id": row["to_tenant_id"], "direction": "in", "status": "received",
            "summary": self.outgoing["summary"], "symbol": self.outgoing.get("symbol"),
            "urgency": self.outgoing.get("urgency"), "issuer_name": self.units[row["tenant_id"]],
            "source_id": row["document_id"], "restricted": False, "file_id": row["file_id"],
        }
        row.update(status="delivered", incoming_document_id=incoming, delivered_at="2026-10-21T09:00:00Z")
        self.dispatch_events += [
            {"document_id": incoming, "kind": "office.document.arrived", "actor_kind": "service",
             "data": {"dispatch_id": row["id"], "from_tenant_id": row["tenant_id"]}},
            {"document_id": row["document_id"], "kind": "office.document.dispatched", "actor_kind": "service",
             "data": {"dispatch_id": row["id"], "to_tenant_id": row["to_tenant_id"]}},
        ]

    async def _dispatch_op(self, op: str, actor: Actor | None, variables: dict[str, Any]) -> dict[str, Any] | None:
        """Các lệnh của liên thông; None nếu không phải."""
        if op not in {"PendingDispatches", "Dispatch", "DocumentDispatches", "Deliver", "DispatchRetry",
                      "DispatchNotified", "DispatchUnits", "FailDispatch"}:
            return None
        if self.slow:
            await asyncio.sleep(0)
        self.dispatch_calls.append((op, variables, actor))
        if op == "DispatchUnits":   # view chỉ có các đơn vị khác đơn vị của phiên
            return {"office_dispatch_units": [{"id": i, "name": n} for i, n in self.units.items()
                                              if i in variables["ids"] and i != str(actor.tenant_id)]}
        if op == "PendingDispatches":
            now = datetime.fromisoformat(variables["now"])
            return {"office_dispatches": [{"id": r["id"]} for r in self.dispatches.values()
                                          if (r["status"] == "pending" and r["next_attempt_at"] <= now)
                                          or (r["status"] in ("delivered", "duplicate") and r["notified_at"] is None)]}
        if op == "DocumentDispatches":
            if self.fail_dispatch_query:
                raise HasuraError("Không gọi được Hasura")
            return {"office_dispatches": [{"id": r["id"]} for r in self.dispatches.values()
                                          if r["document_id"] == variables["doc"] and r["status"] == "pending"]}
        row = self.dispatches.get(variables["id"])
        if op == "Dispatch":
            return {"office_dispatches_by_pk": {**row, "from_unit": {"name": self.units[row["tenant_id"]]}}
                    if row else None}
        assert row is not None and actor is not None and actor.role == "service"
        if op == "Deliver":
            if self.deliver_error:
                raise HasuraError(self.deliver_error, "unexpected")
            if row["to_tenant_id"] != str(actor.tenant_id):   # hàm chỉ thấy dòng gửi tới thuê ước của phiên
                raise HasuraError("không có dòng liên thông này", "unexpected")
            if row["status"] == "pending":
                if row["id"] not in self.copied:
                    raise HasuraError('insert or update on table "document_files" violates foreign key constraint',
                                      "constraint-violation")
                self.deliver_row(row)
            return {"office_deliver_dispatch": [{k: row[k] for k in ("id", "status", "incoming_document_id",
                                                                     "last_error")}]}
        assert str(actor.tenant_id) in (row["tenant_id"], row["to_tenant_id"])
        if op == "FailDispatch":   # office.fail_dispatch: chỉ dòng còn chờ
            if self.fail_fail:
                raise HasuraError("Không gọi được Hasura")
            if row["status"] != "pending":
                return {"office_fail_dispatch": []}
            row.update(status="failed", last_error=variables["reason"])
            return {"office_fail_dispatch": [{k: row[k] for k in ("id", "status", "last_error")}]}
        if op == "DispatchRetry":
            row.update(attempts=row["attempts"] + 1, last_error=variables["error"],
                       next_attempt_at=datetime.fromisoformat(variables["next"]))
        if op == "DispatchNotified":
            if self.fail_notified:
                self.fail_notified -= 1
                raise HasuraError("Không gọi được Hasura")
            row["notified_at"] = variables["now"]
        return {"update_office_dispatches_by_pk": {"id": row["id"]}}

    async def as_service(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        if self.slow:
            await asyncio.sleep(0)
        op = query.split("(")[0].split()[1] if query.strip().startswith(("query", "mutation")) else ""
        found = await self._dispatch_op(op, actor, variables)
        if found is not None:
            return found
        found = await self._suggest_op(op, actor, variables)
        if found is not None:
            return found
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
        if op == "ProcessOf":
            doc = {DOC: self.document, OUT: self.outgoing}.get(variables["id"])
            return {"office_documents_by_pk": {"process_id": doc["process_id"]} if doc else None}
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
            task_id = variables["task"]["task_id"]
            if self.done_elsewhere:
                self.done_elsewhere = False
                self.events_with_task.add(task_id)
                return {"office_document_events": []}
            if task_id not in self.events_with_task:
                return {"office_document_events": []}
            flow = self.saved_flows.get(task_id)
            data = {"task_id": task_id, **({"flow": flow} if flow else {})}
            return {"office_document_events": [{"id": 1, "data": data}]}
        if op == "SlaEvent":
            found = [w for w in self.writes if w[0] == "GhiSuKien" and w[1]["event"]["kind"] == variables["kind"]
                     and w[1]["event"]["data"].get("sla_task_id") == variables["task"]["sla_task_id"]]
            return {"office_document_events": [{"id": 1}] if found else []}
        if op == "People":
            pool = self.tenant_users.get(actor.tenant_id, self.users)
            return {"core_users": [{"id": u, "role": r["role"], "department_id": r["department_id"],
                                    "full_name": r.get("full_name", u)} for u, r in pool.items() if r["enabled"]]}
        if op == "Brief":
            doc = {DOC: self.document, OUT: self.outgoing}.get(variables["id"]) or self.arrived.get(variables["id"])
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
        data = (variables.get("event") or {}).get("data", {})
        task_id = data.get("task_id")
        if task_id in self.events_with_task or (task_id and self.task_once_elsewhere):
            # như chỉ mục duy nhất trong CSDL: cả giao dịch không ghi
            self.task_once_elsewhere = False
            raise HasuraError('duplicate key value violates unique constraint "document_events_task_once"',
                              "constraint-violation")
        self.writes.append((op, variables, actor))
        if task_id:
            self.events_with_task.add(task_id)
            if data.get("flow"):
                self.saved_flows[task_id] = data["flow"]
        if op == "Trinh":
            self.outgoing.update(variables["set"])
        if op == "XuLy":  # như CSDL: giao việc của người xử lý và của phòng đóng lại
            for a in self.assignments:
                if a["id"] in variables["ids"]:
                    a["status"] = "done"
        if op == "ClaimProcess":
            doc = {DOC: self.document, OUT: self.outgoing}[variables["id"]]
            if self.rival_process and not doc["process_id"]:
                doc["process_id"] = self.rival_process
            if doc["process_id"]:
                return {"update_office_documents": {"affected_rows": 0}}
            doc["process_id"] = variables["pid"]
            return {"update_office_documents": {"affected_rows": 1}}
        if op == "TiepNhan":
            self.received.append({**variables["doc"], "id": NEW})
            return {"insert_office_documents_one": {"id": NEW}}
        if op == "PhatHanh":    # như CSDL: issued, trigger documents_dispatch tạo dòng chờ cho mỗi đơn vị nhận
            self.outgoing["status"] = "issued"
            for to in self.outgoing.get("recipient_tenant_ids") or []:
                self.add_dispatch(to)
        return {}

    async def as_user(self, actor: Actor, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "query Visible" in query
        seen = actor.tenant_id == TENANT and actor.user_id in self.viewers
        return {"office_documents_by_pk": {"id": (variables or {})["id"]} if seen else None}

    async def aclose(self) -> None: ...

    async def ping(self) -> bool:
        return True

    async def as_system(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        op = query.split("(")[0].split()[1] if query.strip().startswith(("query", "mutation")) else ""
        found = await self._dispatch_op(op, None, variables or {})
        if found is not None:
            return found
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
    """svc-files giả: dựng PDF phát hành, chép bản phát hành sang đơn vị nhận (liên thông)."""

    calls: list[tuple[str, str]] = field(default_factory=list)
    down: bool = False
    copied: set[str] = field(default_factory=set)   # dùng chung với FakeHasura.copied (core.files bên nhận)
    dispatched: list[str] = field(default_factory=list)  # lần chép thành công
    dispatch_tries: int = 0
    dispatch_down: bool = False
    refuse: str | None = None  # mã 409 (422 nếu là mã của trạm quét) svc-files trả
    explode: bool = False  # lỗi không lường trước
    delay: float = 0.0
    hook: Callable[[str], None] | None = None  # chạy ngay khi được gọi: lần gọi khác chen vào giữa
    # văn bản tương tự (F4.3): câu trả lời chung hoặc theo từng văn bản đích, lỗi svc-files trả, độ trễ, các lần gọi
    similar_answer: dict[str, Any] = field(default_factory=lambda: {"hits": [], "terms": 0, "semantic": False,
                                                                   "duration_ms": 5})
    similar_answers: dict[str, dict[str, Any] | Exception] = field(default_factory=dict)
    similar_error: Exception | None = None
    similar_delay: float = 0.0
    similar_calls: list[tuple[uuid.UUID, str, int]] = field(default_factory=list)

    async def similar(self, tenant_id: uuid.UUID, document_id: str, *, limit: int = 15) -> dict[str, Any]:
        self.similar_calls.append((tenant_id, document_id, limit))
        await asyncio.sleep(self.similar_delay)
        if self.similar_error is not None:
            raise self.similar_error
        answer = self.similar_answers.get(document_id, self.similar_answer)
        if isinstance(answer, Exception):
            raise answer
        return {"document_id": document_id, **answer, "hits": answer["hits"][:limit]}

    async def dispatch_file(self, dispatch_id: str) -> dict[str, Any]:
        self.dispatch_tries += 1
        await asyncio.sleep(self.delay)
        if self.hook is not None:
            self.hook(dispatch_id)
        if self.explode:
            raise RuntimeError("bất ngờ")
        if self.dispatch_down:
            raise DispatchFileError("unavailable", "Kho tệp hoặc trạm quét chưa sẵn sàng, sẽ thử lại", 503)
        if self.refuse:
            status = 422 if self.refuse in ("infected", "unscannable") else 409
            raise DispatchFileError(self.refuse, f"svc-files từ chối: {self.refuse}", status)
        self.copied.add(dispatch_id)     # chép lại thì trả dòng đã có (200), không thêm bản sao
        self.dispatched.append(dispatch_id)
        return {"file_id": f"copy-{dispatch_id}", "sha256": "ab" * 32, "size_bytes": 4321}

    async def issue(self, actor: Actor, document_id: str) -> dict[str, Any]:
        if self.down:
            raise FilesError("svc-files trả 503", 503)
        self.calls.append((actor.user_id, document_id))
        return {"file_id": f"f-{len(self.calls)}", "sha256": "ab" * 32, "size_bytes": 4321}

    async def aclose(self) -> None: ...


class Clock:
    """Đồng hồ cho liên thông: lần thử lại hẹn theo giờ này, đối soát lấy dòng đến hạn theo giờ này."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def tick(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def files(hasura: FakeHasura) -> FakeFiles:
    return FakeFiles(copied=hasura.copied)


@pytest.fixture
def clock() -> Clock:
    return Clock()


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
def dispatcher(hasura: FakeHasura, files: FakeFiles, notifier: Notifier, clock: Clock) -> Dispatcher:
    return Dispatcher(hasura, files, notifier, clock=clock)  # type: ignore[arg-type]


@pytest.fixture
def workflow(hasura: FakeHasura, flowable: FakeFlowable, files: FakeFiles, notifier: Notifier,
             dispatcher: Dispatcher) -> Workflow:
    return Workflow(hasura, flowable, files, notifier=notifier,  # type: ignore[arg-type]
                    intake=FormSchema.load(SCHEMAS / "van-ban-den.json"), dispatcher=dispatcher)
