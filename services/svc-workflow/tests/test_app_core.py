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

"""Chỗ quy trình của ứng dụng chạm vào lõi: hộp việc Văn phòng điện tử không lẫn việc của ứng dụng (cùng một
Flowable), và các lệnh REST mới của client Flowable."""

from __future__ import annotations

import asyncio
import json

import httpx2
import pytest

from conftest import DEPT_DT, TENANT, actor
from svc_workflow.flowable import FlowableClient, FlowableError
from svc_workflow.workflow import WorkflowError

BASE = "http://flowable:8080/flowable-rest/service"
DIRECTOR_GROUP = f"t:{TENANT}:director"
MANAGER_DT_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"


def run(coro):
    return asyncio.run(coro)


# --- hộp việc Văn phòng điện tử ------------------------------------------------------------------------------


def test_office_inbox_leaves_out_app_tasks_even_with_office_like_variables(workflow, flowable):
    """Form của ứng dụng khai được trường tên documentId: chỉ khóa quy trình mới phân biệt việc của ai."""
    flowable.add_task("t-office", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    flowable.add_task("t-app", "nghi-phep.duyet", groups=[DIRECTOR_GROUP], key="nghi-phep.don")
    flowable.add_task("t-app-mine", "nghi-phep.duyet", assignee="u-director", key="nghi-phep.don")
    ids = [t["id"] for t in run(workflow.my_tasks(actor("director", "u-director")))]
    assert ids == ["t-office"]


def test_office_cannot_complete_an_app_task(workflow, flowable):
    flowable.add_task("t-app", "vbden.chiDao", groups=[DIRECTOR_GROUP], key="nghi-phep.don")
    with pytest.raises(WorkflowError) as e:
        run(workflow.complete_task(actor("director", "u-director"), "t-app", "direct", {}))
    assert e.value.status == 404 and e.value.code == "task_not_found"
    assert flowable.claims == [] and flowable.completed == []


def test_office_still_completes_its_own_outgoing_tasks(workflow, flowable):
    flowable.add_task("t-di", "vbdi.duyetPhong", groups=[MANAGER_DT_GROUP])
    tasks = run(workflow.my_tasks(actor("manager", "u-manager", dept=DEPT_DT)))
    assert [t["id"] for t in tasks] == ["t-di"]


# --- client Flowable REST ------------------------------------------------------------------------------------


def calls(answers: list[tuple[int, object]], call) -> tuple[object, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        request.read()
        seen.append(request)
        status, body = answers[len(seen) - 1]
        if isinstance(body, bytes):
            return httpx2.Response(status, content=body)
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


def body(request: httpx2.Request) -> dict:
    return json.loads(request.content)


def test_deployments_newest_first_by_name():
    got, seen = calls([(200, {"data": [{"id": "d-2", "name": "app/nghi-phep@abc"}]})],
                      lambda c: c.deployments("app/nghi-phep@%"))
    assert got == [{"id": "d-2", "name": "app/nghi-phep@abc"}]
    assert seen[0].url.path.endswith("/repository/deployments")
    assert dict(seen[0].url.params) == {"nameLike": "app/nghi-phep@%", "sort": "deployTime", "order": "desc",
                                        "size": "1"}


def test_deploy_zip_is_one_multipart_upload():
    got, seen = calls([(201, {"id": "d-1"})], lambda c: c.deploy_zip("app/x@1", "x.zip", b"PK\x03\x04"))
    assert got == {"id": "d-1"} and seen[0].method == "POST"
    assert seen[0].url.params["deploymentName"] == "app/x@1"
    assert seen[0].headers["content-type"].startswith("multipart/form-data")
    assert b'filename="x.zip"' in seen[0].content and b"PK\x03\x04" in seen[0].content


def test_resource_is_read_raw_and_missing_is_none():
    got, seen = calls([(200, b'{"a": 1}')], lambda c: c.resource("d-1", "nghi-phep.don.json"))
    assert got == b'{"a": 1}'
    assert seen[0].url.raw_path.decode().endswith("/repository/deployments/d-1/resourcedata/nghi-phep.don.json")
    assert calls([(404, None)], lambda c: c.resource("d-1", "x"))[0] is None
    assert isinstance(calls([(500, None)], lambda c: c.resource("d-1", "x"))[0], FlowableError)


def test_definitions_and_state():
    got, seen = calls([(200, {"data": [{"id": "k:1:d"}]})], lambda c: c.definitions(keyLike="nghi-phep.%",
                                                                                   suspended="false"))
    assert got == [{"id": "k:1:d"}]
    assert dict(seen[0].url.params) == {"keyLike": "nghi-phep.%", "suspended": "false", "size": "1000"}
    assert calls([(404, None)], lambda c: c.definition("k:1:d"))[0] is None
    assert isinstance(calls([(503, None)], lambda c: c.definition("k:1:d"))[0], FlowableError)
    _, seen = calls([(200, {})], lambda c: c.set_definition_state("k:1:d", "suspend"))
    assert seen[0].method == "PUT" and body(seen[0]) == {"action": "suspend", "includeProcessInstances": True}
    assert seen[0].url.raw_path.decode().endswith("/repository/process-definitions/k%3A1%3Ad")


def test_start_definition_query_and_complete_typed():
    variables = [{"name": "soNgay", "type": "long", "value": 3}]
    got, seen = calls([(201, {"id": "p-1"})], lambda c: c.start_definition("k:1:d", variables))
    assert got == "p-1" and body(seen[0]) == {"processDefinitionId": "k:1:d", "variables": variables}
    row = {"id": "t-1", "name": "Duyệt", "formKey": "nghi-phep.duyet", "assignee": None, "processInstanceId": "p-1",
           "createTime": "2026-10-26T09:00:00.000+07:00", "processDefinitionId": "nghi-phep.don:1:d",
           "dueDate": "2026-10-28T09:00:00.000+07:00", "variables": [{"name": "loai", "value": "om"}]}
    got, seen = calls([(200, {"data": [row]})], lambda c: c.query_tasks({"processDefinitionKeyLike": "nghi-phep.%"}))
    assert got[0].process_key == "nghi-phep.don" and got[0].due_at == row["dueDate"]
    assert got[0].variables == {"loai": "om"}
    assert body(seen[0]) == {"processDefinitionKeyLike": "nghi-phep.%", "includeProcessVariables": True, "size": 500}
    got, seen = calls([(200, {"data": [{"id": "p-1"}]})], lambda c: c.historic_processes({"processDefinitionKey": "k"}))
    assert got == [{"id": "p-1"}] and seen[0].url.path.endswith("/query/historic-process-instances")
    _, seen = calls([(200, None)], lambda c: c.complete_typed("t-1", variables))
    assert body(seen[0]) == {"action": "complete", "variables": variables}
