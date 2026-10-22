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

"""Văn bản hạn chế (F3.7) trong quy trình: tệp mã hóa khi tiếp nhận, người phải làm việc được thêm vào danh sách
xem, người không đọc được văn bản không làm được việc của nó, thông báo không mang trích yếu."""

from __future__ import annotations

import asyncio
import logging

import pytest

from datetime import UTC, datetime, timedelta

from conftest import DEPT_DT, DOC, OUT, TENANT, actor
from svc_workflow.flowable import ExternalJob
from svc_workflow.hasura import HasuraError
from svc_workflow.notify import brief_of
from svc_workflow.schemas import today_vn
from svc_workflow.sla import Deadlines
from svc_workflow.workflow import WorkflowError, _db_error
from test_intake import F1, F2, build

DIRECTOR_GROUP = f"t:{TENANT}:director"
CLERK_GROUP = f"t:{TENANT}:clerk"
MANAGER_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"
CLERK = actor("clerk", "u-clerk")
DIRECTOR = actor("director", "u-director")
DRAFTER = actor("staff", "u-staff-dt", dept=DEPT_DT)
CREATED = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def shared(hasura) -> list[tuple[str, str, str]]:
    return [(r["document_id"], r["user_id"], r["granted_by"])
            for op, variables, _ in hasura.writes if op == "ChoXem" for r in variables["rows"]]


# --- tiếp nhận ------------------------------------------------------------------------------------------

@pytest.fixture
def uploaded(hasura):
    hasura.uploads.update({F1: "u-clerk", F2: "u-clerk"})
    return hasura


def test_restricted_document_takes_only_sealed_files(workflow, uploaded):
    data = build({"set": {"restricted": True, "file_ids": [F1, F2]}}, today_vn())
    uploaded.sealed = {F1}
    with pytest.raises(WorkflowError) as e:
        run(workflow.receive_incoming(CLERK, data))
    assert e.value.fields == {"file_ids": "not_sealed"} and uploaded.writes == []

    uploaded.sealed = {F1, F2}
    assert run(workflow.receive_incoming(CLERK, data))["document_id"]


def test_sealed_files_go_only_to_restricted_documents(workflow, uploaded):
    uploaded.sealed = {F2}
    with pytest.raises(WorkflowError) as e:
        run(workflow.receive_incoming(CLERK, build({"set": {"restricted": False, "file_ids": [F1, F2]}}, today_vn())))
    assert e.value.fields == {"file_ids": "sealed"} and uploaded.writes == []


@pytest.mark.parametrize("raised", [
    "document_files_sealed: văn bản hạn chế chỉ gắn tệp tải lên ở chế độ hạn chế (đã mã hóa)",
    "documents_restricted_sealed: văn bản đã có tệp nên không đổi được chế độ hạn chế",
])
def test_database_refusals_become_vietnamese_messages(raised):
    err = _db_error(HasuraError(raised, "constraint-violation"))
    assert err.code == "constraint" and err.status == 409 and "_sealed" not in err.message


# --- thông báo ---------------------------------------------------------------------------------------------

def test_brief_of_restricted_document_is_only_a_label():
    doc = {"summary": "Danh sách nâng lương", "symbol": "12/QĐ", "urgency": "khan", "direction": "in"}
    assert brief_of({**doc, "restricted": True}) == {"urgency": "khan", "direction": "in", "restricted": True}
    assert brief_of({**doc, "restricted": False}) == doc
    assert brief_of(None) == {}


# --- danh sách xem theo việc đang mở -----------------------------------------------------------------------

def test_registering_a_restricted_document_shares_it_with_whoever_must_direct_it(workflow, hasura, flowable):
    hasura.document["restricted"] = True
    hasura.viewers = {"u-clerk"}     # văn thư tiếp nhận là người tạo
    flowable.then(DOC, "t-chidao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    run(workflow.register_incoming(CLERK, DOC))
    assert shared(hasura) == [(DOC, "u-director", "u-clerk")]
    (note,) = [n for n in hasura.notifications if n["kind"] == "task.assigned"]
    assert note["user_id"] == "u-director"
    assert note["data"]["restricted"] is True and "summary" not in note["data"]


def test_open_documents_are_never_shared(workflow, hasura, flowable):
    flowable.then(DOC, "t-chidao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    run(workflow.register_incoming(CLERK, DOC))
    assert shared(hasura) == []
    assert hasura.notifications[0]["data"]["summary"]


def test_next_step_holder_is_shared_too(workflow, hasura, flowable):
    hasura.document["restricted"] = True
    hasura.viewers = {"u-director"}
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP], process="proc-1")
    flowable.then("t1", "t2", "vbden.xuLy", assignee="u-staff-dt")
    run(workflow.complete_task(DIRECTOR, "t1", "direct", {"instruction": "Chuyên viên An xử lý",
                                                          "lead_user_id": "u-staff-dt"}))
    assert (DOC, "u-staff-dt", "u-director") in shared(hasura)


def test_submitting_again_does_not_bring_back_a_revoked_reader(workflow, hasura, flowable):
    hasura.outgoing.update(status="in_review", process_id="p-out", signer_id="u-director", restricted=True)
    hasura.viewers = {"u-staff-dt"}     # văn thư vừa gỡ lãnh đạo phòng khỏi danh sách xem
    flowable.add_task("t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT, process="p-out")
    # người soạn (không có quyền cấp, gỡ) gọi lại submitOutgoing khi không còn bước nào để hoàn thành
    assert run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))["status"] == "in_review"
    assert shared(hasura) == [] and hasura.notifications == [] and flowable.completed == []


