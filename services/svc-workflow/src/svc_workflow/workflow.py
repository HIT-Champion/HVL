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

"""Nghiệp vụ của các Action: vào sổ, hộp việc, hoàn thành việc, đối soát.

Thứ tự ghi khi hoàn thành một việc: kiểm quyền và dữ liệu → nhận việc (claim) trong Flowable → ghi
PostgreSQL trong một giao dịch, kèm sự kiện mang ``task_id`` → hoàn thành việc trong Flowable. Gọi lại sau
lỗi mạng: sự kiện có ``task_id`` đã có thì bỏ qua bước ghi, chỉ hoàn thành nốt trong Flowable — không giao
việc hai lần (docs/mo-hinh-du-lieu.md §4.1, "idempotent theo taskId").
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError

from .flowable import FlowableClient, FlowableError, Task
from .forms import FORMS, ChiDao, Note, PhanCong, XuLy
from .hasura import (
    DOCUMENT,
    OPEN_ASSIGNMENTS,
    REGISTER_INCOMING,
    SET_PROCESS,
    TASK_DONE,
    UNLINKED,
    USER,
    Actor,
    HasuraClient,
    HasuraError,
)

PROCESS_IN = "van-ban-den"
URGENCY_RANK = {"hoa_toc": 3, "thuong_khan": 2, "khan": 1, "normal": 0}
SYSTEM_ACTOR = "svc-workflow"

log = logging.getLogger("svc_workflow")


class WorkflowError(Exception):
    """Lỗi trả về cho người dùng qua Hasura: mã máy đọc + câu tiếng Việt."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# Tên ràng buộc trong CSDL → câu cho người dùng (db/README.md: "Đặt tên cho ràng buộc check")
CONSTRAINT_MESSAGES = {
    "documents_due_after_registered": "Hạn giải quyết không được trước ngày vào sổ",
    "documents_in_identity": "Văn bản đến phải có số ký hiệu, cơ quan ban hành và ngày ban hành",
    "assignments_one_lead": "Văn bản đã có nơi chủ trì",
}


def _db_error(exc: HasuraError) -> WorkflowError:
    text = str(exc)
    for name, message in CONSTRAINT_MESSAGES.items():
        if name in text:
            return WorkflowError("constraint", message, 409)
    if exc.code in {"constraint-violation", "data-exception"}:
        return WorkflowError("rejected", text, 409)
    return WorkflowError("database_unavailable", "Chưa ghi được vào cơ sở dữ liệu, thử lại sau", 503)


@dataclass(frozen=True)
class Plan:
    """Việc cần ghi khi hoàn thành một task: một mutation (một giao dịch) và biến cho Flowable."""

    mutation: str
    variables: dict[str, Any]
    flow: dict[str, Any]


DIRECT = """
mutation ChiDao($doc: uuid!, $due: date, $lead: office_assignments_insert_input!,
                $supports: [office_assignments_insert_input!]!, $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: "in_progress", due_on: $due}) { id }
  insert_office_assignments_one(object: $lead) { id }
  insert_office_assignments(objects: $supports) { affected_rows }
  insert_office_document_events_one(object: $event) { id }
}"""

