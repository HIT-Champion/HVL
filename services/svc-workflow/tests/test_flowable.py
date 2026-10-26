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


"""Client Flowable REST: chỉ lỗi khóa lạc quan (giao dịch khác cùng sửa phiên quy trình) mới được gọi lại (#189)."""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from svc_workflow import flowable
from svc_workflow.flowable import FlowableClient, FlowableError, Task

BASE = "http://flowable:8080/flowable-rest/service"
# body lỗi 500 của BaseExceptionHandlerAdvice khi gặp FlowableOptimisticLockingException (run 40197127090 của CI)
CONCURRENT = {"message": "Internal server error",
              "exception": "Execution[ id '8dd073b9' ] - definition 'van-ban-den:1:2906c0a0' - activity 'hanChiDao' "
                           "- parent '8dd073b1' was updated by another transaction concurrently"}
# dạng thông điệp PersistenceException của MyBatis khi PostgreSQL hủy một bên của deadlock; deadlock này thấy ở
# run 40337213084 của CI (#316)
DEADLOCK = {"message": "Internal server error",
            "exception": "\n### Error updating database.  Cause: org.postgresql.util.PSQLException: ERROR: deadlock "
                         "detected\n  Detail: Process 84 waits for ShareLock on transaction 2812; blocked by process "
                         "85.\n### SQL: delete from ACT_RU_EXECUTION where ID_ = ? and REV_ = ?"}
OTHER_500 = {"message": "Internal server error", "exception": "Cannot invoke \"Object.toString()\" because x is null"}


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(flowable, "RETRY_DELAYS_S", (0.0, 0.0))


def calls(answers: list[tuple[int, dict | None]], call):
    """Chạy ``call(client)`` với Flowable giả trả lần lượt ``answers``; trả về (kết quả hoặc lỗi, các đường đã gọi)."""
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        status, body = answers[len(seen) - 1]
        return httpx2.Response(status, json=body) if body is not None else httpx2.Response(status)

    async def go():
        client = FlowableClient(BASE, "rest-admin", "x", transport=httpx2.MockTransport(handler))
        try:
            return await call(client)
        except FlowableError as exc:
            return exc
        finally:
            await client.aclose()

    return asyncio.run(go()), seen


def test_complete_is_retried_after_optimistic_locking():
    got, seen = calls([(500, CONCURRENT), (204, None)], lambda c: c.complete("t-1", {"outcome": "assign"}))
    assert got is None and seen == ["/flowable-rest/service/runtime/tasks/t-1"] * 2


def test_complete_job_is_retried_after_optimistic_locking():
    got, seen = calls([(500, CONCURRENT), (500, CONCURRENT), (204, None)], lambda c: c.complete_job("j-1", "w"))
    assert got is None and seen == ["/flowable-rest/external-job-api/acquire/jobs/j-1/complete"] * 3


def test_complete_is_retried_after_a_deadlock():
    got, seen = calls([(500, DEADLOCK), (204, None)], lambda c: c.complete("t-1", {"outcome": "assign"}))
    assert got is None and seen == ["/flowable-rest/service/runtime/tasks/t-1"] * 2


def test_complete_job_is_retried_after_a_deadlock():
    got, seen = calls([(500, DEADLOCK), (204, None)], lambda c: c.complete_job("j-1", "w"))
    assert got is None and seen == ["/flowable-rest/external-job-api/acquire/jobs/j-1/complete"] * 2


def test_retries_stop_after_the_last_delay():
    got, seen = calls([(500, CONCURRENT)] * 3, lambda c: c.complete("t-1", {}))
    assert isinstance(got, FlowableError) and got.status == 500 and got.concurrent and len(seen) == 3


@pytest.mark.parametrize("status, body", [(500, OTHER_500), (409, CONCURRENT), (409, DEADLOCK), (404, None),
                                          (503, None)])
def test_other_errors_are_not_retried(status, body):
    got, seen = calls([(status, body), (204, None)], lambda c: c.complete("t-1", {}))
    assert isinstance(got, FlowableError) and got.status == status and not got.concurrent and len(seen) == 1


def test_task_process_key_is_empty_when_flowable_dropped_the_key():
    def task(definition_id: str) -> Task:
        return Task("t-1", "Duyệt", "nghi-phep.duyet", None, "p-1", "2026-10-26T00:00:00Z",
                    process_definition_id=definition_id)
    assert task("nghi-phep.don:3:8a0c6a52-0000-4000-8000-000000000001").process_key == "nghi-phep.don"
    # id quá 64 ký tự: Flowable chỉ để uuid — không đoán khóa, không khớp quy trình nào
    assert task("8a0c6a52-0000-4000-8000-000000000001").process_key == ""
    assert task("").process_key == ""


def raw_paths(call) -> list[bytes]:
    """Đường gọi tới Flowable, đúng như gửi đi (chưa giải mã); Flowable giả trả 404 cho mọi yêu cầu."""
    seen: list[bytes] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.raw_path)
        return httpx2.Response(404, json={"message": "Not found"})

    async def go():
        client = FlowableClient(BASE, "rest-admin", "x", transport=httpx2.MockTransport(handler))
        try:
            await call(client)
        except FlowableError:
            pass
        finally:
            await client.aclose()

    asyncio.run(go())
    return seen


@pytest.mark.parametrize("given, sent", [
    ("../t-2?x=1#y", b"..%2Ft-2%3Fx%3D1%23y"),
    ("..", b"%2E%2E"),
    ("nghi-phep.don:3:8a0c6a52", b"nghi-phep.don%3A3%3A8a0c6a52"),
])
@pytest.mark.parametrize("call, path", [
    (lambda c, i: c.task(i), b"/runtime/tasks/"),
    (lambda c, i: c.candidate_groups(i), b"/runtime/tasks/"),
    (lambda c, i: c.claim(i, "u-1"), b"/runtime/tasks/"),
    (lambda c, i: c.complete(i, {}), b"/runtime/tasks/"),
    (lambda c, i: c.complete_typed(i, []), b"/runtime/tasks/"),
    (lambda c, i: c.delete_process(i, "thừa"), b"/runtime/process-instances/"),
    (lambda c, i: c.set_variables(i, {}), b"/runtime/process-instances/"),
    (lambda c, i: c.definition(i), b"/repository/process-definitions/"),
    (lambda c, i: c.set_definition_state(i, "suspend"), b"/repository/process-definitions/"),
    (lambda c, i: c.resource(i, "forms/don.json"), b"/repository/deployments/"),
])
def test_ids_stay_one_path_segment(given, sent, call, path):
    # id lấy từ yêu cầu gửi lên: "/", "?", "#", ".." không đổi được đường gọi tới Flowable
    seen = raw_paths(lambda client: call(client, given))
    assert len(seen) == 1
    assert seen[0].startswith(b"/flowable-rest/service" + path + sent)
    assert seen[0].removeprefix(b"/flowable-rest/service" + path + sent)[:1] in (b"", b"/", b"?")   # ? của client
