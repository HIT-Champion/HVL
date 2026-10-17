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

"""Nghiệp vụ của các Action: ai được làm việc nào, kiểm dữ liệu, không ghi trùng khi gọi lại."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest

from conftest import DEPT_DT, DEPT_KTPM, DOC, OTHER, TENANT, actor
from svc_workflow.workflow import WorkflowError

DIRECTOR_GROUP = f"t:{TENANT}:director"
MANAGER_DT_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"


def run(coro):
    return asyncio.run(coro)


def direct_data(**extra):
    return {"instruction": "Giao Tổ Đào tạo chủ trì", "lead_department_id": str(DEPT_DT), **extra}


# --- vào sổ ---------------------------------------------------------------------------------------


def test_register_starts_process_and_links_it(workflow, hasura, flowable):
    out = run(workflow.register_incoming(actor("clerk", "u-clerk"), DOC))
    assert out == {"document_id": DOC, "register_number": 7}
    assert flowable.started[0]["tenantId"] == str(TENANT) and flowable.started[0]["urgency"] == "khan"
    assert hasura.writes[-1][0] == "SetProcess" and hasura.writes[-1][1]["pid"] == f"proc-{DOC}"


def test_register_reuses_existing_process(workflow, hasura, flowable):
    flowable.processes[DOC] = "proc-old"
    run(workflow.register_incoming(actor("clerk"), DOC))
    assert flowable.started == [] and hasura.writes[-1][1]["pid"] == "proc-old"


def test_register_keeps_number_when_flowable_is_down(workflow, hasura, flowable):
    flowable.down = True
    out = run(workflow.register_incoming(actor("clerk"), DOC))
    assert out["register_number"] == 7          # số đã cấp; job đối soát khởi chạy quy trình sau
    assert not any(w[0] == "SetProcess" for w in hasura.writes)


def test_register_maps_errors(workflow, hasura):
    with pytest.raises(WorkflowError) as e:
        run(workflow.register_incoming(actor("clerk", tenant=OTHER), DOC))
    assert e.value.status == 404
    with pytest.raises(WorkflowError) as e:
        run(workflow.register_incoming(actor("clerk"), "khong-phai-uuid"))
    assert e.value.status == 404
    hasura.register_error = "văn bản ở trạng thái cancelled không vào sổ được"
    with pytest.raises(WorkflowError) as e:
        run(workflow.register_incoming(actor("clerk"), DOC))
    assert e.value.code == "wrong_status"


# --- hộp việc -------------------------------------------------------------------------------------


def test_inbox_has_own_and_group_tasks_of_own_tenant_urgent_first(workflow, flowable):
    flowable.add_task("t-normal", "vbden.chiDao", groups=[DIRECTOR_GROUP], created="2026-10-18T08:00:00Z")
    flowable.add_task("t-urgent", "vbden.chiDao", groups=[DIRECTOR_GROUP], urgency="hoa_toc", created="2026-10-18T09:00:00Z")
    flowable.add_task("t-mine", "vbden.xuLy", assignee="u-director")
    flowable.add_task("t-other-tenant", "vbden.chiDao", assignee="u-director", tenant=OTHER)
    flowable.add_task("t-manager", "vbden.phanCong", groups=[MANAGER_DT_GROUP])
    ids = [t["id"] for t in run(workflow.my_tasks(actor("director", "u-director")))]
    assert ids[0] == "t-urgent"
    assert set(ids) == {"t-urgent", "t-normal", "t-mine"}


def test_groups_follow_role_and_department():
    assert actor("director").groups == [DIRECTOR_GROUP]
    assert actor("manager", dept=DEPT_DT).groups == [MANAGER_DT_GROUP]
    assert actor("manager").groups == []                 # thiếu phòng thì không nhận việc của phòng nào
    assert actor("staff", dept=DEPT_DT).groups == []
    assert actor("tenant_admin").groups == []


def test_inbox_reports_workflow_down(workflow, flowable):
    flowable.down = True
    with pytest.raises(WorkflowError) as e:
        run(workflow.my_tasks(actor("staff")))
    assert e.value.status == 503


# --- quyền hoàn thành việc --------------------------------------------------------------------------


def test_cannot_complete_task_of_other_tenant(workflow, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[f"t:{OTHER}:director"], tenant=OTHER)
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("director"), "t1", "direct", direct_data()))
    assert e.value.status == 404


def test_cannot_complete_task_outside_own_groups(workflow, flowable, hasura):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("manager", dept=DEPT_DT), "t1", "direct", direct_data()))
    assert e.value.code == "not_your_task"
    assert flowable.claims == [] and hasura.writes == []


def test_cannot_complete_task_assigned_to_someone_else(workflow, flowable):
    flowable.add_task("t1", "vbden.xuLy", assignee="u-staff-dt")
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("staff", "u-staff-ktpm"), "t1", "done", {"result_note": "xong"}))
    assert e.value.status == 403


def test_task_taken_by_another_director_is_409(workflow, flowable, hasura):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    flowable.claim_conflict = True
    hasura.users["u-manager-dt"]["enabled"] = True
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("director"), "t1", "direct", direct_data()))
    assert e.value.code == "task_taken" and hasura.writes == []


# --- kiểm dữ liệu (poka-yoke lớp 2) -----------------------------------------------------------------


@pytest.mark.parametrize("data", [
    {"instruction": "x"},                                                             # thiếu nơi chủ trì
    {"instruction": "x", "lead_department_id": str(DEPT_DT), "lead_user_id": "u-staff-dt"},  # hai nơi chủ trì
    {"instruction": "x", "lead_department_id": str(DEPT_DT), "supports": [str(DEPT_DT)]},     # chủ trì kiêm phối hợp
    {"instruction": "  ", "lead_department_id": str(DEPT_DT)},                         # ý kiến trống
    {"instruction": "x", "lead_department_id": str(DEPT_DT), "status": "done"},          # trường lạ
])
def test_invalid_direction_is_rejected_before_anything_is_written(workflow, flowable, hasura, data):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("director"), "t1", "direct", data))
    assert e.value.code == "invalid_data"
    assert flowable.claims == [] and hasura.writes == [] and flowable.completed == []


def test_unknown_outcome_is_rejected(workflow, flowable):
    flowable.add_task("t1", "vbden.xuLy", assignee="u-staff-dt")
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("staff", "u-staff-dt"), "t1", "approve", {}))
    assert e.value.code == "bad_outcome"


def test_past_due_date_is_rejected(workflow, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    past = (date.today() - timedelta(days=1)).isoformat()
    with pytest.raises(WorkflowError, match="Hạn"):
        run(workflow.complete_task(actor("director"), "t1", "direct", direct_data(due_on=past)))


def test_department_without_manager_cannot_lead(workflow, flowable, hasura):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("director"), "t1", "direct",
                                   {"instruction": "x", "lead_department_id": str(DEPT_KTPM)}))
    assert e.value.code == "no_manager"


def test_lead_person_must_be_a_handler_of_the_tenant(workflow, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    for user in ("u-khong-co", "u-clerk"):
        with pytest.raises(WorkflowError):
            run(workflow.complete_task(actor("director"), "t1", "direct", {"instruction": "x", "lead_user_id": user}))


# --- ghi dữ liệu và chuyển bước -----------------------------------------------------------------------


def test_direction_writes_assignments_event_and_moves_process(workflow, flowable, hasura):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    due = (date.today() + timedelta(days=3)).isoformat()
    run(workflow.complete_task(actor("director", "u-director"), "t1", "direct",
                               direct_data(supports=[str(DEPT_KTPM)], due_on=due)))
    op, v, who = hasura.writes[-1]
    assert op == "ChiDao" and who.user_id == "u-director"
    assert v["lead"] == {"document_id": DOC, "instruction": "Giao Tổ Đào tạo chủ trì", "due_on": due,
                         "assigned_by": "u-director", "role": "lead", "department_id": str(DEPT_DT)}
    assert [s["department_id"] for s in v["supports"]] == [str(DEPT_KTPM)]
    assert v["event"]["kind"] == "office.document.directed" and v["event"]["data"]["task_id"] == "t1"
    assert flowable.claims == [("t1", "u-director")]
    assert flowable.completed == [("t1", {"outcome": "direct", "leadDepartmentId": str(DEPT_DT), "handlerId": "",
                                          "dueOn": due})]


def test_direct_to_a_person_skips_department_assignment(workflow, flowable):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    run(workflow.complete_task(actor("director"), "t1", "direct", {"instruction": "Anh Nam xử lý", "lead_user_id": "u-staff-dt"}))
    assert flowable.completed[0][1]["handlerId"] == "u-staff-dt"


def test_retry_after_database_write_only_finishes_flowable(workflow, flowable, hasura):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP], doc=DOC)
    hasura.events_with_task.add("t1")              # lần gọi trước đã ghi CSDL rồi mất kết nối
    run(workflow.complete_task(actor("director"), "t1", "direct", direct_data()))
    assert hasura.writes == []
    assert flowable.completed and flowable.completed[0][0] == "t1"


def test_database_rejection_returns_task_to_group(workflow, flowable, hasura):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    hasura.fail_writes = 'Check constraint violation. new row violates "documents_due_after_registered"'
    with pytest.raises(WorkflowError, match="Hạn giải quyết"):
        run(workflow.complete_task(actor("director", "u-director"), "t1", "direct", direct_data()))
    assert flowable.claims == [("t1", "u-director"), ("t1", None)]
    assert flowable.completed == []


def test_manager_assigns_within_own_department(workflow, flowable, hasura):
    hasura.assignments = [{"id": "a-lead", "parent_id": None, "department_id": str(DEPT_DT), "user_id": None,
                           "role": "lead", "due_on": "2026-10-25", "status": "open"}]
    flowable.add_task("t2", "vbden.phanCong", groups=[MANAGER_DT_GROUP])
    manager = actor("manager", "u-manager-dt", dept=DEPT_DT)
    with pytest.raises(WorkflowError):
        run(workflow.complete_task(manager, "t2", "assign", {"user_id": "u-staff-ktpm"}))   # người phòng khác
    run(workflow.complete_task(manager, "t2", "assign", {"user_id": "u-staff-dt", "note": "Em xử lý"}))
    op, v, _ = hasura.writes[-1]
    assert op == "PhanCong" and v["child"]["parent_id"] == "a-lead" and v["child"]["due_on"] == "2026-10-25"
    assert flowable.completed[-1] == ("t2", {"outcome": "assign", "handlerId": "u-staff-dt"})


def test_handler_reports_done_closing_own_and_department_assignment(workflow, flowable, hasura):
    hasura.assignments = [
        {"id": "a-lead", "parent_id": None, "department_id": str(DEPT_DT), "user_id": None, "role": "lead",
         "due_on": None, "status": "open"},
        {"id": "a-me", "parent_id": "a-lead", "department_id": None, "user_id": "u-staff-dt", "role": "lead",
         "due_on": None, "status": "open"},
    ]
    flowable.add_task("t3", "vbden.xuLy", assignee="u-staff-dt")
    run(workflow.complete_task(actor("staff", "u-staff-dt", dept=DEPT_DT), "t3", "done", {"result_note": "Đã xong"}))
    op, v, _ = hasura.writes[-1]
    assert op == "XuLy" and v["ids"] == ["a-me", "a-lead"] and v["note"] == "Đã xong"
    assert flowable.claims == []                    # việc đích danh: không cần nhận
