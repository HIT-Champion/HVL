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


"""Văn bản đi: trình, duyệt hoặc trả lại, phát hành (Action submitOutgoing, completeTask cho việc vbdi.*)."""

from __future__ import annotations

import asyncio

import pytest

from conftest import DEPT_DT, OUT, TENANT, actor
from svc_workflow.workflow import BASE32, WorkflowError, new_verify_code

DRAFTER = actor("staff", "u-staff-dt", dept=DEPT_DT)
MANAGER = actor("manager", "u-manager-dt", dept=DEPT_DT)
DIRECTOR = actor("director", "u-director")
CLERK = actor("clerk", "u-clerk")
MANAGER_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"
CLERK_GROUP = f"t:{TENANT}:clerk"


def run(coro):
    return asyncio.run(coro)


def writes(hasura, op):
    return [w for w in hasura.writes if w[0] == op]


def test_first_submission_starts_the_process_and_moves_to_review(workflow, hasura, flowable):
    result = run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    assert result == {"document_id": OUT, "status": "in_review"}
    started = flowable.started[0]
    assert (started["departmentId"], started["drafterId"], started["signerId"]) == (str(DEPT_DT), "u-staff-dt", "u-director")
    (_, variables, who), = writes(hasura, "Trinh")
    assert variables["set"] == {"status": "in_review", "signer_id": "u-director"}
    assert variables["event"]["kind"] == "office.document.submitted" and who.user_id == "u-staff-dt"
    assert hasura.outgoing["process_id"] == f"proc-{OUT}"   # gắn khi còn trống, trước lúc chuyển trạng thái


def test_double_submission_submits_once(workflow, hasura, flowable):
    hasura.slow = flowable.slow = True

    async def twice():
        return await asyncio.gather(*(workflow.submit_outgoing(DRAFTER, OUT, "u-director") for _ in range(2)))

    assert run(twice()) == [{"document_id": OUT, "status": "in_review"}] * 2
    assert len(writes(hasura, "Trinh")) == 1 and len(flowable.started) == 1 and flowable.deleted == []


def test_only_the_drafter_submits(workflow, hasura):
    with pytest.raises(WorkflowError) as err:
        run(workflow.submit_outgoing(actor("staff", "u-staff-ktpm"), OUT, "u-director"))
    assert err.value.code == "not_your_document" and not hasura.writes


@pytest.mark.parametrize(("field", "value", "message"), [
    ("body", "  ", "chưa có nội dung"),
    ("body", None, "chưa có nội dung"),
    ("recipients", [], "nơi nhận"),
])
def test_draft_must_be_complete_before_submission(workflow, hasura, flowable, field, value, message):
    hasura.outgoing[field] = value
    with pytest.raises(WorkflowError, match=message):
        run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    assert not hasura.writes and not flowable.started


@pytest.mark.parametrize("signer", ["u-manager-dt", "u-clerk", "khong-co"])
def test_signer_must_be_a_director_of_the_tenant(workflow, hasura, signer):
    with pytest.raises(WorkflowError, match="lãnh đạo đơn vị"):
        run(workflow.submit_outgoing(DRAFTER, OUT, signer))


def test_department_without_manager_cannot_review(workflow, hasura):
    hasura.users["u-manager-dt"]["enabled"] = False
    with pytest.raises(WorkflowError) as err:
        run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    assert err.value.code == "no_manager"


@pytest.mark.parametrize("status", ["approved", "issued"])
def test_cannot_submit_after_review(workflow, hasura, status):
    hasura.outgoing["status"] = status
    with pytest.raises(WorkflowError) as err:
        run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    assert err.value.code == "wrong_status"


def test_resubmission_after_return_finishes_revision_with_new_signer(workflow, hasura, flowable):
    hasura.users["u-director-2"] = {"id": "u-director-2", "department_id": None, "role": "director", "enabled": True}
    hasura.outgoing.update(status="returned", process_id="p-out", signer_id="u-director")
    flowable.add_task("t-sua", "vbdi.chinhSua", assignee="u-staff-dt", doc=OUT, process="p-out")
    run(workflow.submit_outgoing(DRAFTER, OUT, "u-director-2"))
    (_, variables, _), = writes(hasura, "Trinh")
    assert variables["set"] == {"status": "in_review", "signer_id": "u-director-2"}
    assert variables["event"]["kind"] == "office.document.resubmitted"
    assert flowable.completed == [("t-sua", {"signerId": "u-director-2"})] and not flowable.started


def test_retrying_a_submission_does_not_write_twice(workflow, hasura, flowable):
    hasura.outgoing.update(status="in_review", process_id="p-out", signer_id="u-director")
    flowable.add_task("t-sua", "vbdi.chinhSua", assignee="u-staff-dt", doc=OUT, process="p-out")
    run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))
    assert not hasura.writes and flowable.completed == [("t-sua", {"signerId": "u-director"})]


