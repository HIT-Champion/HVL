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


"""Mã yêu cầu X-Request-Id (log tập trung F3.14): svc-workflow nhận hoặc tự sinh như svc-files, trả lại ở header,
ghi vào nhật ký của Action và các dòng cảnh báo, gửi tiếp sang Hasura (biến phiên → core.audit_log.request_id) và
svc-files."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import io
import json
import logging
import re
from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient

from conftest import DOC, OUT, TENANT, actor
from svc_workflow.advisor import Advisor
from svc_workflow.app import create_app
from svc_workflow.config import Settings
from svc_workflow.flowable import FlowableError
from svc_workflow.hasura import Actor, HasuraClient
from svc_workflow.workflow import Workflow, WorkflowError
from test_advisor import TODAY, Tick, call_similar, files_client, goi_y
from test_app import ENV, NoDirectory, body
from test_workflow import DIRECTOR_GROUP, direct_data


def run(coro):
    return asyncio.run(coro)


@contextlib.contextmanager
def lines() -> Iterator[list[dict]]:
    """Dòng JSON logger svc_workflow ghi trong khối (gắn handler sau create_app: bộ lọc PII ở mức logger vẫn chạy)."""
    log, stream = logging.getLogger("svc_workflow"), io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    level = log.level
    log.setLevel(logging.INFO)
    found: list[dict] = []
    try:
        yield found
    finally:
        log.removeHandler(handler)
        log.setLevel(level)
        for line in stream.getvalue().splitlines():
            if line.startswith("{"):
                found.append(json.loads(line))


@pytest.fixture
def app_and_actors(hasura, flowable, monkeypatch):
    seen = []

    async def my_tasks(self, who):
        seen.append(who)
        return []

    monkeypatch.setattr(Workflow, "my_tasks", my_tasks)
    app = create_app(Settings.from_env(ENV), hasura=hasura, flowable=flowable,
                     directory=NoDirectory())  # type: ignore[arg-type]
    return app, seen


def post_action(client: TestClient, headers: dict[str, str] | None = None):
    return client.post("/actions/myTasks", json=body("myTasks", "staff"),
                       headers={"X-Moc-Action-Secret": "bi-mat-action", **(headers or {})})


def test_action_keeps_the_given_request_id(app_and_actors):
    app, seen = app_and_actors
    with lines() as found, TestClient(app) as c:
        r = post_action(c, {"X-Request-Id": "req-85"})
    assert r.status_code == 200 and r.headers["x-request-id"] == "req-85"
    assert [a.request_id for a in seen] == ["req-85"]          # Actor mang mã → Hasura, svc-files nhận tiếp
    done = [x for x in found if x["event"] == "office.action.done"]
    assert [x["request_id"] for x in done] == ["req-85"]


def test_action_without_header_gets_a_fresh_id(app_and_actors):
    app, seen = app_and_actors
    with lines() as found, TestClient(app) as c:
        r = post_action(c)
        again = post_action(c)
    rid = r.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", rid) and again.headers["x-request-id"] != rid
    assert seen[0].request_id == rid
    assert [x["request_id"] for x in found if x["event"] == "office.action.done"][0] == rid


def test_every_route_answers_with_a_request_id(app_and_actors):
    app, _ = app_and_actors
    with TestClient(app) as c:
        r = c.get("/healthz", headers={"X-Request-Id": "req-h"})
        bad = c.post("/actions/myTasks", json=body("myTasks", "staff"))     # sai bí mật: vẫn có mã để tra
    assert r.headers["x-request-id"] == "req-h"
    assert bad.status_code == 401 and re.fullmatch(r"[0-9a-f]{32}", bad.headers["x-request-id"])


@pytest.mark.parametrize("bad", ["co dau cach", "a" * 129, "x\x1b[31m", "nguyenvana@example.com", "ma/khac"])
def test_malformed_request_id_is_replaced(app_and_actors, bad):
    app, seen = app_and_actors
    with lines() as found, TestClient(app) as c:
        r = post_action(c, {"X-Request-Id": bad})
    rid = r.headers["x-request-id"]
    # mã sai dạng không vào nhật ký, sổ kiểm toán: thay bằng mã mới, make logs-tra (cùng luật) tra được
    assert r.status_code == 200 and re.fullmatch(r"[0-9a-f]{32}", rid)
    assert seen[0].request_id == rid
    assert [x["request_id"] for x in found if x["event"] == "office.action.done"] == [rid]


def test_longest_allowed_request_id_is_kept(app_and_actors):
    app, seen = app_and_actors
    good = "goi-y:" + "A1._-" * 24 + "zz"          # đúng 128 ký tự, đủ các loại ký tự được phép
    assert len(good) == 128
    with TestClient(app) as c:
        r = post_action(c, {"X-Request-Id": good})
    assert r.headers["x-request-id"] == good and seen[0].request_id == good


@pytest.mark.parametrize("how", ["as_service", "as_user"])
@pytest.mark.parametrize("request_id", ["req-85", ""])
def test_hasura_calls_carry_the_request_id(how, request_id):
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"data": {"ok": True}})

    async def go():
        client = HasuraClient("http://hasura:8080", "khoa", transport=httpx2.MockTransport(handler))
        who = actor("clerk")
        who = type(who)(who.user_id, who.tenant_id, who.role, who.department_id, request_id)
        try:
            return await getattr(client, how)(who, "query X { x }")
        finally:
            await client.aclose()

    assert run(go()) == {"ok": True}
    headers = seen[0].headers
    # biến phiên cho trigger sổ kiểm toán; X-Request-Id cho nhật ký của Hasura
    assert headers.get("x-hasura-request-id") == (request_id or None)
    assert headers.get("x-request-id") == (request_id or None)
    assert headers["x-hasura-tenant-id"] == str(TENANT)


def test_warning_lines_carry_the_request_id(workflow, flowable, monkeypatch):
    async def refuse(task_id, user_id):
        raise FlowableError("down")

    async def boom():
        raise RuntimeError("Centrifugo không trả lời")

    monkeypatch.setattr(flowable, "claim", refuse)
    with lines() as found:
        run(workflow._unclaim("t-1", "req-85"))
        run(workflow._quietly("announce", "d-1", boom, "req-85"))
    by_event = {x["event"]: x for x in found}
    assert by_event["office.task.unclaim_failed"] == {"event": "office.task.unclaim_failed", "task_id": "t-1",
                                                      "request_id": "req-85"}
    assert by_event["core.notification.failed"]["request_id"] == "req-85"


REQ = "req-85"


def _who(role: str, user: str, **kw) -> Actor:
    return dataclasses.replace(actor(role, user, **kw), request_id=REQ)


def _start_failed(workflow, hasura, flowable, files, monkeypatch):
    flowable.down = True                                     # vào sổ xong, Flowable không khởi chạy được
    run(workflow.register_incoming(_who("clerk", "u-clerk"), DOC))


def _unlinked(workflow, hasura, flowable, files, monkeypatch):
    hasura.fail_writes = "Không gọi được Hasura"             # quy trình đã chạy, ghi process_id lỗi
    run(workflow.register_incoming(_who("clerk", "u-clerk"), DOC))


def _duplicate_left(workflow, hasura, flowable, files, monkeypatch):
    async def refuse(process_id, reason):
        raise FlowableError("down")

    hasura.rival_process = "proc-rival"                      # thua lượt gắn quy trình, hủy quy trình thừa lỗi
    monkeypatch.setattr(flowable, "delete_process", refuse)
    run(workflow.register_incoming(_who("clerk", "u-clerk"), DOC))


def _share_failed(workflow, hasura, flowable, files, monkeypatch):
    hasura.document["restricted"] = True
    hasura.viewers = {"u-clerk"}
    hasura.fail_share = True
    flowable.then(DOC, "t-chidao", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    run(workflow.register_incoming(_who("clerk", "u-clerk"), DOC))


def _retry_other_outcome(workflow, hasura, flowable, files, monkeypatch):
    flowable.add_task("t1", "vbden.chiDao", groups=[DIRECTOR_GROUP])
    flowable.fail_complete = 1                               # lần đầu đã ghi CSDL, Flowable lỗi
    director = _who("director", "u-director")
    with pytest.raises(WorkflowError):
        run(workflow.complete_task(director, "t1", "file", {"note": "Lưu"}))
    run(workflow.complete_task(director, "t1", "direct", direct_data()))   # bấm lại, chọn kết quả khác


def _render_failed(workflow, hasura, flowable, files, monkeypatch):
    hasura.outgoing.update(status="approved", signer_id="u-director")
    flowable.add_task("t-ph", "vbdi.phatHanh", groups=[f"t:{TENANT}:clerk"], doc=OUT)
    files.down = True
    with pytest.raises(WorkflowError):
        run(workflow.complete_task(_who("clerk", "u-clerk"), "t-ph", "issue", {}))


@pytest.mark.parametrize(("event", "scene"), [
    ("office.process.start_failed", _start_failed),
    ("office.process.unlinked", _unlinked),
    ("office.process.duplicate_left", _duplicate_left),
    ("office.acl.share_failed", _share_failed),
    ("office.task.retry_other_outcome", _retry_other_outcome),
    ("office.document.render_failed", _render_failed),
])
def test_each_warning_carries_the_callers_request_id(workflow, hasura, flowable, files, monkeypatch, event, scene):
    with lines() as found:
        scene(workflow, hasura, flowable, files, monkeypatch)
    hits = [x for x in found if x["event"] == event]
    assert hits, f"không có dòng {event}: {[x['event'] for x in found]}"
    assert [x.get("request_id") for x in hits] == [REQ] * len(hits)


def test_similar_sends_the_request_id():
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"hits": []})

    call_similar(handler)
    assert "x-request-id" not in seen[0].headers                     # không có mã thì không gửi header rỗng

    async def go():
        client = files_client(handler)
        try:
            return await client.similar(TENANT, DOC, request_id="goi-y:g1")
        finally:
            await client.aclose()

    run(go())
    assert seen[-1].headers["x-request-id"] == "goi-y:g1"


def test_advisor_job_id_reaches_svc_files(hasura, flowable, files):
    advisor = Advisor(hasura, flowable, files, Settings.from_env(ENV), clock=Tick(),  # type: ignore[arg-type]
                      today=lambda: TODAY)
    goi_y(flowable, "g7")
    assert run(advisor.run_jobs()) == 1
    assert files.similar_request_ids == ["goi-y:g7"]
