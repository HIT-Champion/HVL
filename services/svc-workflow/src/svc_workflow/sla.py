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

"""Nhắc hạn và báo lãnh đạo (F2.3): thời hạn mỗi bước do timer trong BPMN đếm, svc-workflow chỉ gửi thông báo.

Mỗi việc trong ``processes/*.bpmn20.xml`` gắn một timer không ngắt việc, chu kỳ ``R2/${slaDuration}``
(``MOC_SLA_DURATION``: thật PT24H, demo PT1M). Timer bắn thì Flowable tạo một việc giao ra ngoài (external
worker, topic ``moc-sla``); vòng nền ở đây nhận việc đó, tìm việc người dùng đang mở của quy trình và:

  - quá một thời hạn → nhắc người phải làm (``task.overdue``)
  - quá hai thời hạn → báo thêm lãnh đạo của họ (``task.escalated``)

Việc đã xong trước khi timer bắn thì timer tự hủy; việc mở chưa tới hạn (của bước sau) thì bỏ qua. Mỗi lần nhắc
ghi một sự kiện vào dòng thời gian văn bản. Khóa chống trùng của thông báo làm cho việc nhận lại sau lỗi không gửi
hai lần.

Riêng hạn giải quyết của văn bản đến (ngày, do lãnh đạo ghi khi chỉ đạo) không nằm trong quy trình: vòng nền
``overdue_documents`` tìm văn bản đang xử lý đã qua hạn và báo người xử lý cùng lãnh đạo, mỗi văn bản một lần.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from .flowable import ExternalJob, FlowableClient, FlowableError, Task
from .hasura import BRIEF, OVERDUE_DOCUMENTS, READERS, Actor, HasuraClient
from .notify import Notifier, People, brief_of

log = logging.getLogger("svc_workflow")

TOPIC = "moc-sla"
WORKER = "svc-workflow"
ACTOR = "svc-workflow"
# timer không bao giờ bắn sớm; chừa sai lệch đồng hồ giữa Flowable và svc-workflow
TOLERANCE = timedelta(seconds=2)
VN = timezone(timedelta(hours=7))  # Việt Nam không đổi giờ theo mùa

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")

EVENT = """
mutation GhiSuKien($event: office_document_events_insert_input!) {
  insert_office_document_events_one(object: $event) { id }
}"""

SLA_EVENT = """
query SlaEvent($doc: uuid!, $kind: String!, $task: jsonb!) {
  office_document_events(where: {document_id: {_eq: $doc}, kind: {_eq: $kind}, data: {_contains: $task}}, limit: 1) {
    id
  }
}"""


def parse_duration(text: str) -> timedelta:
    """Thời hạn ISO 8601 dạng ngày, giờ, phút, giây (P1D, PT24H, PT1M, PT20S) — đúng phần Flowable hiểu như nhau."""
    m = _DURATION.match(text or "")
    if not m or text.endswith("T"):
        raise ValueError(f"thời hạn không hợp lệ: {text!r} (dạng ISO 8601, ví dụ PT24H, PT1M)")
    days, hours, minutes, seconds = m.groups()
    value = timedelta(days=int(days or 0), hours=int(hours or 0), minutes=int(minutes or 0),
                      seconds=float(seconds or 0))
    if value <= timedelta(0):
        raise ValueError(f"thời hạn phải lớn hơn 0: {text!r}")
    return value


def _event(doc_id: str, kind: str, **data: Any) -> dict[str, Any]:
    # không dùng khóa "task_id": sự kiện mang task_id nghĩa là dữ liệu của việc đó đã ghi (workflow._task_done)
    return {"document_id": doc_id, "kind": kind, "actor_id": ACTOR, "actor_kind": "service", "data": data}


class Deadlines:
    def __init__(self, hasura: HasuraClient, flowable: FlowableClient, notifier: Notifier, *,
                 sla_duration: str = "PT24H") -> None:
        self.hasura = hasura
        self.flowable = flowable
        self.notifier = notifier
        self.sla = parse_duration(sla_duration)

    # --- thời hạn từng bước (timer BPMN) --------------------------------------------------------------

    async def run_jobs(self) -> int:
        """Nhận các việc nhắc hạn Flowable đã tạo, xử lý từng việc → số việc đã nhận."""
        jobs = await self.flowable.acquire_jobs(TOPIC, WORKER)
        for job in jobs:
            # Một việc lỗi không chặn các việc khác. Báo Flowable cũng lỗi thì hết hạn khóa Flowable giao lại việc;
            # khóa chống trùng của thông báo làm cho lần chạy lại không gửi hai lần.
            try:
                await self.handle(job)
            except Exception as exc:  # noqa: BLE001
                log.warning(json.dumps({"event": "office.sla.job_failed", "job_id": job.id, "error": str(exc)},
                                       ensure_ascii=False))
                await self._report(self.flowable.fail_job(job.id, WORKER, str(exc)), job.id)
                continue
            await self._report(self.flowable.complete_job(job.id, WORKER), job.id)
        return len(jobs)

    async def _report(self, call: Awaitable[None], job_id: str) -> None:
        try:
            await call
        except FlowableError as exc:
            log.warning(json.dumps({"event": "office.sla.report_failed", "job_id": job_id, "error": str(exc)},
                                   ensure_ascii=False))

    async def handle(self, job: ExternalJob, now: datetime | None = None) -> None:
        tenant, doc_id = job.variables.get("tenantId"), job.variables.get("documentId")
        if not tenant or not doc_id:
            return
        # thời hạn đã đặt khi khởi chạy quy trình: đổi MOC_SLA_DURATION không đổi hạn của quy trình đang chạy
        given = job.variables.get("slaDuration")
        sla = parse_duration(given) if given else self.sla
        now = now or datetime.now(UTC)
        actor = Actor(ACTOR, uuid.UUID(tenant), "service", None)
        people: People | None = None
        for task in await self.flowable.process_tasks(job.process_instance_id):
            age = now - datetime.fromisoformat(task.created_at)
            if age + TOLERANCE < sla:
                continue  # việc của bước sau, chưa tới hạn: timer này thuộc bước đã xong
            people = people or await self.notifier.people(actor)
            await self._overdue(actor, task, doc_id, people, escalate=age + TOLERANCE >= 2 * sla)

    async def _overdue(self, actor: Actor, task: Task, doc_id: str, people: People, *, escalate: bool) -> None:
        brief = {k: v for k, v in (await self._brief(actor, doc_id)).items() if v}
        data = {"form_key": task.form_key, "task_id": task.id, **brief}
        readers = await self._readers(actor, doc_id)
        holders = await self.notifier.task_people(self.flowable, actor, task, people)
        if readers is not None:
            holders &= readers
        await self.notifier.send(actor, holders, "task.overdue", f"task:{task.id}:overdue", doc_id, data)
        await self._record(actor, doc_id, "office.task.overdue", task, holders)
        if not escalate:
            return
        groups = [] if task.assignee else await self.flowable.candidate_groups(task.id)
        leaders = people.leaders(str(actor.tenant_id), task.assignee, groups)
        if readers is not None:
            leaders &= readers
        holder = people.get(task.assignee or "")
        extra = {"assignee_id": task.assignee, "assignee_name": holder.full_name} if holder else {}
        await self.notifier.send(actor, leaders, "task.escalated", f"task:{task.id}:escalated", doc_id,
                                 {**data, **extra})
        await self._record(actor, doc_id, "office.task.escalated", task, leaders)

    async def _record(self, actor: Actor, doc_id: str, kind: str, task: Task, notified: set[str]) -> None:
        """Ghi lần nhắc vào dòng thời gian, một lần cho mỗi việc. Xét theo sự kiện đã có chứ không theo "vừa gửi":
        gửi xong mà ghi lỗi thì lần nhận lại việc không gửi nữa (khóa chống trùng) nhưng vẫn phải ghi."""
        if not notified:
            return
        found = await self.hasura.as_service(actor, SLA_EVENT, {
            "doc": doc_id, "kind": kind, "task": {"sla_task_id": task.id}})
        if found["office_document_events"]:
            return
        await self.hasura.as_service(actor, EVENT, {"event": _event(
            doc_id, kind, sla_task_id=task.id, form_key=task.form_key, notified=sorted(notified))})

    async def _brief(self, actor: Actor, doc_id: str) -> dict[str, Any]:
        return brief_of((await self.hasura.as_service(actor, BRIEF, {"id": doc_id}))["office_documents_by_pk"])

    async def _readers(self, actor: Actor, doc_id: str) -> set[str] | None:
        """Văn bản hạn chế (F3.7): chỉ nhắc người có tên trong danh sách xem và người tạo — trưởng phòng, lãnh đạo
        không có tên thì không được biết là có văn bản này, dù thông báo đã bỏ trích yếu. None: văn bản thường."""
        data = await self.hasura.as_service(actor, READERS, {"id": doc_id})
        doc = data["office_documents_by_pk"]
        if not doc or not doc.get("restricted"):
            return None
        return ({r["user_id"] for r in data["office_document_acl"]} | {doc.get("created_by")}) - {None}

    # --- hạn giải quyết văn bản đến -------------------------------------------------------------------

    async def overdue_documents(self, today: datetime | None = None) -> int:
        """Báo văn bản đến đã qua hạn giải quyết mà chưa xử lý xong → số văn bản đã báo."""
        day = (today or datetime.now(VN)).date().isoformat()
        rows = (await self.hasura.as_system(OVERDUE_DOCUMENTS, {"today": day}))["office_documents"]
        for row in rows:
            actor = Actor(ACTOR, uuid.UUID(row["tenant_id"]), "service", None)
            people = await self.notifier.people(actor)
            open_rows = row["assignments"]
            users = {a["user_id"] for a in open_rows if a["user_id"]}
            for dept in {a["department_id"] for a in open_rows if a["department_id"] and not a["user_id"]}:
                users |= people.with_role("manager", dept)
            users |= {a["assigned_by"] for a in open_rows if a["assigned_by"]} | people.with_role("director")
            data = {k: row[k] for k in ("summary", "symbol", "due_on") if row.get(k)}
            if row.get("restricted"):
                users &= await self._readers(actor, row["id"]) or set()
                data = {"due_on": row["due_on"], "restricted": True}
            sent = await self.notifier.send(actor, users & people.keys(), "document.overdue",
                                            f"doc:{row['id']}:overdue", row["id"], data)
            # ghi sự kiện cả khi không còn ai để báo: lần quét sau không lấy lại văn bản này
            await self.hasura.as_service(actor, EVENT, {"event": _event(
                row["id"], "office.document.overdue", due_on=row["due_on"], notified=sent)})
        return len(rows)