FILE = """
mutation Luu($doc: uuid!, $event: office_document_events_insert_input!) {
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: "done"}) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

ASSIGN = """
mutation PhanCong($child: office_assignments_insert_input!, $event: office_document_events_insert_input!) {
  insert_office_assignments_one(object: $child) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

PROCESSED = """
mutation XuLy($ids: [uuid!]!, $note: String!, $now: timestamptz!, $doc: uuid!,
              $event: office_document_events_insert_input!) {
  update_office_assignments(where: {id: {_in: $ids}}, _set: {status: "done", result_note: $note, completed_at: $now}) {
    affected_rows
  }
  update_office_documents_by_pk(pk_columns: {id: $doc}, _set: {status: "done"}) { id }
  insert_office_document_events_one(object: $event) { id }
}"""

DEPARTMENT_MANAGERS = """
query Managers($dept: uuid!) {
  office_departments_by_pk(id: $dept) { id }
  core_users(where: {department_id: {_eq: $dept}, role: {_eq: "manager"}, enabled: {_eq: true}}) { id }
}"""


class Workflow:
    def __init__(self, hasura: HasuraClient, flowable: FlowableClient, *, sla_duration: str = "PT24H") -> None:
        self.hasura = hasura
        self.flowable = flowable
        self.sla_duration = sla_duration

    # --- vào sổ ---------------------------------------------------------------------------------------

    async def register_incoming(self, actor: Actor, document_id: str) -> dict[str, Any]:
        try:
            uuid.UUID(document_id)
        except ValueError:
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404) from None
        try:
            data = await self.hasura.as_service(actor, REGISTER_INCOMING, {"id": document_id})
        except HasuraError as exc:
            if "không có văn bản" in str(exc):
                raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404) from exc
            if "vào sổ" in str(exc):
                raise WorkflowError("wrong_status", str(exc), 409) from exc
            raise _db_error(exc) from exc
        doc = data["office_register_incoming"][0]
        if not doc["process_id"]:
            try:
                await self._attach_process(actor, doc)
            except (FlowableError, HasuraError) as exc:
                # Số đến đã cấp và đã ghi; job đối soát sẽ khởi chạy quy trình sau
                log.warning(json.dumps({"event": "office.process.start_failed", "document_id": doc["id"],
                                        "error": str(exc)}, ensure_ascii=False))
        return {"document_id": doc["id"], "register_number": doc["register_number"]}

    async def _attach_process(self, actor: Actor, doc: dict[str, Any]) -> str:
        pid = await self.flowable.find_process(PROCESS_IN, doc["id"])
        if pid is None:
            pid = await self.flowable.start_process(PROCESS_IN, doc["id"], {
                "tenantId": str(actor.tenant_id),
                "documentId": doc["id"],
                "urgency": doc.get("urgency") or "normal",
                "dueOn": doc.get("due_on") or "",
                "slaDuration": self.sla_duration,
                "leadDepartmentId": "",
                "handlerId": "",
            })
        await self.hasura.as_service(actor, SET_PROCESS, {"id": doc["id"], "pid": pid})
        return pid

    async def reconcile(self) -> int:
        """Gắn quy trình cho văn bản đã vào sổ mà chưa có (lỗi giữa chừng ở registerIncoming)."""
        rows = (await self.hasura.as_system(UNLINKED))["office_documents"]
        for row in rows:
            actor = Actor(SYSTEM_ACTOR, uuid.UUID(row["tenant_id"]), "service", None)
            await self._attach_process(actor, row)
        return len(rows)

    # --- hộp việc -------------------------------------------------------------------------------------

    async def my_tasks(self, actor: Actor) -> list[dict[str, Any]]:
        try:
            tasks = await self.flowable.tasks_for(actor.user_id, actor.groups)
        except FlowableError as exc:
            raise WorkflowError("workflow_unavailable", "Chưa lấy được hộp việc, thử lại sau", 503) from exc
        mine = [t for t in tasks if t.variables.get("tenantId") == str(actor.tenant_id)]
        mine.sort(key=lambda t: t.created_at)
        mine.sort(key=lambda t: URGENCY_RANK.get(t.variables.get("urgency") or "normal", 0), reverse=True)
        return [
            {
                "id": t.id,
                "name": t.name,
                "form_key": t.form_key,
                "document_id": t.variables.get("documentId"),
                "created_at": t.created_at,
                "due_on": t.variables.get("dueOn") or None,
                "urgency": t.variables.get("urgency") or "normal",
            }
            for t in mine
            if t.variables.get("documentId")
        ]

    # --- hoàn thành việc --------------------------------------------------------------------------------

    async def complete_task(self, actor: Actor, task_id: str, outcome: str, data: dict[str, Any] | None) -> dict:
        try:
            task = await self.flowable.task(task_id)
        except FlowableError as exc:
            raise WorkflowError("workflow_unavailable", "Chưa gọi được động cơ quy trình, thử lại sau", 503) from exc
        if task is None or task.variables.get("tenantId") != str(actor.tenant_id):
            raise WorkflowError("task_not_found", "Việc không còn — có thể đã có người xử lý", 404)
        await self._check_owner(actor, task)

        outcomes = FORMS.get(task.form_key)
        if outcomes is None:
            raise WorkflowError("unknown_form", f"Không xử lý được việc loại {task.form_key}", 400)
        model = outcomes.get(outcome)
        if model is None:
            raise WorkflowError("bad_outcome", f"Kết quả không hợp lệ: {outcome}", 400)
        try:
            form = model.model_validate(data or {})
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise WorkflowError("invalid_data", f"Dữ liệu không hợp lệ{' (' + where + ')' if where else ''}: "
                                                f"{first['msg']}", 400) from exc

        doc_id = task.variables["documentId"]
        plan = await self._plan(actor, task, doc_id, outcome, form)

        claimed = False
        if not task.assignee:
            try:
                await self.flowable.claim(task_id, actor.user_id)
            except FlowableError as exc:
                if exc.status == 409:
                    raise WorkflowError("task_taken", "Việc này vừa có người khác nhận", 409) from exc
                raise WorkflowError("workflow_unavailable", "Chưa gọi được động cơ quy trình", 503) from exc
            claimed = True
        try:
            done = await self.hasura.as_service(actor, TASK_DONE, {"doc": doc_id, "task": {"task_id": task_id}})
            if not done["office_document_events"]:
                await self.hasura.as_service(actor, plan.mutation, plan.variables)
        except HasuraError as exc:
            if claimed:
                await self._unclaim(task_id)
            raise _db_error(exc) from exc
        try:
            await self.flowable.complete(task_id, plan.flow)
        except FlowableError as exc:
            # Dữ liệu đã ghi; người dùng bấm lại sẽ chỉ hoàn thành nốt trong Flowable
            raise WorkflowError("workflow_unavailable", "Đã lưu, nhưng chưa chuyển được bước tiếp — bấm lại", 503) from exc
        return {"task_id": task_id, "document_id": doc_id}

    async def _check_owner(self, actor: Actor, task: Task) -> None:
        if task.assignee:
            if task.assignee != actor.user_id:
                raise WorkflowError("not_your_task", "Việc này không giao cho bạn", 403)
            return
        groups = await self.flowable.candidate_groups(task.id)
        if not set(groups) & set(actor.groups):
            raise WorkflowError("not_your_task", "Việc này không giao cho bạn", 403)

    async def _unclaim(self, task_id: str) -> None:
        try:
            await self.flowable.claim(task_id, None)
        except FlowableError:
            log.warning(json.dumps({"event": "office.task.unclaim_failed", "task_id": task_id}))

    async def _document(self, actor: Actor, doc_id: str) -> dict[str, Any]:
        doc = (await self.hasura.as_service(actor, DOCUMENT, {"id": doc_id}))["office_documents_by_pk"]
        if doc is None:
            raise WorkflowError("document_not_found", "Không tìm thấy văn bản", 404)
        return doc

    async def _open_assignments(self, actor: Actor, doc_id: str) -> list[dict[str, Any]]:
        return (await self.hasura.as_service(actor, OPEN_ASSIGNMENTS, {"doc": doc_id}))["office_assignments"]

    async def _user(self, actor: Actor, user_id: str) -> dict[str, Any] | None:
        user = (await self.hasura.as_service(actor, USER, {"id": user_id}))["core_users_by_pk"]
        return user if user and user["enabled"] else None

    def _event(self, actor: Actor, doc_id: str, kind: str, task_id: str, note: str | None, **data: Any) -> dict:
        return {
            "document_id": doc_id,
            "kind": kind,
            "actor_id": actor.user_id,
            "actor_kind": "user",
            "note": note,
            "data": {"task_id": task_id, **{k: v for k, v in data.items() if v not in (None, [], "")}},
        }

    async def _plan(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        try:
            return await self._plan_unchecked(actor, task, doc_id, outcome, form)
        except HasuraError as exc:
            raise _db_error(exc) from exc

    async def _plan_unchecked(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        if isinstance(form, ChiDao):
            return await self._plan_direct(actor, task, doc_id, form)
        if task.form_key == "vbden.chiDao" and isinstance(form, Note):
            event = self._event(actor, doc_id, "office.document.filed", task.id, form.note)
            return Plan(FILE, {"doc": doc_id, "event": event}, {"outcome": "file"})
        if task.form_key == "vbden.phanCong":
            return await self._plan_assign(actor, task, doc_id, outcome, form)
        if isinstance(form, XuLy):
            return await self._plan_processed(actor, task, doc_id, form)
        raise WorkflowError("unknown_form", f"Không xử lý được việc loại {task.form_key}", 400)

    async def _plan_direct(self, actor: Actor, task: Task, doc_id: str, form: ChiDao) -> Plan:
        doc = await self._document(actor, doc_id)
        if form.due_on and form.due_on < date.today():
            raise WorkflowError("invalid_data", "Hạn giải quyết đã qua", 400)
        due = form.due_on.isoformat() if form.due_on else doc["due_on"]
        if form.lead_user_id:
            user = await self._user(actor, form.lead_user_id)
            if user is None or user["role"] not in {"staff", "manager"}:
                raise WorkflowError("invalid_data", "Người chủ trì không thuộc đơn vị hoặc không xử lý văn bản", 400)
        else:
            found = await self.hasura.as_service(actor, DEPARTMENT_MANAGERS, {"dept": str(form.lead_department_id)})
            if found["office_departments_by_pk"] is None:
                raise WorkflowError("invalid_data", "Phòng chủ trì không thuộc đơn vị", 400)
            if not found["core_users"]:
                raise WorkflowError("no_manager", "Phòng chủ trì chưa có lãnh đạo phòng để phân công", 409)
        for dept in form.supports:
            found = await self.hasura.as_service(actor, DEPARTMENT_MANAGERS, {"dept": str(dept)})
            if found["office_departments_by_pk"] is None:
                raise WorkflowError("invalid_data", "Phòng phối hợp không thuộc đơn vị", 400)

        base = {"document_id": doc_id, "instruction": form.instruction, "due_on": due, "assigned_by": actor.user_id}
        lead = {**base, "role": "lead"}
        if form.lead_user_id:
            lead["user_id"] = form.lead_user_id
        else:
            lead["department_id"] = str(form.lead_department_id)
        supports = [{**base, "role": "support", "department_id": str(d)} for d in form.supports]
        event = self._event(
            actor, doc_id, "office.document.directed", task.id, form.instruction,
            lead_department_id=str(form.lead_department_id) if form.lead_department_id else None,
            lead_user_id=form.lead_user_id, supports=[str(d) for d in form.supports], due_on=due,
        )
        return Plan(
            DIRECT,
            {"doc": doc_id, "due": due, "lead": lead, "supports": supports, "event": event},
            {"outcome": "direct", "leadDepartmentId": str(form.lead_department_id or ""),
             "handlerId": form.lead_user_id or "", "dueOn": due or ""},
        )

    async def _plan_assign(self, actor: Actor, task: Task, doc_id: str, outcome: str, form: Any) -> Plan:
        parent = next(
            (a for a in await self._open_assignments(actor, doc_id)
             if a["parent_id"] is None and a["role"] == "lead" and a["department_id"] == str(actor.department_id)),
            None,
        )
        if parent is None:
            raise WorkflowError("no_assignment", "Phòng của bạn không chủ trì văn bản này", 409)
        if outcome == "assign":
            assert isinstance(form, PhanCong)
            user = await self._user(actor, form.user_id)
            if user is None or user["department_id"] != str(actor.department_id) or user["role"] not in {"staff", "manager"}:
                raise WorkflowError("invalid_data", "Người được giao phải thuộc phòng của bạn", 400)
            handler = form.user_id
        else:
            handler = actor.user_id
        child = {
            "document_id": doc_id, "parent_id": parent["id"], "user_id": handler, "role": "lead",
            "instruction": form.note, "due_on": parent["due_on"], "assigned_by": actor.user_id,
        }
        event = self._event(actor, doc_id, "office.document.assigned", task.id, form.note, user_id=handler)
        return Plan(ASSIGN, {"child": child, "event": event}, {"outcome": outcome, "handlerId": handler})

    async def _plan_processed(self, actor: Actor, task: Task, doc_id: str, form: XuLy) -> Plan:
        open_rows = await self._open_assignments(actor, doc_id)
        mine = next((a for a in open_rows if a["user_id"] == actor.user_id and a["role"] == "lead"), None)
        if mine is None:
            raise WorkflowError("no_assignment", "Bạn không có việc mở với văn bản này", 409)
        ids = [mine["id"]] + ([mine["parent_id"]] if mine["parent_id"] else [])
        event = self._event(actor, doc_id, "office.document.processed", task.id, form.result_note)
        return Plan(
            PROCESSED,
            {"ids": ids, "note": form.result_note, "now": datetime.now(UTC).isoformat(), "doc": doc_id,
             "event": event},
            {"outcome": "done"},
        )
