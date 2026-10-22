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

"""Thông báo (F2.5): ai nhận sau mỗi bước, gửi một lần, đẩy qua Centrifugo, lỗi không làm hỏng bước nghiệp vụ."""

from __future__ import annotations

import asyncio
import json

import httpx2
import pytest

from conftest import DEPT_DT, DEPT_KTPM, DOC, OUT, TENANT, actor
from svc_workflow.notify import Notifier, People, Person

DIRECTOR_GROUP = f"t:{TENANT}:director"
MANAGER_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"
CLERK_GROUP = f"t:{TENANT}:clerk"
DRAFTER = actor("staff", "u-staff-dt", dept=DEPT_DT)
MANAGER = actor("manager", "u-manager-dt", dept=DEPT_DT)
DIRECTOR = actor("director", "u-director")
CLERK = actor("clerk", "u-clerk")


def run(coro):
    return asyncio.run(coro)


def people() -> People:
    rows = [("d1", "director", None), ("m-dt", "manager", str(DEPT_DT)), ("m-ktpm", "manager", str(DEPT_KTPM)),
            ("s-dt", "staff", str(DEPT_DT)), ("s-ktpm", "staff", str(DEPT_KTPM)), ("c1", "clerk", None)]
    return People({i: Person(i, role, dept, i.upper()) for i, role, dept in rows})


# --- ai nhận ---------------------------------------------------------------------------------------------

def test_candidate_groups_map_to_people_of_own_tenant_only():
    p = people()
    assert p.group(str(TENANT), DIRECTOR_GROUP) == {"d1"}
    assert p.group(str(TENANT), CLERK_GROUP) == {"c1"}
    assert p.group(str(TENANT), MANAGER_GROUP) == {"m-dt"}
    assert p.group(str(TENANT), "t:other:director") == set()
    assert p.group(str(TENANT), "rác") == set()


def test_overdue_goes_up_one_level():
    p, t = people(), str(TENANT)
    assert p.leaders(t, "s-dt", []) == {"m-dt"}                       # chuyên viên → lãnh đạo phòng
    assert p.leaders(t, "m-dt", []) == {"d1"}                         # lãnh đạo phòng → lãnh đạo đơn vị
    assert p.leaders(t, None, [MANAGER_GROUP]) == {"d1"}
    assert p.leaders(t, None, [CLERK_GROUP]) == {"d1"}
    assert p.leaders(t, None, [DIRECTOR_GROUP]) == set()              # việc của lãnh đạo đơn vị: không ai trên
    assert p.leaders(t, "d1", []) == set()
    del p["m-dt"]
    assert p.leaders(t, "s-dt", []) == {"d1"}                         # phòng chưa có lãnh đạo


# --- ghi và đẩy ---------------------------------------------------------------------------------------------

class Centrifugo:
    def __init__(self, status: int = 200, down: bool = False):
        self.calls: list[dict] = []
        self.status, self.down = status, down

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if self.status == 299:
            return httpx2.Response(200, text="<html>proxy</html>")
        if self.down:
            raise httpx2.ConnectError("refused")
        assert request.headers["X-API-Key"] == "khoa-api"
        body = json.loads(request.content)
        self.calls.append(body)
        return httpx2.Response(self.status, json={"replies": [{"publish": {}} for _ in body["commands"]]})


def test_send_writes_once_and_pushes_to_personal_channels(hasura):
    cf = Centrifugo()
    n = Notifier(hasura, "http://centrifugo:9000", "khoa-api", transport=httpx2.MockTransport(cf))
    sent = run(n.send(DIRECTOR, ["u-staff-dt", "u-manager-dt", "", "u-staff-dt"], "task.assigned", "task:t1:assigned",
                      DOC, {"form_key": "vbden.xuLy"}))
    assert sent == ["u-manager-dt", "u-staff-dt"]
    (call,) = cf.calls
    channels = [c["publish"]["channel"] for c in call["commands"]]
    assert channels == ["personal:#u-manager-dt", "personal:#u-staff-dt"]
    assert call["commands"][0]["publish"]["data"]["kind"] == "task.assigned"

    # cùng khóa: không ghi thêm, không đẩy lại
    assert run(n.send(DIRECTOR, ["u-staff-dt"], "task.assigned", "task:t1:assigned", DOC, {})) == []
    assert len(cf.calls) == 1 and len(hasura.notifications) == 2


@pytest.mark.parametrize("cf", [Centrifugo(status=500), Centrifugo(down=True), Centrifugo(status=299)])
def test_push_failure_keeps_the_stored_notification(hasura, cf, caplog):
    n = Notifier(hasura, "http://centrifugo:9000", "khoa-api", transport=httpx2.MockTransport(cf))
    assert run(n.send(DIRECTOR, ["u-staff-dt"], "task.assigned", "k", DOC, {})) == ["u-staff-dt"]
    assert "core.notification.push_failed" in caplog.text


def test_without_api_key_only_stores(hasura):
    cf = Centrifugo()
    n = Notifier(hasura, "http://centrifugo:9000", "", transport=httpx2.MockTransport(cf))
    assert run(n.send(DIRECTOR, ["u-staff-dt"], "task.assigned", "k", DOC, {})) == ["u-staff-dt"]
    assert cf.calls == []


