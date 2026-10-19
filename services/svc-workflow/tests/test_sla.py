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

"""Nhắc hạn (timer BPMN → external worker) và báo văn bản đến quá hạn giải quyết."""

from __future__ import annotations

import asyncio
import pathlib
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import pytest

from conftest import DEPT_DT, DOC, OUT, TENANT
from svc_workflow.config import ConfigError, Settings
from svc_workflow.flowable import ExternalJob, FlowableError
from svc_workflow.hasura import HasuraError
from svc_workflow.sla import Deadlines, parse_duration

DIRECTOR_GROUP = f"t:{TENANT}:director"
MANAGER_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"
CREATED = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
PROCESSES = pathlib.Path(__file__).resolve().parents[3] / "processes"
BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
FLOWABLE = "{http://flowable.org/bpmn}"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def deadlines(hasura, flowable, notifier) -> Deadlines:
    return Deadlines(hasura, flowable, notifier, sla_duration="PT1M")  # type: ignore[arg-type]


def job(process: str = "p1", doc: str = DOC, **variables) -> ExternalJob:
    return ExternalJob("j1", process, "nhacHan",
                       {"tenantId": str(TENANT), "documentId": doc, "slaDuration": "PT1M", **variables})


def at(minutes: float) -> datetime:
    return CREATED + timedelta(minutes=minutes)


def events(hasura, kind):
    return [w[1]["event"] for w in hasura.writes if w[0] == "GhiSuKien" and w[1]["event"]["kind"] == kind]


@pytest.mark.parametrize(("text", "seconds"), [("PT24H", 86400), ("PT1M", 60), ("PT20S", 20), ("P1DT2H", 93600)])
def test_parse_duration(text, seconds):
    assert parse_duration(text).total_seconds() == seconds


@pytest.mark.parametrize("text", ["", "P", "PT", "PT0S", "P1M", "P1Y", "24h", "P1DT"])
def test_reject_ambiguous_or_empty_duration(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_bad_sla_stops_the_service_at_startup():
    env = {"HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": "a", "FLOWABLE_ADMIN_PASSWORD": "f",
           "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_SLA_DURATION": "1 ngày"}
    with pytest.raises(ConfigError, match="MOC_SLA_DURATION"):
        Settings.from_env(env)


def test_first_deadline_reminds_whoever_must_act(deadlines, hasura, flowable):
    flowable.add_task("t1", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT, process="p1",
                      created=CREATED.isoformat())
    run(deadlines.handle(job(doc=OUT), now=at(1.1)))
    assert hasura.sent() == {"task.overdue": {"u-manager-dt"}}
    (event,) = events(hasura, "office.task.overdue")
    assert event["actor_kind"] == "service" and event["data"]["sla_task_id"] == "t1"
    assert "task_id" not in event["data"]   # không lẫn với sự kiện "việc đã ghi" (workflow._task_done)


def test_second_deadline_also_tells_the_leader(deadlines, hasura, flowable):
    flowable.add_task("t1", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT, process="p1",
                      created=CREATED.isoformat())
    run(deadlines.handle(job(doc=OUT), now=at(1.1)))
    run(deadlines.handle(job(doc=OUT), now=at(2.05)))
    assert hasura.sent() == {"task.overdue": {"u-manager-dt"}, "task.escalated": {"u-director"}}
    assert len(events(hasura, "office.task.overdue")) == 1 and len(events(hasura, "office.task.escalated")) == 1


def test_timeline_entry_is_written_on_retry_after_a_failed_write(deadlines, hasura, flowable):
    flowable.add_task("t1", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT, process="p1",
                      created=CREATED.isoformat())
    hasura.fail_writes = "Không gọi được Hasura"
    with pytest.raises(HasuraError):
        run(deadlines.handle(job(doc=OUT), now=at(1.1)))
    assert hasura.sent() == {"task.overdue": {"u-manager-dt"}}    # đã gửi, chưa ghi dòng thời gian
    hasura.fail_writes = None
    run(deadlines.handle(job(doc=OUT), now=at(1.2)))               # Flowable giao lại việc
    run(deadlines.handle(job(doc=OUT), now=at(1.3)))
    (event,) = events(hasura, "office.task.overdue")
    assert event["data"]["notified"] == ["u-manager-dt"] and len(hasura.notifications) == 1


def test_staff_task_escalates_to_their_department_manager(deadlines, hasura, flowable):
    flowable.add_task("t1", "vbden.xuLy", assignee="u-staff-dt", process="p1", created=CREATED.isoformat())
    run(deadlines.handle(job(), now=at(2.1)))
    assert hasura.sent() == {"task.overdue": {"u-staff-dt"}, "task.escalated": {"u-manager-dt"}}
    escalated = next(n for n in hasura.notifications if n["kind"] == "task.escalated")
    assert escalated["data"]["assignee_name"] == "Nguyễn Văn An"


def test_director_task_has_nobody_above(deadlines, hasura, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP], process="p1", created=CREATED.isoformat())
    run(deadlines.handle(job(), now=at(2.1)))
    assert hasura.sent() == {"task.overdue": {"u-director"}}
    assert events(hasura, "office.task.escalated") == []


