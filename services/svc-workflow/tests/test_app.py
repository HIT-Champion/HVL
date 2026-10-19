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

"""Lớp HTTP: chỉ Hasura gọi được, đúng định dạng Action, vai trò đúng thao tác."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import DOC, TENANT
from svc_workflow.app import create_app
from svc_workflow.config import ConfigError, Settings

ENV = {
    "HASURA_ADMIN_SECRET": "h", "MOC_ACTION_SECRET": "bi-mat-action", "FLOWABLE_ADMIN_PASSWORD": "f",
    "MOC_DIRECTORY_CLIENT_SECRET": "d", "MOC_DIRECTORY_SYNC_INTERVAL_S": "0", "MOC_RECONCILE_INTERVAL_S": "0",
    "MOC_PROCESSES_DIR": "/khong-co",
}


class NoDirectory:
    async def aclose(self) -> None: ...


@pytest.fixture
def client(hasura, flowable):
    app = create_app(Settings.from_env(ENV), hasura=hasura, flowable=flowable, directory=NoDirectory())  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


def body(name: str, role: str, payload: dict | None = None) -> dict:
    return {"action": {"name": name}, "input": payload or {},
            "session_variables": {"x-hasura-role": role, "x-hasura-user-id": "u-clerk", "x-hasura-tenant-id": str(TENANT)}}


def call(client, name, role, payload=None, secret="bi-mat-action"):
    return client.post(f"/actions/{name}", json=body(name, role, payload), headers={"X-Moc-Action-Secret": secret})


def test_requires_action_secret(client):
    assert call(client, "myTasks", "staff", secret="sai").status_code == 401
    r = client.post("/actions/myTasks", json=body("myTasks", "staff"))
    assert r.status_code == 401 and r.json()["extensions"]["code"] == "unauthorized"


def test_register_incoming_is_for_clerks_only(client):
    assert call(client, "registerIncoming", "director", {"documentId": DOC}).status_code == 403
    r = call(client, "registerIncoming", "clerk", {"documentId": DOC})
    assert r.status_code == 200 and r.json()["register_number"] == 7


def test_errors_use_hasura_action_format(client):
    r = call(client, "completeTask", "staff", {"taskId": "khong-co", "outcome": "done", "data": {}})
    assert r.status_code == 404
    assert set(r.json()) == {"message", "extensions"} and r.json()["extensions"]["code"] == "task_not_found"


def test_action_name_must_match_path(client):
    r = client.post("/actions/myTasks", json=body("registerIncoming", "clerk"), headers={"X-Moc-Action-Secret": "bi-mat-action"})
    assert r.status_code == 400


def test_missing_session_is_bad_request(client):
    r = client.post("/actions/myTasks", json={"action": {"name": "myTasks"}, "input": {}},
                    headers={"X-Moc-Action-Secret": "bi-mat-action"})
    assert r.status_code == 400


def test_openapi_documents_action_contract(client):
    spec = client.get("/openapi.json").json()
    op = spec["paths"]["/actions/{name}"]["post"]
    assert "session_variables" in op["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert "X-Moc-Action-Secret" in [p["name"] for p in op["parameters"]]
    assert {"401", "403", "409"} <= set(op["responses"])
    assert "/healthz" not in spec["paths"] and "/readyz" not in spec["paths"]

def test_config_requires_secrets():
    with pytest.raises(ConfigError, match="MOC_ACTION_SECRET"):
        Settings.from_env({k: v for k, v in ENV.items() if k != "MOC_ACTION_SECRET"})