def test_retry_that_finishes_the_revision_still_shares_with_the_reviewer(workflow, hasura, flowable):
    hasura.outgoing.update(status="in_review", process_id="p-out", signer_id="u-director", restricted=True)
    hasura.viewers = {"u-staff-dt"}
    flowable.add_task("t-sua", "vbdi.chinhSua", assignee="u-staff-dt", doc=OUT, process="p-out")
    flowable.then("t-sua", "t-phong", "vbdi.duyetPhong", groups=[MANAGER_GROUP], doc=OUT)
    run(workflow.submit_outgoing(DRAFTER, OUT, "u-director"))   # lần trước đã ghi CSDL, lỗi lúc hoàn thành bước sửa
    assert flowable.completed == [("t-sua", {"signerId": "u-director"})]
    assert shared(hasura) == [(OUT, "u-manager-dt", "u-staff-dt")]
    assert hasura.sent() == {"task.assigned": {"u-manager-dt"}}


def test_someone_who_cannot_read_the_document_cannot_act_on_it(workflow, hasura, flowable):
    hasura.document["restricted"] = True
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(DIRECTOR, "t1", "file", {"note": "Lưu"}))
    assert (e.value.code, e.value.status) == ("restricted", 403)
    assert flowable.claims == [] and hasura.writes == []

    hasura.viewers = {"u-director"}
    run(workflow.complete_task(DIRECTOR, "t1", "file", {"note": "Lưu"}))
    assert flowable.completed[0][0] == "t1"


def test_failing_to_share_does_not_undo_the_step(workflow, hasura, flowable, caplog):
    hasura.document["restricted"] = True
    hasura.viewers = {"u-clerk"}
    hasura.fail_share = True
    flowable.then(DOC, "t-chidao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    with caplog.at_level(logging.WARNING, logger="svc_workflow"):
        out = run(workflow.register_incoming(CLERK, DOC))
    assert out["register_number"] == 7
    assert "office.acl.share_failed" in caplog.text


# --- vào sổ, phát hành -----------------------------------------------------------------------------------

def test_clerk_without_a_name_cannot_register_a_restricted_document(workflow, hasura, flowable):
    hasura.document.update(restricted=True, status="received")
    with pytest.raises(WorkflowError) as e:
        run(workflow.register_incoming(actor("clerk", "u-clerk-2"), DOC))
    assert (e.value.code, e.value.status) == ("document_not_found", 404)   # như không có văn bản: không lộ là có
    assert hasura.document["status"] == "received" and hasura.writes == []

    hasura.viewers = {"u-clerk"}
    assert run(workflow.register_incoming(CLERK, DOC))["register_number"] == 7


def test_restricted_outgoing_document_is_never_issued_public(workflow, hasura, flowable, files):
    hasura.outgoing.update(status="approved", signer_id="u-director", restricted=True)
    hasura.viewers = {"u-clerk"}
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(CLERK, "t-ph", "issue", {"is_public": True}))
    assert (e.value.status, e.value.fields) == (400, {"is_public": "restricted"})
    assert not hasura.numbered and not files.calls          # chưa cấp số, chưa dựng PDF

    run(workflow.complete_task(CLERK, "t-ph", "issue", {"is_public": False}))
    assert flowable.completed == [("t-ph", {"outcome": "issue"})]


def test_public_flag_refused_by_the_database_becomes_a_message():
    err = _db_error(HasuraError("documents_restricted_private", "constraint-violation"))
    assert err.status == 409 and "công khai" in err.message


# --- nhắc hạn -----------------------------------------------------------------------------------------------

def sla_job(doc: str = DOC) -> ExternalJob:
    return ExternalJob("j1", "p1", "nhacHan", {"tenantId": str(TENANT), "documentId": doc, "slaDuration": "PT1M"})


def test_overdue_reminders_reach_only_people_with_a_name(hasura, flowable, notifier):
    deadlines = Deadlines(hasura, flowable, notifier, sla_duration="PT1M")  # type: ignore[arg-type]
    hasura.document["restricted"] = True
    hasura.viewers = {"u-staff-dt"}
    flowable.add_task("t1", "vbden.xuLy", assignee="u-staff-dt", process="p1", created=CREATED.isoformat())
    run(deadlines.handle(sla_job(), now=CREATED + timedelta(minutes=2.1)))
    # trưởng phòng không có tên: không nhận leo thang, không biết có văn bản này
    assert hasura.sent() == {"task.overdue": {"u-staff-dt"}}
    assert hasura.notifications[0]["data"]["restricted"] is True

    hasura.viewers = {"u-staff-dt", "u-manager-dt"}
    flowable.add_task("t2", "vbden.xuLy", assignee="u-staff-dt", process="p1", created=CREATED.isoformat())
    flowable.tasks.pop("t1")
    run(deadlines.handle(sla_job(), now=CREATED + timedelta(minutes=2.1)))
    assert hasura.sent("task.escalated") == {"task.escalated": {"u-manager-dt"}}


def test_overdue_restricted_document_is_reported_only_to_its_viewers(hasura, flowable, notifier):
    deadlines = Deadlines(hasura, flowable, notifier, sla_duration="PT1M")  # type: ignore[arg-type]
    hasura.document["restricted"] = True
    hasura.viewers = {"u-staff-dt"}
    hasura.overdue = [{
        "id": DOC, "tenant_id": str(TENANT), "summary": "Danh sách nâng lương trước hạn", "symbol": "89/ĐHCN-TCCB",
        "due_on": "2026-10-18", "restricted": True,
        "assignments": [{"user_id": "u-staff-dt", "department_id": None, "assigned_by": "u-manager-dt"}],
    }]
    assert run(deadlines.overdue_documents()) == 1
    assert hasura.sent() == {"document.overdue": {"u-staff-dt"}}
    assert hasura.notifications[0]["data"] == {"due_on": "2026-10-18", "restricted": True}
