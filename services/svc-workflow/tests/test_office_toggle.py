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

"""Cờ MOC_OFFICE_ENABLED (docs/architecture.md §4.7, bước 2): tắt Văn phòng điện tử thì svc-workflow vẫn lên với phần
chung — không route Actions, /ot/notify, không triển khai BPMN văn bản, không vòng định kỳ nào của Văn phòng; bật (mặc
định) thì route, việc nền như trước khi tách."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import SCHEMAS, TENANT
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings
from svc_workflow.office import api as office_api
from svc_workflow.office.api import Office

SECRET = "bi-mat-action"
# mọi chu kỳ để mặc định (> 0) và bật IT/OT: thấy được vòng nào chạy, vòng nào không
ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": SECRET, "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_PROCESSES_DIR": "/app/processes", "MOC_SCHEMAS_DIR": str(SCHEMAS),
    "MOC_NGSI_URL": "http://scorpio:9090",
}
# form văn bản đến (MOC_SCHEMAS_DIR) là của Văn phòng: tắt thì không đọc, thư mục không có cũng lên
OFF = {**ENV, "MOC_OFFICE_ENABLED": "false", "MOC_SCHEMAS_DIR": "/khong-co"}
COMMON_JOBS = {"directory", "notify"}
OFFICE_LOOPS = {"office.process.reconciled", "office.document.overdue_notified", "office.dispatch.reconciled",
                "office.sla.jobs_handled", "office.assign.jobs_handled", "ot.subscriptions_ensured"}
# app.routes trước khi tách: bốn route tài liệu của FastAPI, /healthz, /readyz, rồi hai route của Văn phòng
ROUTES = [("/openapi.json", {"GET", "HEAD"}), ("/docs", {"GET", "HEAD"}), ("/docs/oauth2-redirect", {"GET", "HEAD"}),
          ("/redoc", {"GET", "HEAD"}), ("/healthz", {"GET"}), ("/readyz", {"GET"}),
          ("/ot/notify/{tenant}", {"POST"}), ("/actions/{name}", {"POST"})]


class Started:
    """Tên các việc nền đã chạy; việc giả chờ tới khi app dừng thì bị hủy."""

    def __init__(self) -> None:
        self.names: list[str] = []

    async def hold(self, name: str) -> None:
        self.names.append(name)
        await asyncio.Event().wait()


class Directory:
    def __init__(self, started: Started) -> None:
        self.started = started

    async def run(self, interval_s: float) -> None:
        await self.started.hold("directory")

    async def aclose(self) -> None: ...


class Router:
    def __init__(self, started: Started) -> None:
        self.started = started

    async def serve(self, interval_s: float) -> None:
        await self.started.hold("notify")

    async def aclose(self) -> None: ...


class Notifier:
    def __init__(self, router: Router) -> None:
        self.router = router

    async def aclose(self) -> None: ...


def wait_until(ok: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not ok() and time.monotonic() < deadline:
        time.sleep(0.01)


@pytest.fixture
def started(monkeypatch) -> Started:
    s = Started()
    # vòng định kỳ của Văn phòng chỉ ghi tên, không chạy việc thật
    monkeypatch.setattr(office_api, "every", lambda interval_s, name, job: s.hold(name))
    return s


@pytest.fixture
def deployed(flowable) -> list[str]:
    seen: list[str] = []

    async def deploy_dir(directory: str) -> list[str]:
        seen.append(directory)
        return []

    async def ping() -> bool:
        return True

    flowable.deploy_dir = deploy_dir
    flowable.ping = ping
    return seen


def make_app(env: dict[str, str], hasura, flowable, files, started: Started) -> Any:
    fakes: dict[str, Any] = {"directory": Directory(started), "notifier": Notifier(Router(started))}
    return create_app(Settings.from_env(env), hasura=hasura, flowable=flowable, files=files, **fakes)


def my_tasks(client: TestClient):
    body = {"action": {"name": "myTasks"}, "input": {},
            "session_variables": {"x-hasura-role": "staff", "x-hasura-user-id": "u-staff-dt",
                                  "x-hasura-tenant-id": str(TENANT)}}
    return client.post("/actions/myTasks", json=body, headers={"X-Moc-Action-Secret": SECRET})


def routes(app) -> list[tuple[str, set[str]]]:
    return [(r.path, set(r.methods)) for r in app.routes]


def test_office_flag_is_on_by_default_and_reads_like_other_flags():
    assert Settings.from_env(ENV).office_enabled is True
    assert Settings.from_env({**ENV, "MOC_OFFICE_ENABLED": "true"}).office_enabled is True
    for value in ("false", "0", "off", "no", " False "):
        assert Settings.from_env({**ENV, "MOC_OFFICE_ENABLED": value}).office_enabled is False
    with pytest.raises(ConfigError, match="MOC_OFFICE_ENABLED"):
        Settings.from_env({**ENV, "MOC_OFFICE_ENABLED": "tat"})


def test_office_on_keeps_routes_and_background_jobs(hasura, flowable, files, started, deployed):
    app = make_app(ENV, hasura, flowable, files, started)
    assert routes(app) == ROUTES
    assert list(app.openapi()["paths"]) == ["/ot/notify/{tenant}", "/actions/{name}"]
    office = app.state.office
    assert isinstance(office, Office) and app.state.workflow is office.workflow and app.state.ot is office.ot
    with TestClient(app) as c:
        wait_until(lambda: set(started.names) >= COMMON_JOBS | OFFICE_LOOPS and bool(deployed))
        assert my_tasks(c).status_code == 200
    assert sorted(started.names) == sorted(COMMON_JOBS | OFFICE_LOOPS)
    assert deployed == ["/app/processes"]


def test_office_off_still_starts_with_the_shared_part_only(hasura, flowable, files, started, deployed):
    app = make_app(OFF, hasura, flowable, files, started)
    assert routes(app) == ROUTES[:6]
    assert app.openapi()["paths"] == {}
    assert app.state.office is None and not hasattr(app.state, "workflow")
    with TestClient(app) as c:
        wait_until(lambda: set(started.names) >= COMMON_JOBS)
        assert c.get("/healthz").json() == {"status": "ok"}
        assert c.get("/readyz").status_code == 200
        assert my_tasks(c).status_code == 404
        assert c.post("/ot/notify/CNTT", json={"data": []}).status_code == 404
    # vòng của phần chung (danh bạ, kênh thông báo) vẫn chạy; không triển khai BPMN văn bản, không vòng nào của
    # Văn phòng
    assert sorted(started.names) == sorted(COMMON_JOBS)
    assert deployed == []