# --- sau mỗi bước ------------------------------------------------------------------------------------------

def test_registering_tells_directors_about_the_new_task(workflow, hasura, flowable):
    flowable.then(DOC, "t-chi-dao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    run(workflow.register_incoming(CLERK, DOC))
    (note,) = hasura.notifications
    assert (note["user_id"], note["kind"], note["key"]) == ("u-director", "task.assigned", "task:t-chi-dao:assigned")
    assert note["data"]["form_key"] == "vbden.chiDao" and note["data"]["urgency"] == "khan"


def test_direction_tells_the_lead_department_managers(workflow, hasura, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP], process="p-in")
    flowable.then("t1", "t2", "vbden.phanCong", groups=[MANAGER_GROUP])
    run(workflow.complete_task(DIRECTOR, "t1", "direct",
                               {"instruction": "Giao Tổ Đào tạo chủ trì", "lead_department_id": str(DEPT_DT)}))
    assert hasura.sent() == {"task.assigned": {"u-manager-dt"}}


def test_the_person_who_acted_is_not_told_about_own_next_task(workflow, hasura, flowable):
    flowable.add_task("t2", "vbden.phanCong", groups=[MANAGER_GROUP])
    flowable.then("t2", "t3", "vbden.xuLy", assignee="u-manager-dt")
    hasura.assignments = [{"id": "a-lead", "parent_id": None, "department_id": str(DEPT_DT), "user_id": None,
                           "role": "lead", "due_on": None, "status": "open", "assigned_by": "u-director"}]
    run(workflow.complete_task(MANAGER, "t2", "self", {"note": "Tôi tự xử lý"}))
    assert hasura.notifications == []


def test_outgoing_flow_notifies_each_next_person(workflow, hasura, flowable):
    flowable.then(OUT, "t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP])
    run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    assert hasura.sent() == {"task.assigned": {"u-manager-dt"}}

    hasura.outgoing.update(status="in_review", process_id=f"proc-{OUT}")
    flowable.then("t-phong", "t-sua", "vbdi.chinhSua", assignee="u-staff-dt")
    run(workflow.complete_task(MANAGER, "t-phong", "return", {"note": "Sửa lại nơi nhận"}))
    returned = [n for n in hasura.notifications if n["key"] == "task:t-sua:assigned"]
    assert returned[0]["user_id"] == "u-staff-dt" and returned[0]["data"]["note"] == "Sửa lại nơi nhận"


def test_issuing_tells_drafter_and_signer(workflow, hasura, flowable):
    hasura.outgoing.update(status="approved", process_id="p-out", signer_id="u-director")
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT, process="p-out")
    run(workflow.complete_task(CLERK, "t-ph", "issue", {"is_public": True}))
    issued = hasura.sent("document.issued")["document.issued"]
    assert issued == {"u-staff-dt", "u-director"}
    note = next(n for n in hasura.notifications if n["kind"] == "document.issued")
    assert note["key"] == f"doc:{OUT}:document.issued" and note["data"]["summary"] == "Thông báo lịch họp giao ban"


def test_reporting_done_tells_those_who_assigned(workflow, hasura, flowable):
    hasura.assignments = [
        {"id": "a-lead", "parent_id": None, "department_id": str(DEPT_DT), "user_id": None, "role": "lead",
         "due_on": None, "status": "open", "assigned_by": "u-director"},
        {"id": "a-me", "parent_id": "a-lead", "department_id": None, "user_id": "u-staff-dt", "role": "lead",
         "due_on": None, "status": "open", "assigned_by": "u-manager-dt"},
    ]
    flowable.add_task("t3", "vbden.xuLy", assignee="u-staff-dt")
    run(workflow.complete_task(DRAFTER, "t3", "done", {"result_note": "Đã gửi danh sách"}))
    assert hasura.sent() == {"document.processed": {"u-director", "u-manager-dt"}}
    note = hasura.notifications[0]
    assert note["data"]["by_name"] == "Nguyễn Văn An" and note["data"]["note"] == "Đã gửi danh sách"


def test_notification_failure_never_fails_the_step(workflow, hasura, flowable, caplog):
    hasura.fail_notify = True
    flowable.then(DOC, "t-chi-dao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    assert run(workflow.register_incoming(CLERK, DOC))["register_number"] == 7
    assert "core.notification.failed" in caplog.text


def test_unexpected_error_in_notification_still_returns_the_step(workflow, hasura, flowable, caplog):
    async def broken(actor):
        raise ValueError("trả lời lạ")

    workflow.notifier.people = broken
    flowable.then(DOC, "t-chi-dao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    assert run(workflow.register_incoming(CLERK, DOC))["register_number"] == 7
    assert "ValueError" in caplog.text


def test_retrying_a_step_does_not_notify_twice(workflow, hasura, flowable):
    flowable.then(OUT, "t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT)
    run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))   # gọi lại: không còn bước nào để hoàn thành
    assert [n["key"] for n in hasura.notifications] == ["task:t-phong:assigned"]