def test_department_approval_records_event_and_moves_to_signer(workflow, hasura, flowable):
    hasura.outgoing["status"] = "in_review"
    flowable.add_task("t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT)
    run(workflow.complete_task(MANAGER, "t-phong", "approve", {"note": "Đồng ý trình ký"}))
    (_, variables, _), = writes(hasura, "GhiSuKien")
    assert variables["event"]["kind"] == "office.document.reviewed"
    assert flowable.completed == [("t-phong", {"outcome": "approve"})]


def test_returning_needs_a_reason_and_sets_status(workflow, hasura, flowable):
    hasura.outgoing["status"] = "in_review"
    flowable.add_task("t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT)
    with pytest.raises(WorkflowError) as err:
        run(workflow.complete_task(MANAGER, "t-phong", "return", {}))
    assert err.value.code == "invalid_data"
    run(workflow.complete_task(MANAGER, "t-phong", "return", {"note": "Sửa lại nơi nhận"}))
    (_, variables, _), = writes(hasura, "DoiTrangThai")
    assert variables["status"] == "returned" and variables["event"]["note"] == "Sửa lại nơi nhận"
    assert flowable.completed == [("t-phong", {"outcome": "return"})]



def test_retry_with_another_choice_finishes_the_saved_one(workflow, hasura, flowable):
    hasura.outgoing["status"] = "in_review"
    flowable.add_task("t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT)
    flowable.fail_complete = 1
    with pytest.raises(WorkflowError, match="Đã lưu"):
        run(workflow.complete_task(MANAGER, "t-phong", "return", {"note": "Sửa lại nơi nhận"}))
    # bấm lại nhưng chọn đồng ý: Flowable đi đúng nhánh đã ghi (trả lại), không ghi thêm
    run(workflow.complete_task(MANAGER, "t-phong", "approve", {"note": "Đồng ý trình ký"}))
    assert [w[0] for w in hasura.writes] == ["DoiTrangThai"]
    assert flowable.completed == [("t-phong", {"outcome": "return"})]

def test_signer_approval_sets_approved(workflow, hasura, flowable):
    hasura.outgoing.update(status="in_review", signer_id="u-director")
    flowable.add_task("t-ky", "vbdi.duyetDonVi", assignee="u-director", doc=OUT)
    with pytest.raises(WorkflowError) as err:
        run(workflow.complete_task(actor("director", "u-director-khac"), "t-ky", "approve", {}))
    assert err.value.code == "not_your_task"
    run(workflow.complete_task(DIRECTOR, "t-ky", "approve", {}))
    (_, variables, _), = writes(hasura, "DoiTrangThai")
    assert variables["status"] == "approved" and variables["event"]["kind"] == "office.document.approved"


def test_review_needs_document_in_review(workflow, hasura, flowable):
    hasura.outgoing["status"] = "draft"
    flowable.add_task("t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT)
    with pytest.raises(WorkflowError) as err:
        run(workflow.complete_task(MANAGER, "t-phong", "approve", {}))
    assert err.value.code == "wrong_status" and not hasura.writes


def test_revision_task_is_finished_by_resubmitting_not_complete_task(workflow, flowable):
    flowable.add_task("t-sua", "vbdi.chinhSua", assignee="u-staff-dt", doc=OUT)
    with pytest.raises(WorkflowError) as err:
        run(workflow.complete_task(DRAFTER, "t-sua", "done", {}))
    assert err.value.code == "use_submit" and not flowable.completed


def test_issuing_numbers_renders_and_records_hash(workflow, hasura, flowable, files):
    hasura.outgoing.update(status="approved", signer_id="u-director")
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)
    run(workflow.complete_task(CLERK, "t-ph", "issue", {"is_public": True}))

    assert len(hasura.numbered) == 1 and files.calls == [("u-clerk", OUT)]
    (_, variables, who), = writes(hasura, "PhatHanh")
    assert variables["sha"] == "\\x" + "ab" * 32 and variables["public"] is True
    assert variables["file"] == {"document_id": OUT, "file_id": "f-1", "role": "issued", "added_by": "u-clerk"}
    data = variables["event"]["data"]
    assert (data["symbol"], data["verify_code"], data["is_public"]) == ("05/TB-CNTT", hasura.numbered[0]["code"], True)
    assert who.user_id == "u-clerk" and flowable.claims == [("t-ph", "u-clerk")]
    assert flowable.completed == [("t-ph", {"outcome": "issue"})]


def test_issue_fails_cleanly_when_files_service_is_down(workflow, hasura, flowable, files):
    hasura.outgoing.update(status="approved", signer_id="u-director")
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)
    files.down = True
    with pytest.raises(WorkflowError) as err:
        run(workflow.complete_task(CLERK, "t-ph", "issue", {}))
    assert err.value.status == 503 and err.value.code == "files_unavailable"
    assert not writes(hasura, "PhatHanh") and flowable.claims == [("t-ph", "u-clerk"), ("t-ph", None)]

    # bấm lại khi svc-files đã lên: dùng lại số và mã đã cấp
    files.down = False
    first_code = hasura.outgoing["verify_code"]
    run(workflow.complete_task(CLERK, "t-ph", "issue", {}))
    assert hasura.outgoing["verify_code"] == first_code and len(writes(hasura, "PhatHanh")) == 1


def test_retry_after_issue_was_recorded_only_finishes_flowable(workflow, hasura, flowable, files):
    hasura.outgoing.update(status="issued", signer_id="u-director")
    hasura.events_with_task.add("t-ph")
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)
    run(workflow.complete_task(CLERK, "t-ph", "issue", {}))
    assert not files.calls and not hasura.writes and flowable.completed == [("t-ph", {"outcome": "issue"})]


def test_issue_needs_signer_approval(workflow, hasura, flowable, files):
    hasura.outgoing["status"] = "in_review"
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)
    with pytest.raises(WorkflowError) as err:
        run(workflow.complete_task(CLERK, "t-ph", "issue", {}))
    assert err.value.code == "wrong_status" and not files.calls


def test_verify_codes_are_ten_base32_characters():
    codes = {new_verify_code() for _ in range(200)}
    assert len(codes) == 200 and all(len(c) == 10 and set(c) <= set(BASE32) for c in codes)
