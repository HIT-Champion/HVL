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

"""Liên thông văn bản trong hệ thống (F3.12): phát hành → văn bản đến ở đơn vị nhận; tệp chép một lần, văn thư bên
nhận được báo một lần, lỗi thì thử lại lùi dần, và không bao giờ làm hỏng bước phát hành."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import timedelta

import httpx2
import pytest

from conftest import OTHER, OUT, RECEIVED_BY_HAND, TENANT, actor
from svc_workflow.app import create_app
from svc_workflow.config import Settings
from svc_workflow.dispatch import Dispatcher, backoff
from svc_workflow.files import DispatchFileError, FilesClient, FilesError, ServiceToken
from svc_workflow.hasura import HasuraError
from svc_workflow.workflow import WorkflowError

CLERK = actor("clerk", "u-clerk")
CLERK_GROUP = f"t:{TENANT}:clerk"
KT = str(OTHER)
KEY = "doc:{}:document.incoming"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def khoa_kinh_te(hasura):
    hasura.tenant_users[OTHER] = {
        "u-vanthu-kt": {"id": "u-vanthu-kt", "department_id": None, "role": "clerk", "enabled": True,
                        "full_name": "Văn thư Khoa Kinh tế"},
        "u-truong-kt": {"id": "u-truong-kt", "department_id": None, "role": "director", "enabled": True,
                        "full_name": "Trưởng khoa Kinh tế"},
    }


def approved(hasura, flowable, units=(KT,)):
    hasura.outgoing.update(status="approved", signer_id="u-director", recipient_tenant_ids=list(units))
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)


def issue(workflow):
    return run(workflow.complete_task(CLERK, "t-ph", "issue", {}))


def only(hasura):
    (row,) = hasura.dispatches.values()
    return row


def incoming_notes(hasura):
    return [n for n in hasura.notifications if n["kind"] == "document.incoming"]


# --- đường thẳng -------------------------------------------------------------------------------------------


def test_issuing_delivers_to_the_unit_and_tells_its_clerks_once(workflow, hasura, flowable, files, dispatcher):
    approved(hasura, flowable)
    assert issue(workflow) == {"task_id": "t-ph", "document_id": OUT}
    assert flowable.completed == [("t-ph", {"outcome": "issue"})]

    row = only(hasura)
    assert (row["to_tenant_id"], row["status"], row["attempts"]) == (KT, "delivered", 0)
    assert files.dispatched == [row["id"]] and row["notified_at"]
    incoming = hasura.arrived[row["incoming_document_id"]]
    assert (incoming["tenant_id"], incoming["status"], incoming["source_id"]) == (KT, "received", OUT)

    # hàm CSDL chạy trong phiên của bên nhận, bằng tài khoản dịch vụ
    (_, variables, who), = [c for c in hasura.dispatch_calls if c[0] == "Deliver"]
    assert variables == {"id": row["id"]}
    assert (who.user_id, who.tenant_id, who.role) == ("svc-workflow", OTHER, "service")

    (note,) = incoming_notes(hasura)
    assert (note["user_id"], note["tenant_id"], note["document_id"]) == ("u-vanthu-kt", OTHER, incoming["id"])
    assert note["key"] == KEY.format(incoming["id"])
    assert note["data"]["from_name"] == "Khoa Công nghệ thông tin"
    assert note["data"]["summary"] == "Thông báo lịch họp giao ban" and note["data"]["direction"] == "in"
    # người soạn, người ký vẫn được báo đã phát hành như trước
    assert hasura.sent("document.issued") == {"document.issued": {"u-staff-dt", "u-director"}}

    # đối soát sau đó không còn gì để làm
    assert run(dispatcher.reconcile()) == 0
    assert files.dispatched == [row["id"]] and len(incoming_notes(hasura)) == 1


def test_two_units_each_get_their_own_incoming_document(workflow, hasura, flowable, files):
    third = "6a1f0b3e-2c4d-4e5f-8a9b-0c1d2e3f4a5b"
    hasura.units[third] = "Phòng Đào tạo"
    hasura.tenant_users[uuid.UUID(third)] = {
        "u-vanthu-dt": {"id": "u-vanthu-dt", "department_id": None, "role": "clerk", "enabled": True}}
    approved(hasura, flowable, units=(KT, third))
    issue(workflow)
    rows = list(hasura.dispatches.values())
    assert sorted(r["to_tenant_id"] for r in rows) == sorted([KT, third])
    assert all(r["status"] == "delivered" and r["notified_at"] for r in rows)
    assert {n["user_id"] for n in incoming_notes(hasura)} == {"u-vanthu-kt", "u-vanthu-dt"}
    assert len(hasura.arrived) == 2


def test_unit_without_clerks_tells_its_directors(workflow, hasura, flowable):
    del hasura.tenant_users[OTHER]["u-vanthu-kt"]
    approved(hasura, flowable)
    issue(workflow)
    assert [n["user_id"] for n in incoming_notes(hasura)] == ["u-truong-kt"]


def test_unit_with_nobody_to_tell_is_still_marked_notified(workflow, hasura, flowable, dispatcher):
    hasura.tenant_users[OTHER] = {}
    approved(hasura, flowable)
    issue(workflow)
    assert only(hasura)["notified_at"] and not incoming_notes(hasura)
    assert run(dispatcher.reconcile()) == 0     # không quay lại dòng này mãi


def test_outgoing_without_units_does_not_look_for_dispatches(workflow, hasura, flowable, files):
    hasura.outgoing.update(status="approved", signer_id="u-director")
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[CLERK_GROUP], doc=OUT)
    issue(workflow)
    assert not hasura.dispatches and not hasura.dispatch_calls and files.dispatch_tries == 0


# --- lỗi, thử lại ----------------------------------------------------------------------------------------


def test_backoff_doubles_from_thirty_seconds_up_to_an_hour():
    assert [backoff(n) for n in range(4)] == [timedelta(seconds=s) for s in (30, 60, 120, 240)]
    assert backoff(7) == backoff(500) == timedelta(hours=1)


def test_files_down_backs_off_and_reconcile_delivers_later(workflow, hasura, flowable, files, dispatcher, clock):
    approved(hasura, flowable)
    files.dispatch_down = True
    issue(workflow)       # phát hành vẫn xong
    assert flowable.completed == [("t-ph", {"outcome": "issue"})]
    row = only(hasura)
    assert (row["status"], row["attempts"]) == ("pending", 1)
    assert row["last_error"] == "Kho tệp hoặc trạm quét chưa sẵn sàng, sẽ thử lại"
    assert row["next_attempt_at"] == clock.now + timedelta(seconds=30)
    assert not hasura.arrived and not incoming_notes(hasura)

    tries = files.dispatch_tries
    assert run(dispatcher.reconcile()) == 0 and files.dispatch_tries == tries     # chưa đến hạn

    clock.tick(seconds=31)
    assert run(dispatcher.reconcile()) == 1
    assert (row["attempts"], row["next_attempt_at"]) == (2, clock.now + timedelta(seconds=60))

    files.dispatch_down = False
    clock.tick(minutes=2)
    assert run(dispatcher.reconcile()) == 1
    assert row["status"] == "delivered" and row["notified_at"] and len(hasura.arrived) == 1
    assert [n["user_id"] for n in incoming_notes(hasura)] == ["u-vanthu-kt"]


@pytest.mark.parametrize("code", ["not_issued", "restricted", "cold", "integrity", "infected", "unscannable"])
def test_lasting_refusals_fail_the_row_for_the_sender_to_see(workflow, hasura, flowable, files, dispatcher, clock,
                                                              code):
    approved(hasura, flowable)
    files.refuse = code
    issue(workflow)
    row = only(hasura)
    # thử lại cũng bị từ chối, mà dòng chờ còn chặn nộp lưu văn bản gửi: failed ngay, không hẹn lần sau
    assert (row["status"], row["attempts"], row["last_error"]) == ("failed", 0, f"svc-files từ chối: {code}")
    assert not hasura.arrived
    (_, _, who), = [c for c in hasura.dispatch_calls if c[0] == "FailDispatch"]
    assert (who.tenant_id, who.role) == (TENANT, "service")
    tries = files.dispatch_tries
    clock.tick(hours=2)
    assert run(dispatcher.reconcile()) == 0 and files.dispatch_tries == tries


def test_failing_to_mark_a_refusal_retries_later(workflow, hasura, flowable, files):
    approved(hasura, flowable)
    files.refuse, hasura.fail_fail = "cold", True
    issue(workflow)
    row = only(hasura)
    assert (row["status"], row["attempts"]) == ("pending", 1)


def test_database_error_is_retried_with_its_message(workflow, hasura, flowable, files, dispatcher, clock):
    approved(hasura, flowable)
    hasura.deliver_error = "Văn bản nguồn chưa phát hành"
    issue(workflow)
    row = only(hasura)
    assert (row["status"], row["attempts"], row["last_error"]) == ("pending", 1, "Văn bản nguồn chưa phát hành")
    # bên gửi ghi lại lần thử, bằng phiên của chính đơn vị gửi
    (_, _, who), = [c for c in hasura.dispatch_calls if c[0] == "DispatchRetry"]
    assert (who.tenant_id, who.role) == (TENANT, "service")

    hasura.deliver_error = None
    clock.tick(minutes=1)
    run(dispatcher.reconcile())
    # tệp chép lại trả dòng đã có: một bản sao, một văn bản đến
    assert row["status"] == "delivered" and files.copied == {row["id"]} and len(hasura.arrived) == 1


def test_network_error_does_not_leak_into_last_error(workflow, hasura, flowable):
    approved(hasura, flowable)
    real = hasura.as_service

    async def as_service(actor_, query, variables=None):
        if "mutation Deliver" in query:     # lỗi mạng: không có mã của CSDL, câu có địa chỉ nội bộ
            raise HasuraError("Không gọi được Hasura: [Errno -2] hasura:8080")
        return await real(actor_, query, variables)

    hasura.as_service = as_service
    issue(workflow)
    assert only(hasura)["last_error"] == "Chưa gọi được cơ sở dữ liệu, sẽ thử lại"


def test_rejected_delivery_is_final(workflow, hasura, flowable, files, dispatcher, clock):
    approved(hasura, flowable)
    hasura.deliver_rejects = "documents_in_summary: trích yếu không hợp lệ"
    issue(workflow)
    row = only(hasura)
    assert (row["status"], row["attempts"]) == ("failed", 0) and not incoming_notes(hasura)
    clock.tick(hours=2)
    assert run(dispatcher.reconcile()) == 0 and files.dispatched == [row["id"]]


def test_duplicate_is_linked_without_notifying(workflow, hasura, flowable, dispatcher):
    approved(hasura, flowable)
    hasura.already_received = True
    issue(workflow)
    row = only(hasura)
    assert (row["status"], row["incoming_document_id"]) == ("duplicate", RECEIVED_BY_HAND)
    assert row["notified_at"] and not incoming_notes(hasura) and not hasura.arrived
    assert run(dispatcher.reconcile()) == 0


# --- dừng giữa chừng, gọi chen nhau --------------------------------------------------------------------------


def test_delivered_but_not_notified_is_notified_by_reconcile_once(workflow, hasura, flowable, files, dispatcher):
    approved(hasura, flowable)
    hasura.fail_notify = True       # ghi thông báo lỗi ngay sau khi văn bản đến đã dựng
    issue(workflow)
    row = only(hasura)
    assert row["status"] == "delivered" and row["notified_at"] is None and not incoming_notes(hasura)

    hasura.fail_notify = False
    assert run(dispatcher.reconcile()) == 1
    assert row["notified_at"] and len(incoming_notes(hasura)) == 1
    assert run(dispatcher.reconcile()) == 0
    assert len(incoming_notes(hasura)) == 1 and files.dispatched == [row["id"]] and len(hasura.arrived) == 1


def test_crash_after_notifying_does_not_notify_twice(workflow, hasura, flowable, dispatcher):
    approved(hasura, flowable)
    hasura.fail_notified = 1        # đã báo, dừng trước khi kịp đặt notified_at
    issue(workflow)
    row = only(hasura)
    assert row["notified_at"] is None and len(incoming_notes(hasura)) == 1
    assert run(dispatcher.reconcile()) == 1
    assert row["notified_at"] and len(incoming_notes(hasura)) == 1


def test_issue_retry_after_flowable_error_dispatches_once(workflow, hasura, flowable, files, dispatcher):
    approved(hasura, flowable)
    flowable.fail_complete = 1
    with pytest.raises(WorkflowError, match="Đã lưu"):
        issue(workflow)
    row = only(hasura)
    assert row["status"] == "pending"       # dòng đã có cùng giao dịch phát hành, chưa chuyển

    issue(workflow)     # bấm lại: chỉ hoàn thành nốt trong Flowable, rồi chuyển
    assert len(hasura.dispatches) == 1 and len(hasura.arrived) == 1 and files.dispatched == [row["id"]]
    assert len([w for w in hasura.writes if w[0] == "PhatHanh"]) == 1
    assert len(incoming_notes(hasura)) == 1
    assert run(dispatcher.dispatch_document(OUT)) == 0


def test_concurrent_deliveries_take_turns(workflow, hasura, flowable, files, dispatcher, clock):
    approved(hasura, flowable)
    files.dispatch_down = True
    issue(workflow)
    row = only(hasura)
    files.dispatch_down, hasura.slow = False, True
    clock.tick(minutes=1)

    async def together():
        await asyncio.gather(dispatcher.deliver(row["id"]), dispatcher.reconcile(),
                             dispatcher.dispatch_document(OUT))

    run(together())
    assert files.dispatched == [row["id"]] and len(hasura.arrived) == 1 and len(incoming_notes(hasura)) == 1
    assert len([c for c in hasura.dispatch_calls if c[0] == "Deliver"]) == 1


def test_other_replica_delivering_first_is_followed(workflow, hasura, flowable, files):
    approved(hasura, flowable)

    def other_replica(dispatch_id: str) -> None:   # chuyển xong ngay trước lần chép của mình
        hasura.copied.add(dispatch_id)
        hasura.deliver_row(hasura.dispatches[dispatch_id])

    files.hook, files.refuse = other_replica, "not_pending"
    issue(workflow)
    row = only(hasura)
    assert (row["status"], row["attempts"]) == ("delivered", 0) and row["notified_at"]
    assert len(incoming_notes(hasura)) == 1
    assert not [c for c in hasura.dispatch_calls if c[0] in ("Deliver", "DispatchRetry")]


# --- không bao giờ làm hỏng phát hành ---------------------------------------------------------------------


def test_dispatch_is_bounded_in_time(workflow, hasura, flowable, files, dispatcher):
    approved(hasura, flowable)
    dispatcher.budget_s, files.delay = 0.05, 5
    started = time.monotonic()
    issue(workflow)
    assert time.monotonic() - started < 2
    assert flowable.completed == [("t-ph", {"outcome": "issue"})]
    assert only(hasura)["status"] == "pending"      # vòng nền chuyển tiếp


def test_failing_lookup_does_not_fail_the_issue(workflow, hasura, flowable):
    approved(hasura, flowable)
    hasura.fail_dispatch_query = True
    assert issue(workflow) == {"task_id": "t-ph", "document_id": OUT}
    assert flowable.completed == [("t-ph", {"outcome": "issue"})] and only(hasura)["status"] == "pending"


def test_unexpected_error_does_not_fail_the_issue(workflow, hasura, flowable, files, dispatcher, clock):
    approved(hasura, flowable)
    files.explode = True
    assert issue(workflow) == {"task_id": "t-ph", "document_id": OUT}
    assert only(hasura)["status"] == "pending"
    files.explode = False
    assert run(dispatcher.reconcile()) == 1 and only(hasura)["status"] == "delivered"


def test_failing_issued_notice_still_dispatches(workflow, hasura, flowable):
    approved(hasura, flowable)
    real = hasura.as_service
    calls = {"n": 0}

    async def as_service(actor_, query, variables=None):
        # thông báo "đã phát hành" cho người soạn lỗi; thông báo của bên nhận thì được
        if "mutation Notify" in query and actor_.tenant_id == TENANT:
            calls["n"] += 1
            raise HasuraError("Không gọi được Hasura")
        return await real(actor_, query, variables)

    hasura.as_service = as_service
    issue(workflow)
    assert calls["n"] >= 1 and only(hasura)["status"] == "delivered" and len(incoming_notes(hasura)) == 1


def test_dispatch_writes_never_carry_a_task_id(workflow, hasura, flowable):
    approved(hasura, flowable)
    issue(workflow)
    assert {c[0] for c in hasura.dispatch_calls} >= {"DocumentDispatches", "Dispatch", "Deliver", "DispatchNotified"}
    for op, variables, _ in hasura.dispatch_calls:
        assert "task_id" not in json.dumps(variables, default=str), op
    assert all("task_id" not in n["data"] for n in incoming_notes(hasura))
    # sự kiện mang task_id chỉ có của chính việc phát hành
    (_, variables, _), = [w for w in hasura.writes if w[0] == "PhatHanh"]
    assert variables["event"]["data"]["task_id"] == "t-ph"


def test_unknown_dispatch_is_ignored(dispatcher):
    assert run(dispatcher.deliver("99999999-9999-4999-8999-999999999999")) is None


# --- svc-files: POST /internal/dispatch-file --------------------------------------------------------------


def files_client(handler) -> FilesClient:
    def keycloak(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"access_token": "tok-svc", "expires_in": 300})

    token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                         transport=httpx2.MockTransport(keycloak))
    return FilesClient("http://svc-files:8000", token, transport=httpx2.MockTransport(handler))


DISPATCH_ID = "55555555-5555-4555-8555-555555555555"


@pytest.mark.parametrize("status", [200, 201])
def test_dispatch_file_posts_only_the_dispatch_id_with_the_service_token(status):
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, json={"file_id": "f", "sha256": "ab" * 32, "size_bytes": 1})

    async def go():
        client = files_client(handler)
        try:
            return await client.dispatch_file(DISPATCH_ID)
        finally:
            await client.aclose()

    assert run(go()) == {"file_id": "f", "sha256": "ab" * 32, "size_bytes": 1}
    (request,) = seen
    assert request.url.path == "/internal/dispatch-file"
    assert request.headers["authorization"] == "Bearer tok-svc"
    assert json.loads(request.content) == {"dispatch_id": DISPATCH_ID, "actor_id": "svc-workflow"}


@pytest.mark.parametrize(("status", "body", "code", "message"), [
    (409, {"detail": {"code": "cold", "message": "Tệp đã sang kho lạnh"}}, "cold", "Tệp đã sang kho lạnh"),
    (409, {"detail": {"code": "not_pending", "message": "Dòng liên thông không còn chờ"}}, "not_pending",
     "Dòng liên thông không còn chờ"),
    (409, {"detail": {"code": "la", "message": "?"}}, "http_409", "Dịch vụ tệp trả lỗi 409, sẽ thử lại"),
    (422, {"detail": {"code": "infected", "message": "Eicar"}}, "infected",
     "Trạm quét mã độc chặn bản phát hành khi chép sang đơn vị nhận"),
    (422, {"detail": {"code": "la", "message": "?"}}, "http_422", "Dịch vụ tệp trả lỗi 422, sẽ thử lại"),
    (503, {"detail": {"code": "storage_unavailable", "message": "Kho"}}, "unavailable",
     "Kho tệp hoặc trạm quét chưa sẵn sàng, sẽ thử lại"),
    (500, "không phải JSON", "http_500", "Dịch vụ tệp trả lỗi 500, sẽ thử lại"),
])
def test_dispatch_file_maps_refusals_to_codes(status, body, code, message):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if isinstance(body, str):
            return httpx2.Response(status, text=body)
        return httpx2.Response(status, json=body)

    async def go():
        client = files_client(handler)
        try:
            await client.dispatch_file(DISPATCH_ID)
        finally:
            await client.aclose()

    with pytest.raises(DispatchFileError) as err:
        run(go())
    assert (err.value.code, err.value.message, err.value.status) == (code, message, status)
    assert isinstance(err.value, FilesError)


def test_dispatch_file_unreachable_is_unavailable():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("svc-files:8000 refused", request=request)

    async def go():
        client = files_client(handler)
        try:
            await client.dispatch_file(DISPATCH_ID)
        finally:
            await client.aclose()

    with pytest.raises(DispatchFileError) as err:
        run(go())
    assert err.value.code == "unavailable" and "svc-files:8000" not in err.value.message
    assert "svc-files:8000" in err.value.detail


# --- nối vào ứng dụng ------------------------------------------------------------------------------------


def test_app_runs_the_dispatcher_beside_the_workflow(hasura, flowable):
    from test_app import ENV, NoDirectory

    app = create_app(Settings.from_env({**ENV, "MOC_DISPATCH_INTERVAL_S": "0"}), hasura=hasura, flowable=flowable,
                     directory=NoDirectory())  # type: ignore[arg-type]
    dispatcher = app.state.dispatcher
    assert isinstance(dispatcher, Dispatcher) and app.state.workflow.dispatcher is dispatcher
    assert app.state.workflow._turns is dispatcher.turns
    assert Settings.from_env(ENV).dispatch_interval_s == 30