def test_timer_of_a_finished_step_ignores_the_newer_task(deadlines, hasura, flowable):
    flowable.add_task("t2", "vbden.phanCong", groups=[MANAGER_GROUP], process="p1",
                      created=at(0.9).isoformat())
    run(deadlines.handle(job(), now=at(1.0)))
    assert hasura.notifications == [] and hasura.writes == []


def test_jobs_are_completed_and_a_broken_one_is_reported(deadlines, hasura, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP], process="p1", created=CREATED.isoformat())
    flowable.jobs = [job(), ExternalJob("j-hong", "p1", "nhacHan", {"tenantId": "khong-phai-uuid", "documentId": DOC})]
    assert run(deadlines.run_jobs()) == 2
    assert flowable.jobs_done == ["j1"] and flowable.jobs_failed[0][0] == "j-hong"


def test_flowable_refusing_a_report_does_not_stop_the_batch(deadlines, hasura, flowable):
    async def refuse(job_id, worker_id):
        raise FlowableError("lock lost", 403)

    flowable.complete_job = refuse
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP], process="p1", created=CREATED.isoformat())
    flowable.jobs = [job(), ExternalJob("j3", "p1", "nhacHan", {})]
    assert run(deadlines.run_jobs()) == 2
    assert hasura.sent() == {"task.overdue": {"u-director"}}


def test_job_without_document_is_just_closed(deadlines, hasura, flowable):
    flowable.jobs = [ExternalJob("j2", "p1", "nhacHan", {})]
    run(deadlines.run_jobs())
    assert flowable.jobs_done == ["j2"] and hasura.notifications == []


def test_overdue_incoming_documents_are_reported_once(deadlines, hasura):
    hasura.overdue = [{
        "id": DOC, "tenant_id": str(TENANT), "summary": "Về việc báo cáo chuyển đổi số", "symbol": "12/SGDĐT-VP",
        "due_on": "2026-10-18",
        "assignments": [{"user_id": None, "department_id": str(DEPT_DT), "assigned_by": "u-director"},
                        {"user_id": "u-staff-dt", "department_id": None, "assigned_by": "u-manager-dt"}],
    }]
    assert run(deadlines.overdue_documents()) == 1
    assert hasura.sent() == {"document.overdue": {"u-staff-dt", "u-manager-dt", "u-director"}}
    (event,) = events(hasura, "office.document.overdue")
    assert event["data"]["due_on"] == "2026-10-18"
    run(deadlines.overdue_documents())       # lần quét sau (giả: CSDL vẫn trả lại) không gửi thêm
    assert len(hasura.notifications) == 3


@pytest.mark.parametrize("name", ["van-ban-den", "van-ban-di"])
def test_every_user_task_has_a_non_interrupting_sla_timer(name):
    process = ET.parse(PROCESSES / f"{name}.bpmn20.xml").getroot().find(f"{BPMN}process")
    tasks = {t.get("id") for t in process.iter(f"{BPMN}userTask")}
    timers = {b.get("attachedToRef"): b for b in process.iter(f"{BPMN}boundaryEvent")}
    assert tasks and tasks <= set(timers)
    for boundary in timers.values():
        assert boundary.get("cancelActivity") == "false"
        assert boundary.find(f"{BPMN}timerEventDefinition/{BPMN}timeCycle").text == "R2/${slaDuration}"
    (worker,) = [s for s in process.iter(f"{BPMN}serviceTask") if s.get(f"{FLOWABLE}type") == "external-worker"]
    assert worker.get(f"{FLOWABLE}topic") == "moc-sla"
    flows = {(f.get("sourceRef"), f.get("targetRef")) for f in process.iter(f"{BPMN}sequenceFlow")}
    assert {(b.get("id"), worker.get("id")) for b in timers.values()} <= flows
